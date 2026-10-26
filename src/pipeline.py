"""Campaign-to-roster backend; collection happens only for a new/refresh run."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from .campaign import (
    Campaign,
    DIMENSIONS,
    default_weights,
    default_priorities,
    audit_controls,
)
from .evaluation import evaluate, dimension, cosine, valid_trends
from .ranking import (
    relative_scores,
    select_roster,
    weighted_score,
    manual_swap,
    marginal_components,
)
from .screening import screen, relative
from .rank_correlation import spearman_rho

SCORING_VERSION = "locked-2"
PROMPT_VERSION = "metadata-evidence-1"


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def code_version():
    return fingerprint(
        {
            p.name: p.read_text(encoding="utf-8")
            for p in sorted(Path(__file__).parent.glob("*.py"))
        }
    )


def run(
    campaign,
    provider,
    at=None,
    trend_snapshot=None,
    min_comments=10,
    reach_exponent=1.0,
):
    at = at or datetime.now(timezone.utc)
    if at.tzinfo is None:
        raise ValueError("Run time must include timezone")
    if (
        not isinstance(min_comments, int)
        or isinstance(min_comments, bool)
        or min_comments < 1
    ):
        raise ValueError("min_comments must be a positive integer")
    if not 0 < reach_exponent <= 5:
        raise ValueError("reach_exponent must be between 0 and 5")
    valid_trends(trend_snapshot, at)
    if (
        trend_snapshot is not None
        and trend_snapshot.get("campaign_fingerprint") != campaign.fingerprint()
    ):
        raise ValueError("Trend snapshot belongs to a different campaign")
    discovery = provider.discover(campaign)
    # Provider output is deduplicated by stable channel ID, preserving all matches.
    unique = {}
    for candidate in discovery["candidates"]:
        key = candidate["channel_id"]
        if key not in unique:
            unique[key] = deepcopy(candidate)
        else:
            for match in candidate["matches"]:
                if match not in unique[key]["matches"]:
                    unique[key]["matches"].append(match)
    channels = [provider.channel(c) for c in unique.values()]
    shortlisted, screening = screen(channels, at)
    evaluated = []
    for record in shortlisted:
        channel = record["channel"]
        channel["comment_records"] = provider.comments(channel)
        analysis = evaluate(channel, campaign, provider, trend_snapshot, min_comments)
        candidate = {
            "handle": channel["handle"],
            "channel_id": channel["channel_id"],
            "title": channel["title"],
            "screening_score": record["screening_score"],
            "creator_health": record["health"],
            "shortlist_reason": record["selection_reason"],
            **analysis,
        }
        for d in ("engagement", "momentum", "speed_to_activate"):
            candidate["dimensions"][d] = dimension(
                record["raw"][d],
                f"Measured from {record['raw']['usable_uploads']} usable uploads",
                counts={k: record["raw"][k] for k in ("recent_count", "prior_count")},
            )
        candidate["capabilities"]["reach"] = (
            relative(
                record["raw"]["median_views"],
                [r["raw"]["median_views"] for r in shortlisted],
            )
            ** reach_exponent
        )
        candidate["capabilities"]["speed"] = relative(
            record["raw"]["speed_to_activate"],
            [r["raw"]["speed_to_activate"] for r in shortlisted],
        )
        evaluated.append(candidate)
    for candidate in evaluated:
        signals = candidate["capability_signals"]
        demo = relative(
            signals["format_lift"],
            [c["capability_signals"]["format_lift"] for c in evaluated],
        )
        depth = relative(
            signals["comment_depth"],
            [c["capability_signals"]["comment_depth"] for c in evaluated],
        )
        candidate["capabilities"]["demonstration"] = demo if demo is not None else 0
        candidate["capabilities"]["credibility"] = max(
            signals["expertise"], depth if depth is not None else 0
        )
        candidate["similarity"], candidate["similarity_components"] = {}, {}
        for other in evaluated:
            if other is candidate:
                continue
            pair = {
                kind: (
                    max(
                        0,
                        min(
                            1,
                            cosine(
                                candidate[kind + "_embedding"],
                                other[kind + "_embedding"],
                            ),
                        ),
                    )
                    if candidate[kind + "_embedding"] and other[kind + "_embedding"]
                    else None
                )
                for kind in ("content", "comment")
            }
            observed = [v for v in pair.values() if v is not None]
            candidate["similarity"][other["handle"]] = (
                sum(observed) / len(observed) if observed else 0
            )
            candidate["similarity_components"][other["handle"]] = pair
    weights, priorities = default_weights(campaign.objective), default_priorities(
        campaign.objective
    )
    run_id = str(uuid4())
    snapshot = {
        "run_id": run_id,
        "run_version": 1,
        "scoring_version": SCORING_VERSION,
        "prompt_version": PROMPT_VERSION,
        "code_version": code_version(),
        "mode": provider.mode,
        "model": provider.model,
        "created_at": at.isoformat(),
        "data_snapshot_at": at.isoformat(),
        "campaign": campaign.canonical(),
        "campaign_fingerprint": campaign.fingerprint(),
        "default_weights": weights,
        "default_priorities": priorities,
        "weights": weights,
        "capability_priorities": priorities,
        "calibration": {"min_comments": min_comments, "reach_exponent": reach_exponent},
        "trend_snapshot": trend_snapshot,
        "trend_snapshot_at": trend_snapshot["fetched_at"] if trend_snapshot else None,
        "discovery": discovery,
        "channels": channels,
        "screening": screening,
        "evaluated": evaluated,
        "audit": [audit_controls(weights, priorities, "objective defaults")],
    }
    snapshot["data_hash"] = fingerprint(
        {"channels": channels, "evaluated": evaluated, "trends": trend_snapshot}
    )
    return score_snapshot(snapshot)


def score_snapshot(snapshot):
    result = deepcopy(snapshot)
    result["ranking"] = relative_scores(result["evaluated"], result["weights"])
    result["roster"] = select_roster(result["ranking"], result["capability_priorities"])
    return summarize(result)


def summarize(result):
    result["warnings"] = []
    if result["mode"] != "live":
        result["warnings"].append(
            "SYNTHETIC DEMO: creators, comments and model judgments are test data."
        )
    if result["trend_snapshot"] is None:
        result["warnings"].append(
            "Google Trends snapshot unavailable: Trend Fit is unmeasured."
        )
    if len(result["roster"]) < 4:
        result["warnings"].append(
            f"Only {len(result['roster'])} eligible creators; roster is incomplete."
        )
    for c in result["roster"]:
        if c["brand_safety"] == "REVIEW":
            result["warnings"].append(
                f"{c['handle']}: metadata safety review required."
            )
        if c["missing_dimensions"]:
            result["warnings"].append(
                f"{c['handle']}: missing evidence for {', '.join(c['missing_dimensions'])}."
            )
    covered = {
        k: max((c["capabilities"][k] for c in result["roster"]), default=0)
        for k in result["capability_priorities"]
    }
    result["coverage"] = covered
    for key, value in covered.items():
        if result["capability_priorities"][key] > 0 and value < 0.5:
            result["warnings"].append(f"Weak {key} coverage; review alternatives.")
    for i, c in enumerate(result["roster"]):
        for other in result["roster"][:i]:
            if c["similarity"].get(other["handle"], 0) > 0.85:
                result["warnings"].append(
                    f"{c['handle']} and {other['handle']} have similar content/comment language; this does not establish shared viewers."
                )
        previous = result["roster"][:i]
        unavailable = {x["handle"] for x in previous} | {c["handle"]}
        alternatives = [
            x
            for x in result["ranking"]
            if x["handle"] not in unavailable
            and x["brand_safety"] != "FAIL"
            and x["combined_score"] is not None
        ]
        next_best = max(
            alternatives,
            key=lambda x: marginal_components(
                x, result["capability_priorities"], previous
            )["total"],
            default=None,
        )
        c["comparison"] = (
            None
            if next_best is None
            else {
                "alternative": next_best["handle"],
                "alternative_components": marginal_components(
                    next_best, result["capability_priorities"], previous
                ),
            }
        )
    result["validation"] = validate_run(result)
    return result


def validate_run(snapshot, human_ranking=None):
    ranking = snapshot["ranking"]
    eligible = [
        c
        for c in ranking
        if c["brand_safety"] != "FAIL" and c["combined_score"] is not None
    ]
    baseline = [c["handle"] for c in eligible]
    roster = {c["handle"] for c in snapshot["roster"]}
    sensitivity = []
    for d in DIMENSIONS:
        for factor in (0.9, 1.1):
            weights = dict(snapshot["weights"])
            weights[d] *= factor
            ranked = sorted(
                eligible,
                key=lambda c: (
                    -(
                        weighted_score(c, weights)
                        if weighted_score(c, weights) is not None
                        else -1
                    ),
                    c["handle"],
                ),
            )
            changed = [
                dict(c, combined_score=weighted_score(c, weights)) for c in ranked
            ]
            new_roster = {
                c["handle"]
                for c in select_roster(changed, snapshot["capability_priorities"])
            }
            sensitivity.append(
                {
                    "dimension": d,
                    "factor": factor,
                    "rho": spearman_rho(baseline, [c["handle"] for c in ranked]),
                    "roster_changes": sorted(roster ^ new_roster),
                }
            )
    replay_orders = [
        [
            c["handle"]
            for c in relative_scores(snapshot["evaluated"], snapshot["weights"])
        ]
        for _ in range(3)
    ]
    return {
        "deterministic_replay": {
            "runs": 3,
            "identical": all(r == replay_orders[0] for r in replay_orders),
            "max_rank_swing": (
                0 if all(r == replay_orders[0] for r in replay_orders) else None
            ),
        },
        "model_stability": {
            "status": "not_measured",
            "reason": "Replay does not repeat Gemini inference; use validate --repeat-model.",
        },
        "human_agreement": {
            "rho": spearman_rho(baseline, human_ranking) if human_ranking else None,
            "status": "measured" if human_ranking else "no_blind_ranking_supplied",
        },
        "sensitivity": sensitivity,
    }


def verify_snapshot(snapshot):
    if (
        snapshot["scoring_version"] != SCORING_VERSION
        or snapshot["prompt_version"] != PROMPT_VERSION
        or snapshot["code_version"] != code_version()
    ):
        raise ValueError(
            "Scoring/prompt/code version mismatch; original run remains intact. Create a new run."
        )
    current_hash = fingerprint(
        {
            "channels": snapshot["channels"],
            "evaluated": snapshot["evaluated"],
            "trends": snapshot["trend_snapshot"],
        }
    )
    if (
        snapshot["data_hash"] != current_hash
        or snapshot["campaign_fingerprint"]
        != Campaign(**snapshot["campaign"]).fingerprint()
    ):
        raise ValueError("Snapshot evidence or campaign was modified")


def revise(snapshot, weights=None, priorities=None, reset=False, swap=None):
    verify_snapshot(snapshot)
    result = deepcopy(snapshot)
    result["parent_run_id"] = snapshot["run_id"]
    result["run_id"] = str(uuid4())
    result["run_version"] += 1
    if reset:
        result["weights"], result["capability_priorities"] = (
            result["default_weights"],
            result["default_priorities"],
        )
    else:
        if weights is not None:
            result["weights"] = weights
        if priorities is not None:
            result["capability_priorities"] = priorities
    event = audit_controls(
        result["weights"],
        result["capability_priorities"],
        "reset" if reset else "strategist",
    )
    result["audit"].append(event)
    result = score_snapshot(result)
    if swap:
        # Preserve earlier manual swaps when making another swap.
        base = (
            snapshot["roster"]
            if weights is None and priorities is None and not reset
            else result["roster"]
        )
        result["roster"] = manual_swap(
            base, result["ranking"], *swap, result["capability_priorities"]
        )
        event["manual_swap"] = {"outgoing": swap[0], "incoming": swap[1]}
        result["audit"][-1] = event
        result = summarize(result)
    return result


def model_stability(snapshot, provider):
    """Three new judgments on identical frozen comments/metadata; no discovery or pull."""
    verify_snapshot(snapshot)
    campaign = Campaign(**snapshot["campaign"])
    source = {c["channel_id"]: c for c in snapshot["channels"]}
    rankings, evaluations = [], []
    for _ in range(3):
        batch = []
        for old in snapshot["evaluated"]:
            analysis = evaluate(
                source[old["channel_id"]],
                campaign,
                provider,
                snapshot["trend_snapshot"],
                snapshot["calibration"]["min_comments"],
            )
            item = deepcopy(old)
            item["dimensions"].update(analysis["dimensions"])
            item["brand_safety"] = analysis["brand_safety"]
            batch.append(item)
        rankings.append(
            [c["handle"] for c in relative_scores(batch, snapshot["weights"])]
        )
        evaluations.append(batch)
    positions = [{handle: i for i, handle in enumerate(order)} for order in rankings]
    return {
        "status": "measured",
        "runs": 3,
        "rankings": rankings,
        "correlations": [
            spearman_rho(rankings[i], rankings[j]) for i, j in ((0, 1), (0, 2), (1, 2))
        ],
        "max_rank_swing": max(
            (
                max(p.get(h, len(p)) for p in positions)
                - min(p.get(h, len(p)) for p in positions)
                for h in set().union(*(set(p) for p in positions))
            ),
            default=0,
        ),
        "evaluations": evaluations,
        "eligibility_changes": sorted(
            set().union(*(set(p) for p in positions))
            - set.intersection(*(set(p) for p in positions))
        ),
        "mode": provider.mode,
        "model": provider.model,
    }


def save(snapshot, root):
    directory = Path(root) / snapshot["run_id"]
    directory.mkdir(parents=True, exist_ok=False)
    with (directory / "audit.json").open("x", encoding="utf-8") as stream:
        json.dump(snapshot, stream, indent=2, ensure_ascii=False, allow_nan=False)
    return directory

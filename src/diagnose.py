"""Read-only diagnostics for saved audit.json files; no APIs or version gate."""

import argparse
import json
import math
from pathlib import Path
from statistics import median


def diagnose(snapshot):
    ranking = snapshot.get("ranking", [])
    roster = snapshot.get("roster", [])
    if not isinstance(ranking, list) or not isinstance(roster, list):
        raise ValueError("Snapshot ranking and roster must be lists")
    if not ranking:
        raise ValueError("Snapshot has no ranking to diagnose")
    eligible = [
        c
        for c in ranking
        if c.get("brand_safety") != "FAIL" and c.get("combined_score") is not None
    ]
    ranks = {c["handle"]: i for i, c in enumerate(eligible, 1)}
    handles = set(ranks)
    pairs = {}
    for c in eligible:
        for other, value in c.get("similarity", {}).items():
            if (
                other in handles
                and other != c["handle"]
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
            ):
                pairs.setdefault(tuple(sorted((c["handle"], other))), value)
    values = sorted(pairs.values())
    similarity = {
        "observed_pairs": len(values),
        "expected_pairs": len(eligible) * (len(eligible) - 1) // 2,
    }
    if values:
        similarity.update(
            min=min(values),
            median=median(values),
            max=max(values),
            spread=max(values) - min(values),
            fraction_above_0_7=sum(v > 0.7 for v in values) / len(values),
        )
    return {
        "run_id": snapshot.get("run_id"),
        "mode": snapshot.get("mode"),
        "scoring_version": snapshot.get("scoring_version"),
        "notice": "Read-only diagnostics; integrity and current-code compatibility are not verified. High similarity or a top-four roster is a finding, not automatically a bug.",
        "similarity": similarity,
        "roster_matches_top_four_in_order": [c["handle"] for c in roster]
        == [c["handle"] for c in eligible[:4]],
        "roster": [
            {
                "handle": c["handle"],
                "individual_rank": ranks.get(c["handle"]),
                "combined_score": c.get("combined_score"),
                "selection": c.get("marginal_components", {}),
            }
            for c in roster
        ],
        "missing_evidence": {
            c["handle"]: c.get("missing_dimensions", [])
            for c in ranking
            if c.get("missing_dimensions")
        },
        "safety": {
            c["handle"]: c.get("brand_safety", "unknown")
            for c in snapshot.get("evaluated", ranking)
        },
        "warnings": snapshot.get("warnings", []),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    args = parser.parse_args(argv)
    result = diagnose(json.loads(Path(args.snapshot).read_text(encoding="utf-8")))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

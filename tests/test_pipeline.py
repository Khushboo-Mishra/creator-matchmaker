import copy
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import pytest
import jsonschema

from src.campaign import (
    Campaign,
    CAPABILITIES,
    DIMENSIONS,
    default_priorities,
    default_weights,
    validate_controls,
)
from src.evaluation import evaluate, valid_trends
from src.pipeline import run, revise, save, verify_snapshot
from src.providers import DemoProvider
from src.ranking import marginal_components, relative_scores, manual_swap
from src.screening import discovery_relevance, screen
from src.matchmaker import main

AT = datetime(2026, 10, 26, tzinfo=timezone.utc)


@pytest.fixture
def campaign():
    return Campaign(**json.loads(Path("examples/campaign.json").read_text()))


@pytest.fixture
def snapshot(campaign):
    return run(campaign, DemoProvider(AT), AT)


def test_full_backend_produces_screening_evidence_roster_and_immutable_output(
    snapshot, tmp_path
):
    assert len(snapshot["channels"]) == 26
    jsonschema.validate(
        snapshot, json.loads(Path("schemas/run.schema.json").read_text())
    )
    channel_schema = json.loads(Path("schemas/channel.schema.json").read_text())
    for channel in snapshot["channels"]:
        jsonschema.validate(channel, channel_schema)
    assert len(snapshot["evaluated"]) == 20
    assert len(snapshot["roster"]) == 4
    assert (
        sum("specialist" in c["shortlist_reason"] for c in snapshot["evaluated"]) == 5
    )
    assert snapshot["screening"]["excluded"][0]["channel_id"] == "demo-25"
    assert all(c["brand_safety"] != "FAIL" for c in snapshot["roster"])
    assert all(
        c["dimensions"]["trend_fit"]["score"] is None for c in snapshot["ranking"]
    )
    for c in snapshot["evaluated"]:
        assert set(c["capabilities"]) == set(CAPABILITIES)
        assert c["dimensions"]["audience_relevance"]["counts"]["prefiltered"] <= 60
    directory = save(snapshot, tmp_path)
    verify_snapshot(json.loads((directory / "audit.json").read_text()))
    with pytest.raises(FileExistsError):
        save(snapshot, tmp_path)


def test_discovery_best_rank_once_per_query_capped_at_four():
    matches = [{"query": str(i), "rank": 1} for i in range(8)]
    matches.extend([{"query": "0", "rank": 2}] * 20)
    assert discovery_relevance(matches) == pytest.approx(4 / math.log(2))
    with pytest.raises(ValueError):
        discovery_relevance([{"query": "q", "rank": 0}])


def test_screening_health_mix_and_additive_blend(campaign):
    p = DemoProvider(AT)
    channels = [p.channel(c) for c in p.discover(campaign)["candidates"]]
    selected, audit = screen(channels, AT)
    for record in selected:
        n = record["normalized_health_components"]
        assert record["health"] == pytest.approx(
            0.4 * n["engagement"] + 0.4 * n["momentum"] + 0.2 * n["speed_to_activate"]
        )
    assert len(audit["eligible"]) == 25


def test_controls_independent_reset_and_data_hash_preserved(snapshot):
    weights = {d: float(d == "brand_fit") for d in DIMENSIONS}
    revision = revise(snapshot, weights=weights)
    assert revision["capability_priorities"] == snapshot["capability_priorities"]
    assert revision["data_hash"] == snapshot["data_hash"]
    assert revision["run_id"] != snapshot["run_id"]
    assert revision["audit"][-1]["weights"] == weights
    restored = revise(revision, reset=True)
    assert restored["weights"] == snapshot["default_weights"]
    assert snapshot["weights"] != weights


def test_tampering_and_code_version_changes_rejected(snapshot):
    altered = copy.deepcopy(snapshot)
    altered["channels"][0]["title"] = "tampered"
    with pytest.raises(ValueError, match="modified"):
        verify_snapshot(altered)
    snapshot["code_version"] = "different"
    with pytest.raises(ValueError, match="version mismatch"):
        revise(snapshot)


def test_relative_scores_missing_and_zero():
    cs = [
        {
            "handle": str(i),
            "dimensions": {
                d: {"score": None if d == "trend_fit" else float(i)} for d in DIMENSIONS
            },
        }
        for i in range(3)
    ]
    ranked = relative_scores(cs, default_weights())
    assert ranked[0]["combined_score"] == 10
    assert ranked[-1]["combined_score"] == 0
    assert ranked[0]["dimensions"]["trend_fit"]["score"] is None
    assert cs[2]["dimensions"]["engagement"]["score"] == 2


def test_roster_terms_use_common_scale_and_continuous_priorities():
    c = {
        "handle": "a",
        "combined_score": 10,
        "capabilities": dict.fromkeys(CAPABILITIES, 1),
        "similarity": {"b": 0.8},
    }
    p = dict.fromkeys(CAPABILITIES, 1)
    assert marginal_components(c, p, [])["total"] == pytest.approx(0.85)
    half = dict.fromkeys(CAPABILITIES, 0.5)
    assert marginal_components(c, half, [])["coverage_gain"] == 0.5
    other = dict(c, handle="b")
    assert marginal_components(c, p, [other])["total"] == pytest.approx(
        0.5 - 0.15 * 0.8
    )


def test_swap_rejects_fail_and_duplicates(snapshot):
    roster = snapshot["roster"]
    with pytest.raises(ValueError):
        manual_swap(
            roster,
            snapshot["ranking"],
            roster[0]["handle"],
            roster[1]["handle"],
            snapshot["capability_priorities"],
        )
    alternative = next(
        c
        for c in snapshot["ranking"]
        if c["brand_safety"] != "FAIL"
        and c["handle"] not in {x["handle"] for x in roster}
    )
    changed = revise(snapshot, swap=(roster[0]["handle"], alternative["handle"]))
    assert changed["roster"][0]["handle"] == alternative["handle"]
    assert changed["audit"][-1]["manual_swap"]["incoming"] == alternative["handle"]


def test_null_versus_measured_no_trend_match(campaign):
    provider = DemoProvider(AT)
    ch = provider.channel(provider.discover(campaign)["candidates"][0])
    ch["comment_records"] = provider.comments(ch)
    snapshot = {"source": "Google Trends", "fetched_at": AT.isoformat(), "trends": []}
    result = evaluate(ch, campaign, provider, snapshot)
    assert result["dimensions"]["trend_fit"]["score"] == 0
    assert result["dimensions"]["audience_relevance"]["score"] is None
    result = evaluate(ch, campaign, provider, None)
    assert result["dimensions"]["trend_fit"]["score"] is None


def test_fabricated_quotes_are_rejected(campaign):
    class BadProvider(DemoProvider):
        def judge(self, *args):
            result = super().judge(*args)
            result["audience"]["quotes"][0]["quote"] = "invented quotation"
            return result

    provider = BadProvider(AT)
    ch = provider.channel(provider.discover(campaign)["candidates"][1])
    ch["comment_records"] = provider.comments(ch)
    with pytest.raises(ValueError, match="not supported"):
        evaluate(ch, campaign, provider, None)


def test_invalid_trend_sources_not_accepted():
    with pytest.raises(ValueError):
        valid_trends(
            {"source": "Google Search", "fetched_at": AT.isoformat(), "trends": []}, AT
        )


def test_control_validation(campaign):
    with pytest.raises(ValueError):
        validate_controls(dict.fromkeys(DIMENSIONS, float("nan")), default_priorities())
    validate_controls(default_weights(), dict.fromkeys(CAPABILITIES, 0))
    with pytest.raises(ValueError):
        Campaign("", "awareness", "goal", "audience")


def test_cli_campaign_to_outputs_and_rescore(tmp_path, capsys):
    main(
        [
            "run",
            "--campaign",
            "examples/campaign.json",
            "--mode",
            "demo",
            "--no-pdf",
            "--out",
            str(tmp_path),
        ]
    )
    path = next(tmp_path.glob("*/audit.json"))
    original = path.read_bytes()
    main(
        [
            "rescore",
            "--snapshot",
            str(path),
            "--reset",
            "--no-pdf",
            "--out",
            str(tmp_path),
        ]
    )
    assert len(list(tmp_path.glob("*/audit.json"))) == 2
    assert path.read_bytes() == original
    assert "SYNTHETIC DEMO" in capsys.readouterr().out
    assert path.with_name("report.md").exists()

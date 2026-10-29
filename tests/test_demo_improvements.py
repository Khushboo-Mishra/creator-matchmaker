import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.export_web import web_payload, js_json, export
from src.campaign import Campaign, CAPABILITIES
from src.matchmaker import load_trends
from src.pipeline import run
from src.providers import DemoProvider
from src.evaluation import valid_trends
from src.ranking import marginal_components
from src.reports import write_reports


@pytest.fixture
def demo():
    campaign = Campaign(**json.loads(Path("examples/campaign.json").read_text()))
    at = datetime(2026, 10, 26, tzinfo=timezone.utc)
    return run(campaign, DemoProvider(at), at, trend_snapshot=load_trends(campaign, "demo"))


def test_demo_diversity_and_complementary_picks(demo):
    similarities = [v for c in demo["evaluated"] for v in c["similarity"].values()]
    assert min(similarities) < 0.2
    assert max(similarities) < 0.99
    ranks = {c["handle"]: i for i, c in enumerate(demo["ranking"], 1)}
    assert ranks[demo["roster"][0]["handle"]] == 1
    assert ranks[demo["roster"][1]["handle"]] > 2
    assert demo["roster"][1]["marginal_components"]["coverage_gain"] > 0
    assert all(
        c["dimensions"]["trend_fit"]["score"] is not None for c in demo["roster"]
    )
    assert any("synthetic fixtures" in w for w in demo["warnings"])


def test_coverage_normalization_and_zero_priorities():
    c = {
        "handle": "a",
        "combined_score": 8,
        "capabilities": dict.fromkeys(CAPABILITIES, 1),
    }
    other = {"handle": "b", "capabilities": dict.fromkeys(CAPABILITIES, 0.2)}
    p = dict.fromkeys(CAPABILITIES, 0.25)
    assert marginal_components(c, p, [other])["coverage_gain"] == pytest.approx(0.8)
    assert (
        marginal_components(c, dict.fromkeys(CAPABILITIES, 0), [other])["coverage_gain"]
        == 0
    )
    assert marginal_components(c, p, [])["selection_rule"] == "quality_anchor"


def test_synthetic_trends_rejected_outside_demo():
    trends = json.loads(Path("examples/trend_snapshot.json").read_text())
    with pytest.raises(ValueError):
        valid_trends(trends, datetime(2026, 10, 26, tzinfo=timezone.utc))


def test_export_saved_roster_and_safe_json(demo):
    data, metadata = web_payload(demo)
    assert [c["handle"] for c in metadata["roster"]] == [
        c["handle"] for c in demo["roster"]
    ]
    assert len(data) == len(demo["ranking"])
    assert "comment_records" not in json.dumps(data)
    assert "<" not in js_json("</script><img>")


def test_report_headings_and_grouped_quotes(demo, tmp_path):
    write_reports(demo, tmp_path, pdf=False)
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert report.startswith("# Creator Matchmaker")
    assert "### Brand Fit" in report
    assert report.count("### Supporting evidence") <= 4
    assert "\n- " in report
    assert "not directly comparable" in report
    assert "## How the team is chosen" in report


def test_live_mode_warning_and_file_export_with_mocked_provider(tmp_path):
    # Exercise live-mode plumbing, not real APIs or verified external measurements.
    class MockLiveProvider(DemoProvider):
        mode = "live"

    campaign = Campaign(**json.loads(Path("examples/campaign.json").read_text()))
    at = datetime(2026, 10, 26, tzinfo=timezone.utc)
    trends = {
        "source": "Google Trends",
        "fetched_at": at.isoformat(),
        "campaign_fingerprint": campaign.fingerprint(),
        "trends": [],
    }
    result = run(campaign, MockLiveProvider(at), at, trend_snapshot=trends)
    assert result["mode"] == "live"
    assert not any("synthetic" in w.lower() for w in result["warnings"])
    assert all(c["dimensions"]["trend_fit"]["score"] is not None for c in result["roster"])
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps(result), encoding="utf-8")
    output = tmp_path / "data.js"
    export(audit, output)
    metadata = json.loads(output.read_text(encoding="utf-8").split("const RUN = ")[1].rstrip(";\n"))
    assert metadata["mode"] == "live"
    assert metadata["warnings"] == result["warnings"]
    assert [c["handle"] for c in metadata["roster"]] == [c["handle"] for c in result["roster"]]

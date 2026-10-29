import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.campaign import Campaign
from src.discover import main as discover_main
from src.discovery_file import validate_discovery
from src.diagnose import diagnose, main as diagnose_main
from src.pipeline import run
from src.providers import DemoProvider


@pytest.fixture
def inputs():
    campaign = Campaign(**json.loads(Path("examples/campaign.json").read_text()))
    at = datetime(2026, 10, 26, tzinfo=timezone.utc)
    data = DemoProvider(at).discover(campaign)
    data["campaign_fingerprint"] = campaign.fingerprint()
    return campaign, at, data


def test_standalone_file_round_trip_bypasses_discovery(inputs, monkeypatch, tmp_path):
    campaign, at, data = inputs

    def discover(**kwargs):
        assert kwargs["campaign"].fingerprint() == campaign.fingerprint()
        return copy.deepcopy(data)

    monkeypatch.setattr("src.discover.discover_candidates", discover)
    output = tmp_path / "discovery.json"
    discover_main(["--campaign", "examples/campaign.json", "--output", str(output)])
    provider = DemoProvider(at)

    def forbidden(*args):
        raise AssertionError("Discovery must not be called")

    monkeypatch.setattr(provider, "discover", forbidden)
    result = run(
        campaign, provider, at, discovery_snapshot=json.loads(output.read_text())
    )
    assert result["discovery"]["candidates"] == data["candidates"]
    assert len(result["roster"]) == 4


@pytest.mark.parametrize("corruption", ["fingerprint", "rank", "query", "empty"])
def test_invalid_discovery_rejected_before_pull(inputs, monkeypatch, corruption):
    campaign, at, data = inputs
    if corruption == "fingerprint":
        data["campaign_fingerprint"] = "wrong"
    elif corruption == "rank":
        data["candidates"][0]["matches"][0]["rank"] = True
    elif corruption == "query":
        data["candidates"][0]["matches"][0]["query"] = "unknown"
    else:
        data["candidates"] = []
    provider = DemoProvider(at)
    monkeypatch.setattr(provider, "channel", lambda c: pytest.fail("No pulls allowed"))
    with pytest.raises(ValueError):
        run(campaign, provider, at, discovery_snapshot=data)


def test_diagnose_old_snapshot_read_only(inputs, tmp_path, capsys):
    campaign, at, _ = inputs
    snapshot = run(campaign, DemoProvider(at), at)
    snapshot["code_version"] = "old"
    path = tmp_path / "audit.json"
    path.write_text(json.dumps(snapshot))
    before = path.read_bytes()
    diagnose_main(["--snapshot", str(path)])
    result = json.loads(capsys.readouterr().out)
    assert (
        result["similarity"]["observed_pairs"] == result["similarity"]["expected_pairs"]
    )
    assert result["roster"][0]["individual_rank"] == 1
    assert path.read_bytes() == before


def test_diagnose_missing_similarity_is_not_zero():
    c = {"handle": "a", "combined_score": 1}
    result = diagnose({"ranking": [c], "roster": [c]})
    assert "min" not in result["similarity"]
    assert result["roster_matches_top_four_in_order"]

from src.campaign import Campaign, default_weights, audit_controls
from src.ranking import weighted_score, select_roster
from src.snapshot import freeze


def dim(**values):
    return {k: {"score": v} for k, v in values.items()}


def channel(handle, **values):
    return {"handle": handle, "dimensions": dim(**values), "brand_safety": "PASS"}


def test_missing_dimensions_are_renormalized():
    c = channel("@a", engagement=10)
    weights = {
        d: 1
        for d in (
            "audience_relevance",
            "engagement",
            "brand_fit",
            "momentum",
            "speed_to_activate",
            "trend_fit",
        )
    }
    assert weighted_score(c, weights) == 10


def test_roster_covers_capabilities():
    p = {"reach": 1, "demonstration": 1, "credibility": 1, "speed": 1}
    cs = [
        {"handle": "a", "combined_score": 9, "capabilities": ["reach"]},
        {"handle": "b", "combined_score": 8, "capabilities": ["demonstration"]},
        {"handle": "c", "combined_score": 7, "capabilities": ["credibility"]},
        {"handle": "d", "combined_score": 6, "capabilities": ["speed"]},
    ]
    assert {x for c in select_roster(cs, p, 4) for x in c["capabilities"]} == set(p)


def test_snapshot_freezes_versions_and_inputs(tmp_path):
    campaign = Campaign(
        "product", "awareness", "goal", "audience", {"banned_phrases": ["guaranteed"]}
    )
    snapshot = freeze(
        tmp_path / "run.json",
        campaign,
        default_weights(),
        {k: 1 for k in ("reach", "demonstration", "credibility", "speed")},
        [],
    )
    assert snapshot["campaign_fingerprint"] == campaign.fingerprint()
    assert (tmp_path / "run.json").exists()


def test_controls_are_audited():
    event = audit_controls(
        default_weights(),
        {k: 1 for k in ("reach", "demonstration", "credibility", "speed")},
    )
    assert event["actor"] == "system"

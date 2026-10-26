from src.campaign import Campaign, default_weights, audit_controls
from src.ranking import creator_health, weighted_score, shortlist, select_roster
from src.snapshot import freeze

def dim(**values):
    return {k: {"score": v} for k, v in values.items()}

def channel(handle, **values):
    return {"handle": handle, "dimensions": dim(**values), "brand_safety": "PASS"}

def test_creator_health_locked_mix():
    c = channel("@a", engagement=10, momentum=5, speed_to_activate=0)
    assert creator_health(c) == 6.0

def test_missing_dimensions_are_renormalized():
    c = channel("@a", engagement=10)
    weights = {d: 1 for d in ("audience_relevance", "engagement", "brand_fit", "momentum", "speed_to_activate", "trend_fit")}
    assert weighted_score(c, weights) == 10

def test_shortlist_top_plus_specialists():
    base = dict(audience_relevance=5, engagement=8, brand_fit=5, momentum=8, speed_to_activate=5, trend_fit=5)
    result = shortlist([channel("@" + str(i), **base) for i in range(22)], {d: 1 for d in base}, top_n=3, specialist_n=2)
    assert len(result) == 5

def test_roster_covers_capabilities():
    p = {"audience_relevance": 1, "brand_fit": 1, "trend_fit": 1, "speed_to_activate": 1}
    cs = [{"handle": "a", "combined_score": 9, "capabilities": ["audience_relevance"]}, {"handle": "b", "combined_score": 8, "capabilities": ["brand_fit"]}, {"handle": "c", "combined_score": 7, "capabilities": ["trend_fit"]}, {"handle": "d", "combined_score": 6, "capabilities": ["speed_to_activate"]}]
    assert {x for c in select_roster(cs, p, 4) for x in c["capabilities"]} == set(p)

def test_snapshot_freezes_versions_and_inputs(tmp_path):
    campaign = Campaign("product", "awareness", "goal", "audience", {"banned_phrases": ["guaranteed"]})
    snapshot = freeze(tmp_path / "run.json", campaign, default_weights(), {k: 1 for k in ("audience_relevance", "brand_fit", "trend_fit", "speed_to_activate")}, [])
    assert snapshot["campaign_fingerprint"] == campaign.fingerprint()
    assert (tmp_path / "run.json").exists()

def test_controls_are_audited():
    event = audit_controls(default_weights(), {k: 1 for k in ("audience_relevance", "brand_fit", "trend_fit", "speed_to_activate")})
    assert event["actor"] == "system"

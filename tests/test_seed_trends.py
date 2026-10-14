"""The offline trend snapshot has to be indistinguishable to score_ai, and
distinguishable to a human reading the file. No network, no key.
"""
import json

import pytest

from src import score_ai, seed_trends

RULES = "# Campaign\nSome rules text.\n"


@pytest.fixture(autouse=True)
def snapshot_in_tmp(tmp_path, monkeypatch):
    path = tmp_path / "trend_snapshot.json"
    monkeypatch.setattr(score_ai, "TREND_CACHE_FILE", path)
    monkeypatch.setattr(seed_trends, "TREND_CACHE_FILE", path)
    score_ai.ground_trend_topics.cache_clear()
    return path


def test_seeded_snapshot_is_accepted_by_score_ai(snapshot_in_tmp):
    """The whole point: no Google call happens after seeding."""
    seed_trends.seed("Rising: moodboard workflows", ["https://example.com/a"], RULES)
    context, citations = score_ai.ground_trend_topics(RULES)
    assert context == "Rising: moodboard workflows"
    assert citations == ["https://example.com/a"]


def test_seeding_does_not_call_the_api(snapshot_in_tmp, monkeypatch):
    def explode(*a, **k):
        raise AssertionError("seed_trends must never hit the network")

    monkeypatch.setattr(score_ai, "_fetch_grounded_trends", explode)
    seed_trends.seed("text", [], RULES)
    score_ai.ground_trend_topics(RULES)


def test_provenance_is_recorded_so_the_writeup_can_be_honest(snapshot_in_tmp):
    seed_trends.seed("text", [], RULES)
    assert json.loads(snapshot_in_tmp.read_text())["source"] == "manual"


def test_a_snapshot_for_different_rules_is_rejected(snapshot_in_tmp):
    """Stale-rules detection must still work on a manual snapshot."""
    seed_trends.seed("text", [], RULES)
    assert score_ai._read_trend_snapshot("# Different rules\n") is None


def test_empty_text_is_refused(snapshot_in_tmp):
    with pytest.raises(ValueError):
        seed_trends.seed("   \n ", [], RULES)
    assert not snapshot_in_tmp.exists()

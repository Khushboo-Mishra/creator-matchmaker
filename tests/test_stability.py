"""Tests for the reproducibility script, with the network mocked out.

The key behavior under test: grounding is cached per rules_text (see
score_ai.ground_trend_topics), so scoring the same channel RUNS times should
hit the search endpoint once and the scoring endpoint RUNS times, not both
RUNS times -- that's the point of caching trends once per run.

Run: python -m pytest
"""
import json

import pytest

from src import score_ai, stability


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._payload


def channel_record(**overrides):
    base = {
        "handle": "@studio",
        "title": "Studio Channel",
        "subscribers": 10000,
        "videos": [{"video_id": "v1", "title": "A video", "description": "A description."}],
        "sampled_comments": ["a real comment"],
    }
    base.update(overrides)
    return base


def scoring_payload(score=5):
    body = {
        "audience_relevance": {"score": score, "reason": "r", "evidence": []},
        "brand_fit": {"score": score, "reason": "r", "evidence": []},
        "trend_fit": {"score": score, "reason": "r", "evidence": []},
        "hard_stop": False,
    }
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(body)}]}}]}


GROUNDING_PAYLOAD = {
    "candidates": [{
        "content": {"parts": [{"text": "rising topic"}]},
        "groundingMetadata": {"groundingChunks": [{"web": {"uri": "https://example.com"}}]},
    }]
}


@pytest.fixture(autouse=True)
def isolated_trend_cache(tmp_path, monkeypatch):
    """The cache now lives on disk so it survives across processes; give each
    test its own throwaway file instead of sharing the real one.
    """
    monkeypatch.setattr(score_ai, "TREND_CACHE_FILE", tmp_path / "trend_cache.json")


class TestGroundingIsCachedAcrossRuns:
    def test_stability_grounds_once_and_scores_runs_times(self, monkeypatch):
        counts = {"grounding": 0, "scoring": 0}

        def fake_post(**kwargs):
            if "tools" in kwargs["json"]:
                counts["grounding"] += 1
                return FakeResponse(200, GROUNDING_PAYLOAD)
            counts["scoring"] += 1
            return FakeResponse(200, scoring_payload())

        monkeypatch.setattr(score_ai.requests, "post", fake_post)
        stability.score_channel(channel_record(), rules_text="rules")

        assert counts["grounding"] == 1
        assert counts["scoring"] == stability.RUNS

    def test_spread_is_zero_when_the_model_returns_the_same_score_each_time(self, monkeypatch):
        def fake_post(**kwargs):
            if "tools" in kwargs["json"]:
                return FakeResponse(200, GROUNDING_PAYLOAD)
            return FakeResponse(200, scoring_payload(score=7))

        monkeypatch.setattr(score_ai.requests, "post", fake_post)
        per_dim = stability.score_channel(channel_record(), rules_text="rules")

        for values in per_dim.values():
            assert stability._spread(values) == 0.0

    def test_grounding_is_logged_once_then_silent_on_cache_hits(self, monkeypatch, capsys):
        """grep -c "grounding trends" is how the live check counts real search calls."""
        monkeypatch.setattr(score_ai.requests, "post", lambda **kw: FakeResponse(
            200, GROUNDING_PAYLOAD if "tools" in kw["json"] else scoring_payload()
        ))

        stability.score_channel(channel_record(), rules_text="rules")

        assert capsys.readouterr().out.count("grounding trends") == 1

    def test_cache_survives_a_fresh_process_reusing_the_same_file(self, monkeypatch, capsys):
        """A later, separate process pointed at the same cache file must not re-ground."""
        monkeypatch.setattr(score_ai.requests, "post", lambda **kw: FakeResponse(
            200, GROUNDING_PAYLOAD if "tools" in kw["json"] else scoring_payload()
        ))

        score_ai.ground_trend_topics("rules")
        capsys.readouterr()  # discard the first run's output

        score_ai.ground_trend_topics("rules")
        assert "grounding trends" not in capsys.readouterr().out


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))

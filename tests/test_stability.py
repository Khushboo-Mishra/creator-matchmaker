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
        "trend_fit": {"score": score, "reason": "r", "evidence": []}
    }
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(body)}]}}]}


GROUNDING_PAYLOAD = {
    "candidates": [{
        "content": {"parts": [{"text": "rising topic"}]},
        "groundingMetadata": {"groundingChunks": [{"web": {"uri": "https://example.com"}}]},
    }]
}


@pytest.fixture(autouse=True)
def clear_trend_cache():
    """The cache is shared across tests, so start and end each test empty."""
    score_ai.ground_trend_topics.cache_clear()
    yield
    score_ai.ground_trend_topics.cache_clear()


class TestGroundingIsCachedAcrossRuns:
    def test_stability_grounds_once_and_scores_runs_times(self, monkeypatch):
        counts = {"grounding": 0, "scoring": 0}
        monkeypatch.setattr(score_ai, "audience_similarity", lambda record, rules: None)

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
        monkeypatch.setattr(score_ai, "audience_similarity", lambda record, rules: None)
        def fake_post(**kwargs):
            if "tools" in kwargs["json"]:
                return FakeResponse(200, GROUNDING_PAYLOAD)
            return FakeResponse(200, scoring_payload(score=7))

        monkeypatch.setattr(score_ai.requests, "post", fake_post)
        per_dim = stability.score_channel(channel_record(), rules_text="rules")

        for values in per_dim.values():
            assert stability._spread(values) == 0.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))

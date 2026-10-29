from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from src.campaign import Campaign
from src.evaluation import evaluate
from src.pipeline import run, model_stability
from src.providers import DemoProvider, LiveProvider
from src import providers, trends

AT = datetime(2026, 10, 26, tzinfo=timezone.utc)


def campaign():
    return Campaign(**json.loads(Path("examples/campaign.json").read_text()))


def test_verified_csv_import_retains_series_and_hash(tmp_path):
    (tmp_path / "rise.csv").write_text(
        "Category: All categories\n\nWeek,planning: (United States)\n2026-09-01,10\n2026-09-08,20\n2026-09-15,40\n2026-09-22,60\n"
    )
    manifest = {
        "campaign_fingerprint": campaign().fingerprint(),
        "exports": [
            {
                "topic": "planning",
                "file": "rise.csv",
                "source_url": "https://trends.google.com/trends/explore?q=planning",
                "geo": "US",
                "window": "2026-09",
            }
        ],
    }
    snapshot = trends.import_exports(manifest, tmp_path)
    assert snapshot["trends"][0]["previous_interest"] == 15
    assert snapshot["trends"][0]["recent_interest"] == 50
    assert len(snapshot["trends"][0]["export_sha256"]) == 64
    assert len(snapshot["checked_topics"][0]["series"]) == 4


def test_low_audience_is_not_null_with_sufficient_evidence():
    class NoMatch(DemoProvider):
        def judge(self, *args):
            result = super().judge(*args)
            result["audience"] = {
                "score": 0,
                "reason": "No relevant interests observed",
                "quotes": [],
            }
            return result

    p = NoMatch(AT)
    ch = p.channel(p.discover(campaign())["candidates"][1])
    ch["comment_records"] = p.comments(ch)
    result = evaluate(ch, campaign(), p, None)
    assert result["dimensions"]["audience_relevance"]["score"] == 0


def test_literal_requirement_flag_remains_review():
    c = campaign()
    c.brand_requirements["banned_phrases"] = ["moodboarding"]
    p = DemoProvider(AT)
    ch = p.channel(p.discover(c)["candidates"][1])
    ch["comment_records"] = p.comments(ch)
    result = evaluate(ch, c, p, None)
    assert result["brand_safety"] == "REVIEW"
    assert result["safety_flags"]


def test_model_stability_repeats_judgments_without_collecting():
    snapshot = run(campaign(), DemoProvider(AT), AT)

    class FrozenOnly(DemoProvider):
        def discover(self, *_):
            raise AssertionError("No rediscovery allowed")

        def channel(self, *_):
            raise AssertionError("No repull allowed")

        def comments(self, *_):
            raise AssertionError("No resampling allowed")

    result = model_stability(snapshot, FrozenOnly(AT))
    assert result["runs"] == 3
    assert result["correlations"] == [1, 1, 1]
    assert result["max_rank_swing"] == 0
    assert len(result["evaluations"]) == 3


def test_live_provider_key_check(monkeypatch):
    monkeypatch.setattr(providers, "GEMINI_API_KEY", None)
    with pytest.raises(ValueError, match="requires"):
        LiveProvider()


def test_live_judge_uses_supplied_campaign_and_json(monkeypatch):
    monkeypatch.setattr(providers, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(providers, "YOUTUBE_API_KEY", "test-key")
    seen = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "candidates": [{"content": {"parts": [{"text": '{"audience": {}}'}]}}]
            }

    def post(**kwargs):
        seen.append(kwargs)
        return Response()

    monkeypatch.setattr(providers.score_ai, "_post_with_retry", post)
    p = LiveProvider()
    p.judge(campaign(), [], [], None)
    assert "Milanote" in seen[0]["json"]["contents"][0]["parts"][0]["text"]
    assert seen[0]["json"]["generationConfig"]["responseMimeType"] == "application/json"


def test_prefilter_caps_comments_and_keeps_source_ids():
    from src.evaluation import prefilter

    comments = [
        {"comment_id": str(i), "video_id": "v", "text": f"planning {i}"}
        for i in range(90)
    ]
    selected = prefilter(comments, "planning", DemoProvider(AT).embed)
    assert len(selected) == 60
    assert all(c["comment_id"] in {x["comment_id"] for x in comments} for c in selected)

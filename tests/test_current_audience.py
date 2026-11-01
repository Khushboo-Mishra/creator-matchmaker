from copy import deepcopy
import inspect

import pytest

from src import providers
from src.providers import LiveProvider
from src.reports import audience_summary


@pytest.mark.parametrize("count", [0, 2, 15, 50])
def test_comments_select_top_three_only_within_recent_fifteen(monkeypatch, count):
    monkeypatch.setattr(providers, "GEMINI_API_KEY", "test")
    monkeypatch.setattr(providers, "YOUTUBE_API_KEY", "test")
    channel = {"videos": [{"video_id": str(i), "views": i * 100} for i in range(count)]}
    original = deepcopy(channel)
    calls = []

    def get(endpoint, **kwargs):
        calls.append(kwargs["videoId"])
        return {
            "items": [
                {
                    "snippet": {
                        "topLevelComment": {
                            "id": "comment-" + kwargs["videoId"],
                            "snippet": {"textDisplay": "planning"},
                        }
                    }
                }
            ]
        }

    monkeypatch.setattr(providers.pull, "_get", get)
    comments = LiveProvider().comments(channel)
    assert calls == [str(i) for i in reversed(range(min(count, 15)))][:3]
    assert {c["video_id"] for c in comments} <= {
        v["video_id"] for v in channel["videos"][:15]
    }
    assert channel == original


def test_report_does_not_repeat_demographic_model_claims():
    evidence = {
        "score": 0.8,
        "reason": "The audience consists of professional designers aged 25-34",
        "counts": {"usable": 40},
        "evidence": [{"quote": "I am a designer"}],
    }
    original = deepcopy(evidence)
    text = audience_summary(evidence)
    assert "8.0/10" in text
    assert "25-34" not in text
    assert "unverified individual statement" in text
    assert "whole audience" in text
    assert evidence == original
    evidence["score"] = None
    assert "Not enough" in audience_summary(evidence)


def test_prompt_explicitly_limits_population_claims():
    prompt_source = inspect.getsource(LiveProvider.judge)
    assert "not the whole audience" in prompt_source
    assert "unverified individual statement" in prompt_source


def test_historical_migration_rejects_changed_sampling(tmp_path):
    from src.migrate_checkpoint import migrate

    with pytest.raises(ValueError, match="Collection method changed: comments"):
        migrate(tmp_path / "old", tmp_path / "new", {})
    assert not (tmp_path / "new").exists()

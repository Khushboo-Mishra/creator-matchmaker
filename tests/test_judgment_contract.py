import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from src.campaign import Campaign
from src.evaluation import evaluate
from src.providers import DemoProvider, LiveProvider
from src.judgment_contract import JUDGMENT_SCHEMA, validate_judgment
from src import providers, failure_diagnostics


@pytest.fixture
def context():
    campaign = Campaign(**json.loads(Path("examples/campaign.json").read_text()))
    provider = DemoProvider(datetime(2026, 10, 26, tzinfo=timezone.utc))
    channel = provider.channel(provider.discover(campaign)["candidates"][1])
    channel["comment_records"] = provider.comments(channel)
    metadata = [
        {"video_id": v["video_id"], "text": v["title"] + " " + v["description"]}
        for v in channel["videos"][:15]
    ]
    result = provider.judge(campaign, metadata, channel["comment_records"], None)
    return campaign, provider, channel, result


@pytest.mark.parametrize(
    "value", [8, -0.1, "0.8", None, True, float("nan"), float("inf")]
)
def test_invalid_unit_reports_field_and_creator_and_saves(
    context, tmp_path, monkeypatch, value
):
    campaign, provider, channel, result = context
    provider.mode = "live"
    result["audience"]["score"] = value
    monkeypatch.setattr(provider, "judge", lambda *args: result)
    monkeypatch.setattr(failure_diagnostics, "DATA", tmp_path)
    with pytest.raises(
        ValueError, match=r"Creator @demo1: judgment.audience.score"
    ) as error:
        evaluate(channel, campaign, provider, None)
    assert "Private diagnostics saved:" in str(error.value)
    artifact = json.loads(next((tmp_path / "diagnostics").glob("*.json")).read_text())
    assert artifact["channel"]["channel_id"] == channel["channel_id"]
    assert artifact["kind"] == "failed_evaluation_not_resumable"
    assert "judgment" in artifact


def test_contract_all_score_fields_and_boundaries(context):
    *_, result = context
    Draft202012Validator.check_schema(JUDGMENT_SCHEMA)
    for section, key in [
        ("audience", "score"),
        ("brand_fit", "score"),
        ("capabilities", "expertise"),
    ]:
        original = result[section][key]
        for value in (0, 1):
            result[section][key] = value
            validate_judgment(result)
        result[section][key] = 9
        with pytest.raises(ValueError, match=section + "." + key):
            validate_judgment(result)
        result[section][key] = original
    result["trend_matches"] = [
        {
            "topic": "x",
            "campaign_relevance": 0.8,
            "creator_proximity": 2,
            "video_ids": ["v"],
        }
    ]
    with pytest.raises(ValueError, match=r"trend_matches\[0\].creator_proximity"):
        validate_judgment(result)


def test_missing_fields_and_shapes(context):
    *_, result = context
    del result["audience"]["score"]
    with pytest.raises(ValueError, match="required"):
        validate_judgment(result)
    with pytest.raises(ValueError):
        validate_judgment([])


def test_diagnostic_write_error_preserves_original_failure(context, monkeypatch):
    campaign, provider, channel, result = context
    provider.mode = "live"
    result["brand_fit"]["score"] = 10
    monkeypatch.setattr(provider, "judge", lambda *args: result)

    def unavailable(*args):
        raise OSError("disk unavailable")

    monkeypatch.setattr(failure_diagnostics, "save_failure", unavailable)
    with pytest.raises(
        ValueError, match="brand_fit.score.*Diagnostics could not be saved"
    ):
        evaluate(channel, campaign, provider, None)


@pytest.mark.parametrize(
    "text,finish", [("not JSON", "STOP"), ('{"partial":', "MAX_TOKENS")]
)
def test_live_raw_failure_saved_without_headers(
    context, tmp_path, monkeypatch, text, finish
):
    campaign, demo, channel, _ = context
    monkeypatch.setattr(providers, "GEMINI_API_KEY", "secret-test-key")
    monkeypatch.setattr(providers, "YOUTUBE_API_KEY", "secret-test-key")
    monkeypatch.setattr(failure_diagnostics, "DATA", tmp_path)

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "candidates": [
                    {"finishReason": finish, "content": {"parts": [{"text": text}]}}
                ]
            }

    calls = []

    def post(**kwargs):
        calls.append(kwargs)
        return Response()

    monkeypatch.setattr(providers.score_ai, "_post_with_retry", post)
    provider = LiveProvider()
    monkeypatch.setattr(provider, "embed", demo.embed)
    with pytest.raises(ValueError, match="Creator @demo1: judgment response"):
        evaluate(channel, campaign, provider, None)
    assert len(calls) == 1  # No hidden paid repair loop.
    assert calls[0]["json"]["generationConfig"]["responseJsonSchema"] == JUDGMENT_SCHEMA
    saved = next((tmp_path / "diagnostics").glob("*.json")).read_text()
    assert "secret-test-key" not in saved
    assert json.loads(saved)["response_text"] == text


def test_valid_evaluation_does_not_write_diagnostics(context, tmp_path, monkeypatch):
    campaign, provider, channel, _ = context
    provider.mode = "live"
    monkeypatch.setattr(failure_diagnostics, "DATA", tmp_path)
    evaluate(channel, campaign, provider, None)
    assert not (tmp_path / "diagnostics").exists()

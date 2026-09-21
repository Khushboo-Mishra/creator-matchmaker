"""Tests for the deterministic policy gate, with hand-made channel fixtures.

These catch what a judge would notice first: false positives on a clean
channel matter as much as catching a bad one.

Run: python -m pytest
"""
import json
from pathlib import Path

import pytest

from src import policy

FIXTURES = Path(__file__).parent / "fixtures"
RULES_TEXT = (Path(__file__).parent.parent / "config" / "rules.md").read_text()


def load(name):
    return json.loads((FIXTURES / name).read_text())


class TestEvaluate:
    def test_clean_channel_is_not_hard_stopped_or_warned(self):
        """False positives matter as much as catching bad channels."""
        result = policy.evaluate(load("clean_channel.json"), RULES_TEXT)
        assert result["hard_stop"] is False
        assert result["hard_stop_reason"] is None
        assert result["warnings"] == []

    def test_banned_claim_wording_is_a_warning_not_a_hard_stop(self):
        """A word-overlap match is a judgement call, not proof; it can't disqualify on its own."""
        result = policy.evaluate(load("banned_claim_channel.json"), RULES_TEXT)
        assert result["hard_stop"] is False
        assert any("guarantees" in w.lower() for w in result["warnings"])

    def test_sponsorship_mention_is_a_warning_not_a_hard_stop(self):
        """We can't confirm a spoken disclosure from text, so this is a warning, not a stop."""
        result = policy.evaluate(load("missing_disclosure_channel.json"), RULES_TEXT)
        assert result["hard_stop"] is False
        assert any("spoken disclosure" in w for w in result["warnings"])

    def test_mostly_emoji_or_generic_comments_is_a_hard_stop_with_evidence(self):
        result = policy.evaluate(load("fake_engagement_channel.json"), RULES_TEXT)
        assert result["hard_stop"] is True
        assert "emoji-only or generic" in result["hard_stop_reason"]

    def test_competitor_mention_is_a_hard_stop_with_evidence(self):
        rules_with_competitors = RULES_TEXT + "\n## Competitors\n\n- RivalBoard\n"
        record = {
            "videos": [{"video_id": "v1", "title": "Why I switched from RivalBoard", "description": ""}],
            "sampled_comments": ["great comparison", "this helped me decide"],
        }
        result = policy.evaluate(record, rules_with_competitors)
        assert result["hard_stop"] is True
        assert "rivalboard" in result["hard_stop_reason"].lower()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))

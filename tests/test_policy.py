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
    def test_clean_channel_is_not_hard_stopped(self):
        """False positives matter as much as catching bad channels."""
        result = policy.evaluate(load("clean_channel.json"), RULES_TEXT)
        assert result["hard_stop"] is False
        assert result["hard_stop_reason"] is None

    def test_banned_claim_in_a_title_stops_and_names_the_claim(self):
        result = policy.evaluate(load("banned_claim_channel.json"), RULES_TEXT)
        assert result["hard_stop"] is True
        assert "reversing signs of ageing" in result["hard_stop_reason"]

    def test_sponsored_description_without_hashtag_ad_stops(self):
        result = policy.evaluate(load("missing_disclosure_channel.json"), RULES_TEXT)
        assert result["hard_stop"] is True
        assert "#ad" in result["hard_stop_reason"]

    def test_mostly_emoji_or_generic_comments_flag_fake_engagement(self):
        result = policy.evaluate(load("fake_engagement_channel.json"), RULES_TEXT)
        assert result["hard_stop"] is True
        assert "emoji-only or generic" in result["hard_stop_reason"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))

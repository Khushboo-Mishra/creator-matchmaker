"""Tests for the three dimensions that need no model.

These exist because the arithmetic is the half of the scoring we promise is
explainable. If a number here is wrong, the reason string beside it is a
confident lie, which is worse than no score at all.

Run: python -m pytest
"""
from datetime import datetime, timedelta, timezone

import pytest

from src import arithmetic
from src.arithmetic import engagement, momentum, speed_to_activate

NOW = datetime.now(timezone.utc)


def video(views=10000, likes=500, comments=50, days_ago=1):
    return {
        "video_id": f"v{days_ago}",
        "title": "t",
        "published_at": (NOW - timedelta(days=days_ago)).isoformat().replace(
            "+00:00", "Z"
        ),
        "views": views,
        "likes": likes,
        "comments": comments,
    }


def channel(count, gap_days=3, **kw):
    """Newest first, the order pull.py writes and arithmetic.py assumes."""
    return [video(days_ago=1 + i * gap_days, **kw) for i in range(count)]


class TestEngagement:
    def test_anchor_scores_ten(self):
        # (likes + comments) / views == 0.08, the anchor
        score, _ = engagement(channel(15, views=10000, likes=750, comments=50))
        assert score == 10.0

    def test_above_anchor_is_clamped_not_overflowed(self):
        score, _ = engagement(channel(15, views=1000, likes=900, comments=100))
        assert score == 10.0

    def test_reads_only_the_rate_window(self):
        """A deeper cache must not move the number. This is why the window is fixed."""
        fifteen = channel(15, views=10000, likes=500, comments=50)
        fifty = fifteen + channel(35, views=10, likes=10, comments=10)
        assert engagement(fifteen)[0] == engagement(fifty)[0]

    def test_zero_view_videos_are_skipped_not_divided_by(self):
        videos = channel(14) + [video(views=0, likes=0, comments=0, days_ago=99)]
        score, reason = engagement(videos)
        assert score > 0
        assert "14 uploads" in reason

    def test_no_videos_is_not_measurable_rather_than_zero(self):
        score, reason = engagement([])
        assert score is None
        assert "not measurable" in reason


class TestMomentum:
    def test_rising_channel_scores_above_flat(self):
        flat = channel(15, views=10000)
        rising = [video(views=30000, days_ago=1 + i) for i in range(5)] + [
            video(views=10000, days_ago=10 + i) for i in range(10)
        ]
        assert momentum(rising)[0] > momentum(flat)[0]

    def test_median_not_mean_so_one_viral_video_cannot_rescue_a_dead_channel(self):
        """The whole reason the module uses medians. Guard it."""
        dead = [video(views=100, days_ago=1 + i) for i in range(15)]
        one_hit = [video(views=10_000_000, days_ago=1)] + [
            video(views=100, days_ago=2 + i) for i in range(14)
        ]
        assert momentum(one_hit)[0] == momentum(dead)[0]

    def test_short_channel_is_not_measurable_not_zero(self):
        """Zero means measured and fading. Nine uploads means we cannot tell."""
        score, reason = momentum(channel(9))
        assert score is None
        assert "not measurable" in reason

    def test_zero_prior_views_does_not_divide_by_zero(self):
        videos = [video(views=1000, days_ago=1 + i) for i in range(5)] + [
            video(views=0, days_ago=10 + i) for i in range(10)
        ]
        score, reason = momentum(videos)
        assert score is None
        assert "not measurable" in reason


class TestSpeedToActivate:
    def test_reads_the_whole_cache_not_the_rate_window(self):
        """The bug this dimension had: capped at 15, it could never reach its anchor."""
        daily = channel(50, gap_days=1)
        score, reason = speed_to_activate(daily)
        assert score == 10.0
        assert "50 uploads" in reason

    def test_frequent_and_infrequent_posters_separate(self):
        assert (
            speed_to_activate(channel(50, gap_days=3))[0]
            > speed_to_activate(channel(50, gap_days=30))[0]
        )

    def test_only_counts_the_last_90_days(self):
        old = [video(days_ago=200 + i) for i in range(20)]
        score, reason = speed_to_activate(old)
        assert score == 0.0
        assert "0 uploads" in reason


class TestComputeContract:
    """build_scores.py and scores.schema.json both depend on this shape."""

    def test_every_dimension_carries_score_reason_and_source(self):
        out = arithmetic.compute({"videos": channel(15)})
        assert set(out) == set(arithmetic_dimensions())
        for name, dim in out.items():
            assert 0 <= dim["score"] <= 10, name
            assert dim["reason"], name
            assert dim["source"] == "arithmetic", name

    def test_a_channel_with_no_videos_is_null_everywhere_not_zero(self):
        """A failed pull must not look like a terrible channel."""
        out = arithmetic.compute({"videos": []})
        for name, dim in out.items():
            assert dim["score"] is None, name
            assert "not measurable" in dim["reason"], name

    def test_a_measurable_channel_still_produces_numbers(self):
        out = arithmetic.compute({"videos": channel(20)})
        for name, dim in out.items():
            assert isinstance(dim["score"], float), name


def arithmetic_dimensions():
    return ("engagement", "momentum", "speed_to_activate")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))

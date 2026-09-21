"""Tests for the hand-written Spearman rank correlation, with known answers.

Run: python -m pytest
"""
import pytest

from src import rank_correlation


class TestSpearmanRho:
    def test_identical_rankings_score_exactly_one(self):
        ranking = ["a", "b", "c", "d", "e"]
        assert rank_correlation.spearman_rho(ranking, ranking) == 1.0

    def test_fully_reversed_rankings_score_exactly_negative_one(self):
        ranking = ["a", "b", "c", "d", "e"]
        assert rank_correlation.spearman_rho(ranking, list(reversed(ranking))) == -1.0

    def test_extra_items_outside_the_overlap_do_not_skew_the_score(self):
        """A handle only one side ranked must not leave a gap in the other side's positions."""
        rank_a = ["a", "b", "c", "x", "y", "d"]
        rank_b = ["a", "b", "c", "d"]
        assert rank_correlation.spearman_rho(rank_a, rank_b) == 1.0

    def test_fewer_than_two_common_items_returns_none(self):
        assert rank_correlation.spearman_rho(["a"], ["a", "b"]) is None
        assert rank_correlation.spearman_rho(["a", "b"], ["c", "d"]) is None


class TestMissingHandles:
    def test_reports_handles_missing_from_each_side(self):
        only_in_a, only_in_b = rank_correlation.missing_handles(
            ["a", "b", "c"], ["b", "c", "d"]
        )
        assert only_in_a == ["a"]
        assert only_in_b == ["d"]

    def test_no_warning_when_both_sides_match(self):
        only_in_a, only_in_b = rank_correlation.missing_handles(["a", "b"], ["b", "a"])
        assert only_in_a == []
        assert only_in_b == []


class TestToolRanking:
    def test_default_weights_are_equal_across_all_dimensions(self):
        from src.config import DIMENSIONS
        assert rank_correlation.DEFAULT_WEIGHTS == {dim: 1.0 for dim in DIMENSIONS}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))

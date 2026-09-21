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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))

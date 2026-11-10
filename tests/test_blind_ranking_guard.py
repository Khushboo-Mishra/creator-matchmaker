import pytest

from src.trend_rules import check_min_lift
from src.rank_correlation import parse_blind_ranking

WORKSHEET = [
    "# @a   A   10 subscribers",
    "# @b   B   20 subscribers",
    "# @c   C   30 subscribers",
    "# --- your ranking, best first, one handle per line ---",
]


def test_empty_ranking_is_rejected():
    with pytest.raises(ValueError, match="empty"):
        parse_blind_ranking(WORKSHEET)


def test_worksheet_order_is_rejected():
    with pytest.raises(ValueError, match="worksheet order"):
        parse_blind_ranking(WORKSHEET + ["@a", "@b", "@c"])


def test_duplicates_are_rejected():
    with pytest.raises(ValueError, match="repeats"):
        parse_blind_ranking(WORKSHEET + ["@c", "@c", "@a"])


def test_real_reordering_passes_and_ignores_comments():
    assert parse_blind_ranking(WORKSHEET + ["@c", "@a", "@b"]) == ["@c", "@a", "@b"]


def test_shipped_worksheet_is_not_yet_a_ranking():
    from src.rank_correlation import HUMAN_RANKING_FILE

    with pytest.raises(ValueError, match="empty"):
        parse_blind_ranking(HUMAN_RANKING_FILE.read_text(encoding="utf-8").splitlines())


def _snapshot(previous, recent, **extra):
    trend = {
        "topic": "mood board",
        "source_url": "https://trends.google.com/trends/explore?q=mood%20board",
        "previous_interest": previous,
        "recent_interest": recent,
        "window": "2026-08-04 to 2026-11-03",
        "geo": "US",
        **extra,
    }
    return {"source": "Google Trends", "fetched_at": "2026-11-04T00:00:00+00:00", "trends": [trend]}


def test_trend_below_recorded_min_lift_is_rejected():
    with pytest.raises(ValueError, match="minimum lift"):
        check_min_lift(_snapshot(48.8, 49.2, min_lift=0.05))


def test_trend_at_or_above_min_lift_passes():
    assert check_min_lift(_snapshot(59.4, 70.0, min_lift=0.05))


def test_legacy_snapshot_without_min_lift_keeps_old_rule():
    assert check_min_lift(_snapshot(48.8, 49.2))


def test_reversed_worksheet_order_is_rejected():
    with pytest.raises(ValueError, match="worksheet order"):
        parse_blind_ranking(WORKSHEET + ["@c", "@b", "@a"])


def test_handles_are_normalised_for_numbering_case_and_missing_at():
    assert parse_blind_ranking(WORKSHEET + ["1. @C", "2) a", "3.@B"]) == ["@c", "@a", "@b"]


def test_normalised_handles_resolve_to_known_spelling():
    ranking = parse_blind_ranking(WORKSHEET + ["1. C", "2. a", "3. B"], ["@A", "@B", "@C"])
    assert ranking == ["@C", "@A", "@B"]


def test_unknown_handle_is_rejected():
    with pytest.raises(ValueError, match="unknown handles"):
        parse_blind_ranking(WORKSHEET + ["@c", "@a", "@zzz"])


def test_unknown_handle_is_rejected_against_explicit_known_set():
    with pytest.raises(ValueError, match="unknown handles"):
        parse_blind_ranking(["@x", "@y"], ["@a", "@b"])


def test_main_waits_instead_of_crashing_on_an_empty_worksheet(monkeypatch, capsys):
    from src import rank_correlation

    monkeypatch.setattr(rank_correlation, "tool_ranking", lambda: ["@a", "@b"])
    rank_correlation.main()
    assert "Waiting on" in capsys.readouterr().out


@pytest.mark.parametrize("bad", [0, -1, 0.01, "0.05", True])
def test_recorded_min_lift_below_registered_minimum_or_non_numeric_is_rejected(bad):
    with pytest.raises(ValueError, match="min_lift|minimum lift"):
        check_min_lift(_snapshot(48.8, 70.0, min_lift=bad))


def test_zero_baseline_trend_gets_a_distinct_message():
    with pytest.raises(ValueError, match="zero baseline"):
        check_min_lift(_snapshot(0, 20, min_lift=0.05))

"""Spearman's rank correlation between the tool's ranking and a human blind ranking.

Written by hand instead of using scipy.stats.spearmanr: the formula is short and
adding scipy to requirements.txt is not worth it for one number.

Usage:
    python -m src.rank_correlation
"""
import json
import re

from .config import DIMENSIONS, ROOT, SCORES

HUMAN_RANKING_FILE = ROOT / "config" / "human_ranking.txt"

# Equal by default; pass a weights dict to tool_ranking() to favor some dimensions.
DEFAULT_WEIGHTS = {dim: 1.0 for dim in DIMENSIONS}


def spearman_rho(rank_a, rank_b):
    """Spearman's rho between two rank orderings (best first), over their common items.

    Positions are re-ranked within that overlap, not taken from the original
    lists: a handle missing from one side would otherwise leave gaps in the
    other side's positions and inflate the rank differences for no reason.
    """
    common = set(rank_a) & set(rank_b)
    n = len(common)
    if n < 2:
        return None
    a_in_overlap = [h for h in rank_a if h in common]
    b_in_overlap = [h for h in rank_b if h in common]
    pos_a = {h: i for i, h in enumerate(a_in_overlap)}
    pos_b = {h: i for i, h in enumerate(b_in_overlap)}
    d_squared = sum((pos_a[h] - pos_b[h]) ** 2 for h in common)
    return 1 - (6 * d_squared) / (n * (n**2 - 1))


def missing_handles(rank_a, rank_b):
    """(only_in_a, only_in_b): handles each ranking is missing from the other."""
    return (
        [h for h in rank_a if h not in rank_b],
        [h for h in rank_b if h not in rank_a],
    )


def tool_ranking(weights=None):
    """Handles ranked best first by weighted average dimension score, hard stops excluded."""
    weights = weights or DEFAULT_WEIGHTS
    ranked = []
    for p in sorted(SCORES.glob("*.json")):
        record = json.loads(p.read_text())
        if record.get("hard_stop"):
            continue
        total, weight_sum = 0.0, 0.0
        for dim in DIMENSIONS:
            score = record["dimensions"][dim]["score"]
            if score is None:
                continue
            w = weights.get(dim, 1.0)
            total += score * w
            weight_sum += w
        if weight_sum:
            ranked.append((record["handle"], total / weight_sum))
    ranked.sort(key=lambda pair: pair[1], reverse=True)
    return [handle for handle, _ in ranked]


class EmptyRankingError(ValueError):
    """The worksheet has no ranking lines yet."""


def _normalise_handle(token):
    """Strip list numbering ("1.", "2)"), force lower case and a leading @."""
    token = re.sub(r"^\d+[.):-]+", "", token.strip().lower())
    name = token.lstrip("@")
    return f"@{name}" if name else ""


def parse_blind_ranking(lines, known_handles=None):
    """Return the human ranking (best first) from worksheet lines, or raise.

    Lines starting with # are worksheet context. A ranking that is empty, has
    duplicates, names unknown handles, or repeats (or exactly reverses) the
    worksheet's own listed order is not a human ranking and must not be
    correlated against the tool. Handles are matched case-insensitively with
    or without the leading @; a line may start with its rank number
    ("1. @handle"). The listed-order check needs the worksheet's # lines, and
    it cannot catch a lightly shuffled copy.
    """
    ranking, worksheet_order = [], []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            first = line.lstrip("#").split()
            if first and first[0].startswith("@"):
                worksheet_order.append(_normalise_handle(first[0]))
            continue
        tokens = line.split()
        # "1. @handle" has the rank number as its own token; "1.@handle" does not.
        token = tokens[0]
        if not _normalise_handle(token) and len(tokens) > 1:
            token = tokens[1]
        ranking.append(_normalise_handle(token))
    if not ranking:
        raise EmptyRankingError(
            "Blind ranking is empty: a person who has not seen the tool's "
            "output must fill it in, best first, one handle per line"
        )
    known = {_normalise_handle(h): h for h in (known_handles or worksheet_order)}
    if known:
        unknown = [h for h in ranking if h not in known]
        if unknown:
            raise ValueError(f"Blind ranking names unknown handles: {unknown}")
        ranking = [known[h] for h in ranking]
        worksheet_order = [known.get(h, h) for h in worksheet_order]
    duplicates = sorted({h for h in ranking if ranking.count(h) > 1})
    if duplicates:
        raise ValueError(f"Blind ranking repeats handles: {duplicates}")
    if worksheet_order and ranking in (worksheet_order, worksheet_order[::-1]):
        raise ValueError(
            "Ranking matches the unranked worksheet order; this is not a human ranking"
        )
    return ranking


def read_ranking_file(path, known_handles=None):
    return parse_blind_ranking(
        path.read_text(encoding="utf-8").splitlines(), known_handles
    )


def main():
    if not HUMAN_RANKING_FILE.exists():
        print(
            f"Waiting on {HUMAN_RANKING_FILE}: one handle per line, "
            "Rutuja's blind ranking of the ten channels, best first."
        )
        return

    tool_rank = tool_ranking()
    try:
        human_rank = read_ranking_file(HUMAN_RANKING_FILE, tool_rank)
    except EmptyRankingError:
        print(
            f"Waiting on {HUMAN_RANKING_FILE}: no ranking lines yet. Add one handle "
            "per line, best first, below the worksheet comments."
        )
        return

    only_in_tool, only_in_human = missing_handles(tool_rank, human_rank)
    if only_in_tool:
        print(f"Warning: not in the human ranking, excluded from rho: {only_in_tool}")
    if only_in_human:
        print(f"Warning: not in the tool ranking, excluded from rho: {only_in_human}")

    rho = spearman_rho(tool_rank, human_rank)

    print(f"tool ranking:  {tool_rank}")
    print(f"human ranking: {human_rank}")
    if rho is None:
        print("Not enough channels in common to compute a correlation.")
    else:
        print(f"Spearman's rho: {rho:.3f}")


if __name__ == "__main__":
    main()

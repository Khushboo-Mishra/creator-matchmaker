"""Spearman's rank correlation between the tool's ranking and a human blind ranking.

Written by hand instead of using scipy.stats.spearmanr: the formula is short and
adding scipy to requirements.txt is not worth it for one number.

Usage:
    python -m src.rank_correlation
"""
import json

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


def _read_ranking_file(path):
    lines = path.read_text().splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def main():
    if not HUMAN_RANKING_FILE.exists():
        print(
            f"Waiting on {HUMAN_RANKING_FILE}: one handle per line, "
            "Rutuja's blind ranking of the ten channels, best first."
        )
        return

    tool_rank = tool_ranking()
    human_rank = _read_ranking_file(HUMAN_RANKING_FILE)

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

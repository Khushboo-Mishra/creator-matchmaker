"""Spearman's rank correlation between the tool's ranking and a human blind ranking.

Written by hand instead of using scipy.stats.spearmanr: the formula is short and
adding scipy to requirements.txt is not worth it for one number.

Usage:
    python -m src.rank_correlation
"""
import json

from .config import ROOT, SCORES, DIMENSIONS

HUMAN_RANKING_FILE = ROOT / "config" / "human_ranking.txt"


def spearman_rho(rank_a, rank_b):
    """Spearman's rho between two rank orderings (best first), over their common items."""
    common = [h for h in rank_a if h in rank_b]
    n = len(common)
    if n < 2:
        return None
    pos_a = {h: i for i, h in enumerate(rank_a)}
    pos_b = {h: i for i, h in enumerate(rank_b)}
    d_squared = sum((pos_a[h] - pos_b[h]) ** 2 for h in common)
    return 1 - (6 * d_squared) / (n * (n**2 - 1))


def tool_ranking():
    """Handles ranked best first by average dimension score, hard stops excluded."""
    ranked = []
    for p in sorted(SCORES.glob("*.json")):
        record = json.loads(p.read_text())
        if record.get("hard_stop"):
            continue
        scores = [
            record["dimensions"][d]["score"]
            for d in DIMENSIONS
            if record["dimensions"][d]["score"] is not None
        ]
        if scores:
            ranked.append((record["handle"], sum(scores) / len(scores)))
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
    rho = spearman_rho(tool_rank, human_rank)

    print(f"tool ranking:  {tool_rank}")
    print(f"human ranking: {human_rank}")
    if rho is None:
        print("Not enough channels in common to compute a correlation.")
    else:
        print(f"Spearman's rho: {rho:.3f}")


if __name__ == "__main__":
    main()

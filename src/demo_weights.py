"""Show the same scored candidates reordering under different campaign weights.

This is the architectural claim made visible: nothing is recomputed here. Every
score was written to disk once, so a weight change is arithmetic over stored
numbers. The elapsed time printed at the end is the whole point.

Usage:
    python -m src.demo_weights
"""
import time

from .config import DIMENSIONS
from .rank_correlation import tool_ranking

PRESETS = {
    "Balanced": {d: 1.0 for d in DIMENSIONS},
    "Launch week: react fast": {
        "speed_to_activate": 3.0, "momentum": 2.5, "trend_fit": 2.0,
        "audience_relevance": 1.0, "brand_fit": 1.0, "engagement": 0.5,
    },
    "Regulated brand: safety first": {
        "brand_fit": 3.5, "audience_relevance": 2.0, "engagement": 1.5,
        "momentum": 0.5, "speed_to_activate": 0.5, "trend_fit": 0.5,
    },
    "Niche trust: proof over reach": {
        "engagement": 3.0, "audience_relevance": 2.5, "brand_fit": 1.5,
        "trend_fit": 1.0, "momentum": 1.0, "speed_to_activate": 0.5,
    },
}
TOP = 5


def main():
    started = time.perf_counter()
    rankings = {name: tool_ranking(w)[:TOP] for name, w in PRESETS.items()}
    elapsed = time.perf_counter() - started

    for name, ranked in rankings.items():
        print(f"\n{name}")
        print("-" * len(name))
        for position, handle in enumerate(ranked, 1):
            print(f"  {position}. {handle}")

    moved = len({r[0] for r in rankings.values()})
    print(
        f"\n{len(PRESETS)} weightings over {len(tool_ranking())} scored candidates "
        f"in {elapsed*1000:.0f} ms, {moved} different creators took first place."
    )
    print("No API call was made. Every score was read from data/scores/.")


if __name__ == "__main__":
    main()

"""Reproducibility check: score every channel three times and report the spread.

This is the "how reproducible is this" number for the deck. Arithmetic dimensions
are deterministic by design and always spread zero; the number that matters here
is how much score_ai's model dimensions move between runs at the same input.

Usage:
    python -m src.stability              # every channel in data/channels/
    python -m src.stability @handle ...  # just these handles
"""
import json
import sys

from . import score_ai
from .config import CHANNELS, MODEL_DIMENSIONS, RULES_FILE

RUNS = 3


def _spread(values):
    return max(values) - min(values)


def score_channel(record, rules_text):
    """Score one channel RUNS times, return {dim: [scores across runs]}."""
    per_dim = {dim: [] for dim in MODEL_DIMENSIONS}
    for _ in range(RUNS):
        result = score_ai.score(record, rules_text)
        for dim in MODEL_DIMENSIONS:
            per_dim[dim].append(result["dimensions"][dim]["score"])
    return per_dim


def main():
    wanted = set(sys.argv[1:])
    paths = sorted(CHANNELS.glob("*.json"))
    if wanted:
        paths = [p for p in paths if p.stem in wanted]

    rules_text = RULES_FILE.read_text()
    worst = 0.0
    for p in paths:
        record = json.loads(p.read_text())
        per_dim = score_channel(record, rules_text)
        print(f"{p.stem}:")
        for dim, values in per_dim.items():
            spread = round(_spread(values), 2)
            worst = max(worst, spread)
            print(f"  {dim}: {values} spread={spread}")

    print(f"\nmax spread across all channels and dimensions: {round(worst, 2)}")


if __name__ == "__main__":
    main()

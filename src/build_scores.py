"""Merge the arithmetic and model dimensions into data/scores/<handle>.json.

Usage:
    python -m src.build_scores              # everything in data/channels/
    python -m src.build_scores --no-model   # arithmetic only, no API key needed
"""
import json
import sys
from datetime import datetime, timezone

from . import arithmetic
from .config import CHANNELS, RULES_FILE, SCORES


def build(channel_path, use_model=True):
    record = json.loads(channel_path.read_text())
    dimensions = arithmetic.compute(record)

    if use_model:
        from . import score_ai
        dimensions.update(score_ai.score(record, RULES_FILE.read_text()))
    else:
        for dim in ("audience_relevance", "brand_fit", "trend_fit"):
            dimensions[dim] = {
                "score": 0, "reason": "model scoring skipped",
                "source": "model", "evidence": [],
            }

    out = {
        "handle": record["handle"],
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "hard_stop": False,
        "hard_stop_reason": None,
        "dimensions": dimensions,
    }
    SCORES.mkdir(parents=True, exist_ok=True)
    path = SCORES / channel_path.name
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    return path


def main():
    use_model = "--no-model" not in sys.argv
    for p in sorted(CHANNELS.glob("*.json")):
        try:
            print(f"ok   {p.stem} -> {build(p, use_model).name}")
        except Exception as exc:
            print(f"fail {p.stem}: {exc}")


if __name__ == "__main__":
    main()

"""Merge the arithmetic and model dimensions into data/scores/<handle>.json.

Usage:
    python -m src.build_scores              # everything in data/channels/
    python -m src.build_scores --no-model   # arithmetic only, no API key needed
    python -m src.build_scores --force      # re-score channels that already have a score file
"""
import json
import sys
from datetime import datetime, timezone

from . import arithmetic, policy
from .config import CHANNELS, RULES_FILE, SCORES


def build(channel_path, use_model=True):
    record = json.loads(channel_path.read_text())
    dimensions = arithmetic.compute(record)
    rules_text = RULES_FILE.read_text()

    # Policy gate runs regardless of --no-model: it's plain code, not a model call.
    gate = policy.evaluate(record, rules_text)
    reasons = [gate["hard_stop_reason"]] if gate["hard_stop"] else []
    warnings = list(gate["warnings"])

    if use_model:
        from . import score_ai
        result = score_ai.score(record, rules_text)
        dimensions.update(result["dimensions"])
        if result["hard_stop"]:
            reasons.append(result.get("hard_stop_reason") or "model flagged hard stop")
    else:
        for dim in ("audience_relevance", "brand_fit", "trend_fit"):
            dimensions[dim] = {
                "score": None, "reason": "model scoring skipped",
                "source": "model", "evidence": [],
            }

    out = {
        "handle": record["handle"],
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "hard_stop": bool(reasons),
        "hard_stop_reason": "; ".join(reasons) if reasons else None,
        "warnings": warnings,
        "dimensions": dimensions,
    }
    SCORES.mkdir(parents=True, exist_ok=True)
    path = SCORES / channel_path.name
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    return path


def main():
    use_model = "--no-model" not in sys.argv
    force = "--force" in sys.argv
    for p in sorted(CHANNELS.glob("*.json")):
        if not force and (SCORES / p.name).exists():
            print(f"skip {p.stem}: already scored, pass --force to redo")
            continue
        try:
            print(f"ok   {p.stem} -> {build(p, use_model).name}")
        except Exception as exc:
            print(f"fail {p.stem}: {exc}")


if __name__ == "__main__":
    main()

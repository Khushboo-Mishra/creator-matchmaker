"""Write data/trend_snapshot.json from text a human gathered, with no API call.

Why this exists: Google Search grounding needs billing enabled, and on the free
tier refresh_trends fails. But score_ai only calls Google when the snapshot on
disk is missing or stale, so a snapshot written by hand unblocks trend_fit and
everything downstream of it. Someone searches, pastes what they found, and the
pipeline runs.

The file this writes is deliberately marked source="manual". A grounded snapshot
and a hand-written one are not the same evidence, and the write-up has to be able
to tell them apart: trend_fit scored against a manual snapshot is reproducible,
but it is not source-backed by a live search.

Usage:
    python -m src.seed_trends --from-file trends.txt --citation https://...
    echo "..." | python -m src.seed_trends --citation https://...
"""
import argparse
import sys

from .config import RULES_FILE, TREND_CACHE_FILE
from .score_ai import _write_trend_snapshot, ground_trend_topics


def seed(context, citations, rules_text=None):
    """Persist a manual snapshot that score_ai will read as valid."""
    context = (context or "").strip()
    if not context:
        raise ValueError("refusing to write an empty trend snapshot")
    rules_text = rules_text if rules_text is not None else RULES_FILE.read_text()
    _write_trend_snapshot(rules_text, context, list(citations))
    _mark_manual()
    ground_trend_topics.cache_clear()
    return TREND_CACHE_FILE


def _mark_manual():
    """Record provenance. score_ai ignores unknown keys, so this is safe to add."""
    import json

    snapshot = json.loads(TREND_CACHE_FILE.read_text(encoding="utf-8"))
    snapshot["source"] = "manual"
    TREND_CACHE_FILE.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-file", help="file holding the trend text; default stdin")
    parser.add_argument(
        "--citation",
        action="append",
        default=[],
        help="source URL the text came from; repeat for each one",
    )
    args = parser.parse_args()

    if args.from_file:
        context = open(args.from_file, encoding="utf-8").read()
    else:
        context = sys.stdin.read()

    if not args.citation:
        print("warning: no --citation given, the snapshot will cite nothing")

    path = seed(context, args.citation)
    print(f"wrote {path} (source=manual, {len(args.citation)} citations)")
    print("score_ai will now read this instead of calling Google Search.")


if __name__ == "__main__":
    main()

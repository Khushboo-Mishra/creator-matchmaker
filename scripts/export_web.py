"""Export only public display fields from an audited run to the static prototype.

Usage: python scripts/export_web.py data/runs/RUN_ID/audit.json
"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.pipeline import verify_snapshot  # noqa: E402


def web_payload(run):
    verify_snapshot(run)
    channels = {c["channel_id"]: c for c in run["channels"]}
    data = [
        {
            "h": c["handle"],
            "t": c["title"],
            "subs": channels[c["channel_id"]].get("subscribers"),
            "d": {
                key: {"s": value["score"], "r": value["reason"]}
                for key, value in c["dimensions"].items()
            },
            "score": c["combined_score"],
            "safety": c["brand_safety"],
            "capabilities": c["capabilities"],
            "similarity": c["similarity"],
        }
        for c in run["ranking"]
    ]
    metadata = {
        "run_id": run["run_id"],
        "mode": run["mode"],
        "snapshot_at": run["data_snapshot_at"],
        "scoring_version": run["scoring_version"],
        "weights": run["weights"],
        "priorities": run["capability_priorities"],
        "warnings": run["warnings"],
        "roster": [
            {"handle": c["handle"], "components": c["marginal_components"]}
            for c in run["roster"]
        ],
    }
    return data, metadata


def js_json(value):
    # Prevent script termination or HTML injection even when a title contains markup.
    return (
        json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def export(run_path, output):
    run = json.loads(Path(run_path).read_text(encoding="utf-8"))
    data, metadata = web_payload(run)
    Path(output).write_text(
        "// Generated from a pipeline run. Do not edit by hand.\n"
        + "const DATA = "
        + js_json(data)
        + ";\n"
        + "const RUN = "
        + js_json(metadata)
        + ";\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "audit", help="Saved run audit.json (display fields will be public)"
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parents[1] / "docs" / "data.js"),
    )
    args = parser.parse_args()
    export(args.audit, args.output)
    print(f"Exported saved roster and scores to {args.output}")

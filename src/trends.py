"""Gemini proposes topics; Google Trends export data confirms measured rises.

Google Search citations are never accepted as Google Trends verification.
The import boundary is explicit: the operator supplies official Trends CSVs.
"""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
from statistics import mean
from urllib.parse import urlparse

from .campaign import Campaign
from .config import GEMINI_API_KEY, GEMINI_MODEL
from . import score_ai
from .trend_rules import MIN_LIFT, meets_min_lift


def propose(campaign):
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is required for trend proposals")
    response = score_ai._post_with_retry(
        url=score_ai.ENDPOINT.format(model=GEMINI_MODEL),
        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
        json={
            "contents": [
                {
                    "parts": [
                        {
                            "text": "Propose up to 8 specific Google Trends search topics relevant to this campaign. These are hypotheses, not verified trends. Return JSON with topics: array of strings. Campaign data: "
                            + json.dumps(campaign.canonical())
                        }
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0,
            },
        },
        timeout=60,
    )
    response.raise_for_status()
    result = json.loads(response.json()["candidates"][0]["content"]["parts"][0]["text"])
    topics = result["topics"]
    if (
        not isinstance(topics, list)
        or not topics
        or len(topics) > 8
        or any(not isinstance(t, str) or not t.strip() for t in topics)
    ):
        raise ValueError("Invalid trend topic response")
    return {
        "campaign_fingerprint": campaign.fingerprint(),
        "proposed_at": datetime.now(timezone.utc).isoformat(),
        "model": GEMINI_MODEL,
        "topics": list(dict.fromkeys(topics)),
        "status": "unverified_proposals",
    }


def import_exports(manifest, base, before=None):
    if before is not None:
        try:
            cutoff = datetime.strptime(before, "%Y-%m-%d").date()
            if cutoff.isoformat() != before:
                raise ValueError()
        except (ValueError, TypeError) as exc:
            raise ValueError("--before must be a date in YYYY-MM-DD format") from exc
    records, rising = [], []
    for item in manifest["exports"]:
        if urlparse(item["source_url"]).hostname != "trends.google.com":
            raise ValueError("Export must identify its Google Trends source URL")
        content = (base / item["file"]).read_bytes()
        rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
        header = next(
            (
                i
                for i, row in enumerate(rows)
                if row and row[0] in {"Day", "Week", "Month", "Time"}
            ),
            None,
        )
        if header is None or len(rows[header]) != 2:
            raise ValueError(
                "Use an English Google Trends interest-over-time CSV with one topic"
            )
        # Google Trends exports have carried two header shapes: the older
        # "topic: (United States)", which names the geo inline, and the
        # current "topic", which puts the geo in the filename instead.
        # Accept both. The manifest still declares geo, and export_sha256
        # below binds the record to these exact bytes either way.
        column = rows[header][1].casefold().strip()
        topic = item["topic"].casefold().strip()
        if column != topic and not column.startswith(topic + ":"):
            raise ValueError("Manifest topic does not match the CSV topic header")
        series = []
        for row in rows[header + 1:]:
            if not row:
                continue
            datetime.fromisoformat(row[0] + "-01" if len(row[0]) == 7 else row[0])
            value = 0.5 if row[1] == "<1" else float(row[1])
            if not 0 <= value <= 100:
                raise ValueError("Google Trends interest must be 0-100")
            series.append({"date": row[0], "value": value})
        if len(series) < 4 or [x["date"] for x in series] != sorted(
            {x["date"] for x in series}
        ):
            raise ValueError(
                "At least four unique ordered Google Trends periods required"
            )
        excluded = []
        if before is not None:
            excluded = [
                x["date"]
                for x in series
                if datetime.fromisoformat(
                    x["date"] + "-01" if len(x["date"]) == 7 else x["date"]
                ).date()
                >= cutoff
            ]
            series = [x for x in series if x["date"] not in excluded]
        if len(series) < 4:
            raise ValueError(
                "At least four retained periods required after --before cutoff"
            )
        split = len(series) // 2
        previous = mean(x["value"] for x in series[:split])
        recent = mean(x["value"] for x in series[split:])
        record = {
            "topic": item["topic"],
            "geo": item["geo"],
            "window": item["window"],
            "source_url": item["source_url"],
            "export_sha256": hashlib.sha256(content).hexdigest(),
            "series": series,
            "excluded_dates": excluded,
            "retained_period_start_range": {
                "first": series[0]["date"],
                "last": series[-1]["date"],
            },
            "previous_interest": previous,
            "recent_interest": recent,
        }
        record["min_lift"] = MIN_LIFT
        if meets_min_lift(previous, recent):
            rising.append(record)
        elif previous <= 0:
            record["not_retained_reason"] = "zero baseline: lift is undefined"
        else:
            record["not_retained_reason"] = "lift below minimum"
        records.append(record)
    if not records:
        raise ValueError("At least one official export is required")
    return {
        "source": "Google Trends",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "verification_method": "Operator-supplied official CSV; recent-half mean exceeds previous-half mean by at least min_lift",
        "campaign_fingerprint": manifest["campaign_fingerprint"],
        "filter": {
            "before": before,
            "rule": "Retain only periods whose start date is strictly before the cutoff; no automatic partial-period detection",
        },
        "checked_topics": records,
        "trends": rising,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("propose")
    p.add_argument("--campaign", required=True)
    p.add_argument("--output", required=True)
    p = sub.add_parser("import")
    p.add_argument("--manifest", required=True)
    p.add_argument("--output", required=True)
    p.add_argument(
        "--before", help="YYYY-MM-DD: exclude periods starting on or after this date"
    )
    args = parser.parse_args(argv)
    if args.command == "propose":
        result = propose(
            Campaign(**json.loads(Path(args.campaign).read_text(encoding="utf-8")))
        )
    else:
        path = Path(args.manifest)
        result = import_exports(
            json.loads(path.read_text(encoding="utf-8")),
            path.parent,
            before=args.before,
        )
    with Path(args.output).open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2, ensure_ascii=False)
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()

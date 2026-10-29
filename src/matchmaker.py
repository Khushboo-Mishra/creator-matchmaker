"""Backend entrypoint: python -m src.matchmaker --help."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from .campaign import Campaign
from .pipeline import run, revise, save, verify_snapshot, validate_run, model_stability
from .providers import DemoProvider, LiveProvider
from .reports import write_reports


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_trends(campaign, mode, path=None):
    if path:
        return read(path)
    if mode in {"demo", "synthetic-demo"}:
        fixture = read(
            Path(__file__).resolve().parent.parent / "examples" / "trend_snapshot.json"
        )
        if fixture["campaign_fingerprint"] == campaign.fingerprint():
            return fixture
    return None


def parser():
    p = argparse.ArgumentParser(
        description="Campaign input -> screening -> evidence -> roster -> report"
    )
    sub = p.add_subparsers(dest="command", required=True)
    for command in ("run", "refresh-data"):
        s = sub.add_parser(command)
        if command == "run":
            s.add_argument("--campaign", required=True)
            s.add_argument("--mode", choices=["demo", "live"], required=True)
        else:
            s.add_argument("--snapshot", required=True)
        s.add_argument(
            "--trends",
            help="Verified Google Trends snapshot JSON; unavailable means null Trend Fit",
        )
        s.add_argument("--min-comments", type=int, default=10)
        s.add_argument("--reach-exponent", type=float, default=1)
        s.add_argument("--out", default="data/runs")
        s.add_argument("--no-pdf", action="store_true")
    s = sub.add_parser("rescore")
    s.add_argument("--snapshot", required=True)
    s.add_argument("--weights", help="JSON file with all six ranking weights")
    s.add_argument("--priorities", help="JSON file with all four capability priorities")
    s.add_argument("--reset", action="store_true")
    s.add_argument("--swap", nargs=2, metavar=("OUTGOING", "INCOMING"))
    s.add_argument("--out", default="data/runs")
    s.add_argument("--no-pdf", action="store_true")
    s = sub.add_parser("validate")
    s.add_argument("--snapshot", required=True)
    s.add_argument(
        "--human-ranking", help="Blind ranking text file, one handle per line"
    )
    s.add_argument(
        "--repeat-model",
        action="store_true",
        help="Make three fresh evaluations of frozen evidence (uses API in live mode)",
    )
    s.add_argument("--output", help="Save validation JSON to a new file")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command == "validate":
        snapshot = read(args.snapshot)
        verify_snapshot(snapshot)
        human = (
            Path(args.human_ranking).read_text(encoding="utf-8").splitlines()
            if args.human_ranking
            else None
        )
        validation = validate_run(snapshot, human)
        if args.repeat_model:
            provider = (
                LiveProvider()
                if snapshot["mode"] == "live"
                else DemoProvider(datetime.fromisoformat(snapshot["data_snapshot_at"]))
            )
            validation["model_stability"] = model_stability(snapshot, provider)
        payload = json.dumps(validation, indent=2)
        if args.output:
            with Path(args.output).open("x", encoding="utf-8") as output:
                output.write(payload)
        print(payload)
        return
    if not args.no_pdf:
        try:
            import reportlab  # noqa: F401
        except ImportError as exc:
            raise ValueError(
                "Install requirements.txt for PDF output, or use --no-pdf"
            ) from exc
    at = datetime.now(timezone.utc)
    if args.command == "rescore":
        snapshot = revise(
            read(args.snapshot),
            read(args.weights) if args.weights else None,
            read(args.priorities) if args.priorities else None,
            args.reset,
            args.swap,
        )
    else:
        previous = read(args.snapshot) if args.command == "refresh-data" else None
        campaign = Campaign(
            **(previous["campaign"] if previous else read(args.campaign))
        )
        mode = previous["mode"] if previous else args.mode
        provider = LiveProvider() if mode == "live" else DemoProvider(at)
        snapshot = run(
            campaign,
            provider,
            at,
            load_trends(campaign, mode, args.trends),
            args.min_comments,
            args.reach_exponent,
        )
        if previous:
            snapshot["refresh_of"] = previous["run_id"]
    directory = save(snapshot, args.out)
    write_reports(snapshot, directory, pdf=not args.no_pdf)
    print(f"Mode: {snapshot['mode']} | Snapshot: {snapshot['data_snapshot_at']}")
    print(
        f"Discovered: {len(snapshot['channels'])} | Shortlisted: {len(snapshot['evaluated'])} | Roster: {len(snapshot['roster'])}"
    )
    for creator in snapshot["roster"]:
        print(
            f"  {creator['handle']}: {creator['combined_score']:.2f}/10 | {creator['brand_safety']}"
        )
    for warning in snapshot["warnings"]:
        print(f"WARNING: {warning}")
    print(f"Saved run: {directory.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError) as exc:
        raise SystemExit(f"Run failed: {exc}") from exc

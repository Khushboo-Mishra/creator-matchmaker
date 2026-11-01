"""Migrate approved checkpoint versions offline with explicit evidence checks."""

import argparse
from datetime import datetime, timezone
import hashlib
import inspect
import json
from pathlib import Path
from .checkpoint import Checkpoint, atomic_write, digest
from .campaign import Campaign
from .config import GEMINI_MODEL, GEMINI_EMBEDDING_MODEL
from .discovery_file import validate_discovery
from .evaluation import valid_trends
from .pipeline import code_version, fingerprint
from .providers import LiveProvider

LEGACY_CODE = "fd4a6217447f2576d04a942723c5acb0b37ccb77f66f0a47a0538eb4cf0f1eed"
REFERENCE_CODE = "df606f53fd5ed1511b84a25b792da541b4cbac455ba5e043004fd87dcb3acd30"
PACER_SOURCE_CODE = "3af7bbbd171d13e17b54a731fdda6a18f28caf7a955874b77bfc8707e2878c84"
VALIDATION_FILES = {
    "evaluation.py": "da73697877d741f694b19564fd5d356d492319fbe116e50fccdb0b1d7db60f28",
    "metadata_evidence.py": "af6744260a5ac4e7bfb47436570dff25975a5ce0066f691c1721f97e7f7724d5",
    "judgment_contract.py": "8dd8a6426cabbbb856d426d3811d5b272a0c12d8b23370bb662ddda5a6055436",
    "ranking.py": "6947d3a75acae2ae71968126f913ab843c6a56048e2d35384df538cf2ba04c21",
    "screening.py": "3e4137865b3308cb0daaefe7ff5ddecc5cfa92c503fa83050793f4e7045ddda4",
}
COLLECTION_FILES = {
    "config.py": "229ac66b225199569e218ac3b8abfe4e4e5e9540c15e345f4fcbc0bda6bed918",
    "discover.py": "8a404248b928e34c7893d70d57ca0ac18e338f3b38735817fb83e648ad524aa1",
    "pull.py": "24584e96043a20a98c63f7be3d2bb039e035a8e9badefba344b5fbe9b29997d1",
    "score_ai.py": "328e2eb94a000773c328c8cf44cd5cc066d443847fe5633e38aed5b189ab1dc5",
}
COLLECTION_METHODS = {
    "discover": "0e55fff29f3d5c2e6e82ad2d6372a60d68c948f770bee8b259b29a142ea80b8d",
    "channel": "0203b68e3fbec386a49299a2fbc8233f386412895ef3bb8c9772a809460ada5c",
    "comments": "e77b04b97a490451b692741d6ec7368b385a622997743a324422c668d914c71a",
    "embed": "be401d03f75ab55db82fa92c14f628c593a3d77a798f06a8befb3a2c3cf723a5",
}


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def migrate(source, destination, bindings, campaign=None, trends=None):
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise ValueError("Migration destination must be a new directory")
    for name, expected in COLLECTION_FILES.items():
        if sha(Path(__file__).with_name(name).read_text(encoding="utf-8")) != expected:
            raise ValueError(f"Collection implementation changed: {name}")
    for name, expected in COLLECTION_METHODS.items():
        if sha(inspect.getsource(getattr(LiveProvider, name))) != expected:
            raise ValueError(f"Collection method changed: {name}")
    state = json.loads((source / "checkpoint.json").read_text(encoding="utf-8"))
    checksum = state.pop("checksum")
    if digest(state) != checksum:
        raise ValueError("Source checkpoint manifest integrity mismatch")
    old = state["bindings"]
    preserve_evaluations = old["code"] in {REFERENCE_CODE, PACER_SOURCE_CODE}
    if old["code"] not in {LEGACY_CODE, REFERENCE_CODE, PACER_SOURCE_CODE}:
        raise ValueError(
            "This migration only supports the approved legacy code version"
        )
    if {k: v for k, v in old.items() if k != "code"} != {
        k: v for k, v in bindings.items() if k != "code"
    }:
        raise ValueError("Campaign, data, model or calibration mismatch")
    if bindings["code"] != code_version():
        raise ValueError("Target code version mismatch")
    if preserve_evaluations:
        for name, expected in VALIDATION_FILES.items():
            if (
                sha(Path(__file__).with_name(name).read_text(encoding="utf-8"))
                != expected
            ):
                raise ValueError(f"Evaluation semantics changed: {name}")
        if (
            campaign is None
            or campaign.fingerprint() != old["campaign"]
            or fingerprint(trends) != old["trends"]
        ):
            raise ValueError(
                "Migration requires matching campaign and trends for evidence checks"
            )
    records, counts = [], {}
    skipped = 0
    for path in sorted(source.glob("*.json")):
        if path.name == "checkpoint.json":
            continue
        stage, key = path.stem.split("-", 1)
        if stage not in {"discovery", "channel", "comments", "embedding", "evaluation"}:
            raise ValueError(f"Unexpected checkpoint stage: {stage}")
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["key"] != key or digest(record["value"]) != record["checksum"]:
            raise ValueError(f"Checkpoint entry integrity mismatch: {path.name}")
        if stage == "evaluation" and not preserve_evaluations:
            skipped += 1
            continue
        records.append((path.name, record))
        counts[stage] = counts.get(stage, 0) + 1
    reused = 0
    if preserve_evaluations:
        from .checkpoint_validation import validate_cached_evaluations

        reused = validate_cached_evaluations(
            records, campaign, trends, old["min_comments"]
        )
    destination.mkdir(parents=True, exist_ok=False)
    for name, record in records:
        atomic_write(destination / name, record)
    migration = {
        "source": str(source.resolve()),
        "source_manifest_checksum": checksum,
        "source_code": old["code"],
        "target_code": bindings["code"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "copied": counts,
        "evaluations_not_reused": skipped,
        "evaluations_reused": reused,
        "retained_evaluation_prompt_version": (
            (
                "metadata-evidence-6 (see previous_migration for inherited versions)"
                if old["code"] == PACER_SOURCE_CODE
                else "metadata-evidence-5"
            )
            if reused
            else None
        ),
        "previous_migration": state.get("migration"),
        "policy": (
            "Preserve source-validated evaluations; transport pacing/retry only for bounded-reference source"
            if preserve_evaluations
            else "Raw collection and embeddings only; re-evaluate with current prompt"
        ),
    }
    new_state = {"bindings": bindings, "at": state["at"], "migration": migration}
    atomic_write(
        destination / "checkpoint.json", dict(new_state, checksum=digest(new_state))
    )
    Checkpoint(destination, bindings, datetime.fromisoformat(state["at"]), resume=True)
    return migration


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "output", "campaign", "discovery", "trends"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--min-comments", type=int, default=10)
    parser.add_argument("--reach-exponent", type=float, default=1)
    args = parser.parse_args(argv)

    def read(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))

    campaign = Campaign(**read(args.campaign))
    discovery, trends = read(args.discovery), read(args.trends)
    validate_discovery(discovery, campaign)
    valid_trends(trends, datetime.now(timezone.utc))
    if trends["campaign_fingerprint"] != campaign.fingerprint():
        raise ValueError("Trend campaign mismatch")
    bindings = {
        "campaign": campaign.fingerprint(),
        "trends": fingerprint(trends),
        "discovery": fingerprint(discovery),
        "code": code_version(),
        "model": GEMINI_MODEL,
        "embedding_model": GEMINI_EMBEDDING_MODEL,
        "mode": "live",
        "min_comments": args.min_comments,
        "reach_exponent": args.reach_exponent,
    }
    print(
        json.dumps(
            migrate(args.source, args.output, bindings, campaign, trends), indent=2
        )
    )


if __name__ == "__main__":
    main()

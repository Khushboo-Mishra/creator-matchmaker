"""One-off raw-cache migration. No APIs; completed judgments are not reused."""

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
COLLECTION_FILES = {
    "config.py": "229ac66b225199569e218ac3b8abfe4e4e5e9540c15e345f4fcbc0bda6bed918",
    "discover.py": "8a404248b928e34c7893d70d57ca0ac18e338f3b38735817fb83e648ad524aa1",
    "pull.py": "24584e96043a20a98c63f7be3d2bb039e035a8e9badefba344b5fbe9b29997d1",
    "score_ai.py": "681f4b1b4ec965541ad148e686f42d1e895fdf08ffc437f18b9d3f51f8083bef",
}
COLLECTION_METHODS = {
    "discover": "0e55fff29f3d5c2e6e82ad2d6372a60d68c948f770bee8b259b29a142ea80b8d",
    "channel": "0203b68e3fbec386a49299a2fbc8233f386412895ef3bb8c9772a809460ada5c",
    "comments": "e77b04b97a490451b692741d6ec7368b385a622997743a324422c668d914c71a",
    "embed": "be401d03f75ab55db82fa92c14f628c593a3d77a798f06a8befb3a2c3cf723a5",
}


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def migrate(source, destination, bindings):
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
    if old["code"] != LEGACY_CODE:
        raise ValueError(
            "This migration only supports the approved legacy code version"
        )
    if {k: v for k, v in old.items() if k != "code"} != {
        k: v for k, v in bindings.items() if k != "code"
    }:
        raise ValueError("Campaign, data, model or calibration mismatch")
    if bindings["code"] != code_version():
        raise ValueError("Target code version mismatch")
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
        if stage == "evaluation":
            skipped += 1
            continue
        records.append((path.name, record))
        counts[stage] = counts.get(stage, 0) + 1
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
        "policy": "Raw collection and embeddings only; re-evaluate with current prompt",
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
    print(json.dumps(migrate(args.source, args.output, bindings), indent=2))


if __name__ == "__main__":
    main()

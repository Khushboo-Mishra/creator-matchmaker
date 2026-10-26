"""Frozen run snapshots; refresh is explicit and never implicit on weight edits."""
from datetime import datetime, timezone
import json
from pathlib import Path

def freeze(path, campaign, weights, priorities, candidates, run_version="1", scoring_version="1"):
    snapshot = {"run_version": run_version, "scoring_version": scoring_version, "created_at": datetime.now(timezone.utc).isoformat(), "campaign": campaign.canonical(), "campaign_fingerprint": campaign.fingerprint(), "weights": dict(weights), "capability_priorities": dict(priorities), "candidates": candidates}
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False))
    return snapshot

"""Private local evidence for failed evaluations; not a resumable run."""

from datetime import datetime, timezone
import json
from uuid import uuid4

from .config import DATA


def save_failure(channel, campaign, provider, trends, error):
    directory = DATA / "diagnostics"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"evaluation-{uuid4()}.json"
    # Never serialize HTTP objects, request headers, environment or API keys.
    payload = {
        "kind": "failed_evaluation_not_resumable",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": provider.model,
        "campaign_fingerprint": campaign.fingerprint(),
        "channel": channel,
        "trend_snapshot": trends,
        "error": str(error),
        "judgment": getattr(provider, "last_judgment", None),
        "response_text": getattr(provider, "last_response_text", None),
    }
    with path.open("x", encoding="utf-8") as output:
        # repr preserves invalid NaN/Infinity diagnostically without invalid JSON.
        def safe(value):
            if isinstance(value, float):
                import math

                return value if math.isfinite(value) else repr(value)
            if isinstance(value, dict):
                return {k: safe(v) for k, v in value.items()}
            if isinstance(value, list):
                return [safe(v) for v in value]
            return value

        json.dump(safe(payload), output, ensure_ascii=False, indent=2, allow_nan=False)
    return path.resolve()

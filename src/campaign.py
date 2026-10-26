"""Campaign inputs and versioned, auditable ranking controls."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json

DIMENSIONS = ("audience_relevance", "engagement", "brand_fit", "momentum", "speed_to_activate", "trend_fit")
CAPABILITIES = ("audience_relevance", "brand_fit", "trend_fit", "speed_to_activate")

@dataclass
class Campaign:
    product_description: str
    objective: str
    specific_goal: str
    audience: str
    brand_requirements: dict = field(default_factory=dict)

    def canonical(self):
        return asdict(self)

    def fingerprint(self):
        raw = json.dumps(self.canonical(), sort_keys=True, ensure_ascii=False).encode()
        return hashlib.sha256(raw).hexdigest()

def default_weights(objective="awareness"):
    """Independent dimensions; objective presets are starting points only."""
    presets = {
        "awareness": {"audience_relevance": .25, "engagement": .20, "brand_fit": .20, "momentum": .15, "speed_to_activate": .05, "trend_fit": .15},
        "conversion": {"audience_relevance": .25, "engagement": .20, "brand_fit": .30, "momentum": .10, "speed_to_activate": .05, "trend_fit": .10},
        "launch": {"audience_relevance": .25, "engagement": .15, "brand_fit": .20, "momentum": .15, "speed_to_activate": .15, "trend_fit": .10},
    }
    return dict(presets.get(objective.lower(), presets["awareness"]))

def validate_controls(weights, priorities):
    if set(weights) != set(DIMENSIONS) or any(v < 0 for v in weights.values()) or sum(weights.values()) <= 0:
        raise ValueError("weights must contain all six dimensions and have a positive non-negative total")
    if set(priorities) != set(CAPABILITIES) or any(v < 0 for v in priorities.values()) or sum(priorities.values()) <= 0:
        raise ValueError("capability priorities must contain four non-negative values with a positive total")

def audit_controls(weights, priorities, actor="system"):
    validate_controls(weights, priorities)
    return {"weights": dict(weights), "capability_priorities": dict(priorities), "actor": actor, "changed_at": datetime.now(timezone.utc).isoformat()}

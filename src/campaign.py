"""Campaign inputs and versioned, auditable ranking controls."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math

DIMENSIONS = (
    "audience_relevance",
    "engagement",
    "brand_fit",
    "momentum",
    "speed_to_activate",
    "trend_fit",
)
CAPABILITIES = ("reach", "demonstration", "credibility", "speed")


@dataclass
class Campaign:
    product_description: str
    objective: str
    specific_goal: str
    audience: str
    brand_requirements: dict = field(default_factory=dict)

    def __post_init__(self):
        for name in ("product_description", "objective", "specific_goal", "audience"):
            if (
                not isinstance(getattr(self, name), str)
                or not getattr(self, name).strip()
            ):
                raise ValueError(f"{name} must be nonempty text")
        if self.objective.lower() not in {
            "awareness",
            "consideration",
            "conversion",
            "launch",
            "trend response",
        }:
            raise ValueError("Unsupported objective")
        allowed = {"banned_phrases", "raw_tone", "category_exclusions", "competitors"}
        if (
            not isinstance(self.brand_requirements, dict)
            or set(self.brand_requirements) - allowed
        ):
            raise ValueError("Invalid brand requirements")
        self.brand_requirements = {
            "banned_phrases": [],
            "raw_tone": "",
            "category_exclusions": [],
            "competitors": [],
            **self.brand_requirements,
        }
        for key, value in self.brand_requirements.items():
            if key == "raw_tone":
                if not isinstance(value, str):
                    raise ValueError("raw_tone must be text")
            elif not isinstance(value, list) or any(
                not isinstance(x, str) or not x.strip() for x in value
            ):
                raise ValueError(f"{key} must be a list of nonempty strings")

    def canonical(self):
        return asdict(self)

    def fingerprint(self):
        raw = json.dumps(self.canonical(), sort_keys=True, ensure_ascii=False).encode()
        return hashlib.sha256(raw).hexdigest()


def default_weights(objective="awareness"):
    """Independent dimensions; objective presets are starting points only."""
    presets = {
        "awareness": {
            "audience_relevance": 0.25,
            "engagement": 0.20,
            "brand_fit": 0.20,
            "momentum": 0.15,
            "speed_to_activate": 0.05,
            "trend_fit": 0.15,
        },
        "conversion": {
            "audience_relevance": 0.25,
            "engagement": 0.20,
            "brand_fit": 0.30,
            "momentum": 0.10,
            "speed_to_activate": 0.05,
            "trend_fit": 0.10,
        },
        "launch": {
            "audience_relevance": 0.25,
            "engagement": 0.15,
            "brand_fit": 0.20,
            "momentum": 0.15,
            "speed_to_activate": 0.15,
            "trend_fit": 0.10,
        },
    }
    presets["consideration"] = dict(presets["conversion"])
    presets["trend response"] = dict(
        presets["launch"], trend_fit=0.25, brand_fit=0.10, momentum=0.10
    )
    return dict(presets[objective.lower()])


def default_priorities(objective="awareness"):
    values = {
        "awareness": (1, 0.3, 0.6, 0.6),
        "launch": (1, 0.3, 0.6, 0.6),
        "consideration": (0.3, 1, 1, 0.3),
        "conversion": (0.3, 1, 1, 0.4),
        "trend response": (0.6, 0.2, 0.3, 1),
    }
    return dict(zip(CAPABILITIES, values[objective.lower()]))


def validate_controls(weights, priorities):
    def valid(values):
        return all(
            isinstance(v, (int, float))
            and not isinstance(v, bool)
            and math.isfinite(v)
            and v >= 0
            for v in values
        )

    if (
        set(weights) != set(DIMENSIONS)
        or not valid(weights.values())
        or sum(weights.values()) <= 0
    ):
        raise ValueError(
            "weights must contain all six dimensions and have a positive non-negative total"
        )
    if (
        set(priorities) != set(CAPABILITIES)
        or not valid(priorities.values())
        or any(v > 1 for v in priorities.values())
    ):
        raise ValueError(
            "Reach, Demonstration, Credibility, Speed priorities must be between 0 and 1"
        )


def audit_controls(weights, priorities, actor="system"):
    validate_controls(weights, priorities)
    return {
        "weights": dict(weights),
        "capability_priorities": dict(priorities),
        "actor": actor,
        "changed_at": datetime.now(timezone.utc).isoformat(),
    }

"""Model output shape shared by Gemini constraints and local validation."""

import math
from copy import deepcopy

from jsonschema import Draft202012Validator


def obj(**properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def array(items):
    return {"type": "array", "items": items}


TEXT = {"type": "string"}
UNIT = {"type": "number", "minimum": 0, "maximum": 1}
EVIDENCE = array(obj(video_id=TEXT, quote=TEXT))
JUDGMENT_SCHEMA = obj(
    audience=obj(
        score=UNIT,
        reason=TEXT,
        quotes=array(obj(comment_id=TEXT, video_id=TEXT, quote=TEXT)),
    ),
    brand_fit=obj(
        score=UNIT,
        reason=TEXT,
        mismatch_direction=TEXT,
        consistency=TEXT,
        evidence=EVIDENCE,
    ),
    safety=obj(
        status={"type": "string", "enum": ["PASS", "REVIEW", "FAIL"]},
        reason=TEXT,
        evidence=EVIDENCE,
    ),
    capabilities=obj(
        expertise=UNIT, demonstration_video_ids=array(TEXT), evidence=EVIDENCE
    ),
    trend_matches=array(
        obj(
            topic=TEXT,
            campaign_relevance=UNIT,
            creator_proximity=UNIT,
            video_ids=array(TEXT),
        )
    ),
)


def schema_for_trends(snapshot):
    schema = deepcopy(JUDGMENT_SCHEMA)
    topics = list(dict.fromkeys(t["topic"] for t in (snapshot or {}).get("trends", [])))
    matches = schema["properties"]["trend_matches"]
    if topics:
        matches["items"]["properties"]["topic"] = {"type": "string", "enum": topics}
    else:
        matches["maxItems"] = 0
    return schema


def validate_judgment(result, schema=None):
    # JSON Schema considers NaN a number, so reject nonfinite values explicitly.
    def finite(value, path):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"{path}: expected finite number; got {value!r}")
        if isinstance(value, dict):
            for key, child in value.items():
                finite(child, f"{path}.{key}")
        elif isinstance(value, list):
            for i, child in enumerate(value):
                finite(child, f"{path}[{i}]")

    finite(result, "judgment")
    error = next(
        Draft202012Validator(schema or JUDGMENT_SCHEMA).iter_errors(result), None
    )
    if error:
        path = "judgment" + "".join(
            f"[{p}]" if isinstance(p, int) else f".{p}" for p in error.absolute_path
        )
        value = repr(error.instance)
        if len(value) > 160:
            value = value[:157] + "..."
        raise ValueError(f"{path}: failed {error.validator} constraint; got {value}")

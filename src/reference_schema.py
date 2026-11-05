"""Limit selectable references to the evidence actually sent to the model."""

from copy import deepcopy


def bind_references(schema, metadata, comments, passages):
    schema = deepcopy(schema)
    props = schema["properties"]
    videos = list(
        dict.fromkeys(
            m["video_id"] for m in metadata if m["video_id"] != "channel-description"
        )
    )
    comment_ids = list(dict.fromkeys(c["comment_id"] for c in comments))
    passage_ids = list(dict.fromkeys(p["passage_id"] for p in passages))

    def bind(array, allowed, field=None):
        value = {"type": "string"}
        if allowed:
            value["enum"] = allowed
        else:
            array["maxItems"] = 0
        if field:
            array["items"]["properties"][field] = value
        else:
            array["items"] = value

    bind(props["audience"]["properties"]["quotes"], comment_ids, "comment_id")
    for section in ("brand_fit", "safety", "capabilities"):
        bind(props[section]["properties"]["evidence"], passage_ids, "passage_id")
    bind(props["capabilities"]["properties"]["demonstration_video_ids"], videos)
    trend_videos = props["trend_matches"]["items"]["properties"]["video_ids"]
    bind(trend_videos, videos)
    if videos:
        trend_videos["minItems"] = 1
    else:
        props["trend_matches"]["maxItems"] = 0
    return schema

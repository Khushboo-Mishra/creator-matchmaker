"""Offline reference checks for previously validated evaluation cache entries."""

from copy import deepcopy
from .checkpoint import digest
from .evaluation import prefilter, unit


def validate_cached_evaluations(records, campaign, trends, min_comments):
    entries = {name: record for name, record in records}

    def lookup(stage, inputs):
        key = digest({"stage": stage, "inputs": inputs})
        return entries.get(stage + "-" + key + ".json")

    def embed(text):
        record = lookup("embedding", text)
        if record is None:
            raise ValueError(
                "Missing embedding needed for offline evidence verification"
            )
        return record["value"]

    verified = set()
    for name, record in records:
        if not name.startswith("channel-"):
            continue
        channel = deepcopy(record["value"])
        comments = lookup("comments", channel)
        if comments is None:
            continue
        channel["comment_records"] = comments["value"]
        evaluation = lookup("evaluation", channel)
        if evaluation is None:
            continue
        result = evaluation["value"]
        videos = {v["video_id"]: v for v in channel["videos"][:15]}
        metadata = {
            k: v.get("title", "") + " " + v.get("description", "")
            for k, v in videos.items()
        }
        metadata["channel-description"] = channel.get("description", "")
        usable, seen = [], set()
        for c in channel["comment_records"]:
            if (
                c.get("comment_id")
                and c.get("video_id") in videos
                and c.get("text", "").strip()
                and c["comment_id"] not in seen
            ):
                seen.add(c["comment_id"])
                usable.append(c)
        selected = (
            prefilter(
                usable, campaign.audience + " " + campaign.product_description, embed
            )
            if usable
            else []
        )
        by_id = {c["comment_id"]: c for c in selected}
        audience = result["dimensions"]["audience_relevance"]
        if (audience["score"] is None) != (len(usable) < min_comments):
            raise ValueError("Cached audience missing-evidence state is inconsistent")
        if audience["score"] is not None:
            unit(audience["score"])
        for quote in audience["evidence"]:
            source = by_id.get(quote["comment_id"])
            if (
                source is None
                or quote["video_id"] != source["video_id"]
                or not quote["quote"].strip()
                or quote["quote"] not in source["text"]
            ):
                raise ValueError(
                    "Cached audience evidence references unsupported source"
                )
        if (
            audience["score"] is not None
            and audience["score"] > 0.2
            and not audience["evidence"]
        ):
            raise ValueError("Cached audience lacks positive-match evidence")
        brand = result["dimensions"]["brand_fit"]
        if brand["score"] is not None:
            unit(brand["score"])
            if not brand["evidence"]:
                raise ValueError("Cached brand fit lacks evidence")
        for evidence in (
            brand["evidence"],
            result["safety_evidence"],
            result["capability_evidence"],
        ):
            for quote in evidence:
                if (
                    quote["video_id"] not in metadata
                    or not quote["quote"].strip()
                    or quote["quote"] not in metadata[quote["video_id"]]
                ):
                    raise ValueError(
                        "Cached metadata evidence references unsupported source"
                    )
        signals = result["capability_signals"]
        unit(signals["expertise"])
        if set(signals["demonstration_video_ids"]) - set(videos):
            raise ValueError("Cached demonstration IDs reference unsupported videos")
        if (
            signals["expertise"] > 0 or signals["demonstration_video_ids"]
        ) and not result["capability_evidence"]:
            raise ValueError("Cached capability lacks evidence")
        known = {t["topic"] for t in (trends or {}).get("trends", [])}
        for match in result["dimensions"]["trend_fit"]["evidence"]:
            if (
                match["topic"] not in known
                or not match["video_ids"]
                or set(match["video_ids"]) - set(videos)
            ):
                raise ValueError(
                    "Cached trend evidence references unsupported topic or video"
                )
            unit(match["campaign_relevance"])
            unit(match["creator_proximity"])
        verified.add(evaluation["key"])
    expected = {r["key"] for n, r in records if n.startswith("evaluation-")}
    if verified != expected:
        raise ValueError(
            "Cannot bind every cached evaluation to collected channel evidence"
        )
    return len(verified)

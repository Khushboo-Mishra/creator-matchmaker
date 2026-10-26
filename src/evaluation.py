"""Evidence contracts shared by live and explicitly synthetic providers."""

import math
from datetime import datetime
from urllib.parse import urlparse
from statistics import median


def unit(value):
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or not 0 <= value <= 1
    ):
        raise ValueError("Expected finite score between 0 and 1")
    return float(value)


def cosine(left, right):
    if not left or len(left) != len(right):
        raise ValueError("Invalid embedding dimensions")
    if not all(math.isfinite(x) for x in (*left, *right)):
        raise ValueError("Nonfinite embeddings")
    denom = math.sqrt(sum(x * x for x in left) * sum(x * x for x in right))
    return sum(x * y for x, y in zip(left, right)) / denom if denom else 0


def prefilter(comments, audience, embed, limit=60):
    query = embed(audience)
    scored = [(cosine(query, embed(c["text"])), c) for c in comments]
    return [
        dict(c, embedding_similarity=s)
        for s, c in sorted(scored, key=lambda x: -x[0])[:limit]
    ]


def mean_embedding(texts, embed):
    vectors = [embed(text) for text in texts if text.strip()]
    if not vectors:
        return None
    if any(len(v) != len(vectors[0]) for v in vectors):
        raise ValueError("Inconsistent embedding dimensions")
    return [sum(v[i] for v in vectors) / len(vectors) for i in range(len(vectors[0]))]


def dimension(score, reason, evidence=None, **extra):
    return {"score": score, "reason": reason, "evidence": evidence or [], **extra}


def valid_trends(snapshot, at):
    if snapshot is None:
        return None
    stamp = datetime.fromisoformat(snapshot["fetched_at"].replace("Z", "+00:00"))
    if stamp.tzinfo is None or stamp > at:
        raise ValueError(
            "Trend snapshot must have a nonfuture timezone-aware timestamp"
        )
    if snapshot.get("source") != "Google Trends":
        raise ValueError(
            "Trend confirmation requires Google Trends, not Search citations"
        )
    for trend in snapshot["trends"]:
        if urlparse(trend["source_url"]).hostname != "trends.google.com":
            raise ValueError("Trend source must be trends.google.com")
        before, after = trend["previous_interest"], trend["recent_interest"]
        if not all(
            isinstance(x, (float, int)) and math.isfinite(x) and 0 <= x <= 100
            for x in (before, after)
        ):
            raise ValueError("Trend interest values must be 0-100")
        if after <= before or not trend.get("window") or not trend.get("geo"):
            raise ValueError(
                "Verified trend must be rising with a time window and geography"
            )
    return snapshot


def evaluate(channel, campaign, provider, trend_snapshot, min_comments=10):
    """Only sourced comments count; legacy text-only comments cannot be cited."""
    videos = {v["video_id"]: v for v in channel["videos"][:15]}
    metadata = [
        {
            "video_id": v["video_id"],
            "text": v.get("title", "") + " " + v.get("description", ""),
        }
        for v in videos.values()
    ]
    metadata.append(
        {"video_id": "channel-description", "text": channel.get("description", "")}
    )
    comments = []
    seen = set()
    for c in channel.get("comment_records", []):
        if (
            c.get("comment_id")
            and c.get("video_id") in videos
            and c.get("text", "").strip()
            and c["comment_id"] not in seen
        ):
            comments.append(c)
            seen.add(c["comment_id"])
    selected = (
        prefilter(
            comments,
            campaign.audience + " " + campaign.product_description,
            provider.embed,
        )
        if comments
        else []
    )
    result = provider.judge(campaign, metadata, selected, trend_snapshot)
    counts = {
        "sampled": len(channel.get("comment_records", [])),
        "usable": len(comments),
        "prefiltered": len(selected),
        "cited": 0,
    }
    by_id = {c["comment_id"]: c for c in selected}
    quotes = result["audience"]["quotes"]
    for quote in quotes:
        source = by_id.get(quote["comment_id"])
        if (
            source is None
            or quote["video_id"] != source["video_id"]
            or quote["quote"] not in source["text"]
            or not quote["quote"].strip()
        ):
            raise ValueError("Audience quote not supported by supplied source comment")
        quote["url"] = (
            f"https://www.youtube.com/watch?v={source['video_id']}&lc={source['comment_id']}"
        )
    counts["cited"] = len({q["comment_id"] for q in quotes})
    if len(comments) < min_comments:
        audience = dimension(
            None, "Too few sourced comments to evaluate", counts=counts
        )
    else:
        score = unit(result["audience"]["score"])
        if score > 0.2 and not quotes:
            raise ValueError("Positive audience match requires sourced quotes")
        audience = dimension(score, result["audience"]["reason"], quotes, counts=counts)
    # Every metadata assertion must cite supplied text, not imagined video contents.
    for section in ("brand_fit", "safety", "capabilities"):
        for item in result[section]["evidence"]:
            source = next(
                (m["text"] for m in metadata if m["video_id"] == item["video_id"]), None
            )
            if (
                source is None
                or not item["quote"].strip()
                or item["quote"] not in source
            ):
                raise ValueError(f"Unsupported {section} metadata evidence")
    fit = result["brand_fit"]
    enough_metadata = sum(len(m["text"].strip()) for m in metadata) >= 120
    fit_score = unit(fit["score"]) if enough_metadata else None
    if fit_score is not None and not fit["evidence"]:
        raise ValueError("Brand Fit requires metadata evidence")
    brand = dimension(
        fit_score,
        fit["reason"] if enough_metadata else "Insufficient titles/descriptions",
        fit["evidence"],
        mismatch_direction=fit["mismatch_direction"],
        consistency=fit["consistency"],
    )
    safety = result["safety"]
    if safety["status"] not in {"PASS", "REVIEW", "FAIL"}:
        raise ValueError("Invalid safety status")
    if safety["status"] != "PASS" and not safety["evidence"]:
        raise ValueError("Safety concern requires evidence")
    flags = []
    metadata_text = (
        " ".join(m["text"] for m in metadata) + " " + channel.get("description", "")
    )
    for key in ("banned_phrases", "category_exclusions", "competitors"):
        for phrase in campaign.brand_requirements[key]:
            if phrase.casefold() in metadata_text.casefold():
                flags.append({"requirement": key, "phrase": phrase})
    # Literal mentions may be quotation or criticism; flag for review, never infer wrongdoing.
    status = safety["status"]
    if (flags or not enough_metadata) and status == "PASS":
        status = "REVIEW"
    capabilities = result["capabilities"]
    expertise = unit(capabilities["expertise"])
    format_ids = set(capabilities["demonstration_video_ids"])
    if format_ids - set(videos):
        raise ValueError("Demonstration formats must reference supplied videos")
    if (format_ids or expertise > 0) and not capabilities["evidence"]:
        raise ValueError("Capabilities require metadata evidence")
    demos = [
        v["views"]
        for k, v in videos.items()
        if k in format_ids and v.get("views") is not None
    ]
    others = [
        v["views"]
        for k, v in videos.items()
        if k not in format_ids and v.get("views") is not None
    ]
    format_lift = (
        median(demos) / median(others) if demos and others and median(others) else None
    )
    comment_depth = (
        median(len(c["text"].split()) for c in comments) if comments else None
    )
    if trend_snapshot is None:
        trend = dimension(
            None, "Google Trends verification unavailable", flag="TREND_UNAVAILABLE"
        )
    else:
        known = {t["topic"]: t for t in trend_snapshot["trends"]}
        matches = result["trend_matches"]
        values, evidence = [], []
        for m in matches:
            if (
                m["topic"] not in known
                or any(v not in videos for v in m["video_ids"])
                or not m["video_ids"]
            ):
                raise ValueError(
                    "Trend match must cite verified topic and supplied videos"
                )
            values.append(unit(m["campaign_relevance"]) * unit(m["creator_proximity"]))
            evidence.append(dict(m, source=known[m["topic"]]))
        trend = dimension(
            max(values, default=0),
            (
                "Verified trend alignment"
                if values
                else "No match to verified rising topics"
            ),
            evidence,
            flag=None if values else "NO_TREND_MATCH",
            snapshot_at=trend_snapshot["fetched_at"],
        )
    content_proxy = mean_embedding(
        [m["text"] for m in metadata if m["video_id"] != "channel-description"],
        provider.embed,
    )
    comment_proxy = mean_embedding([c["text"] for c in comments], provider.embed)
    return {
        "dimensions": {
            "audience_relevance": audience,
            "brand_fit": brand,
            "trend_fit": trend,
        },
        "brand_safety": status,
        "safety_evidence": safety["evidence"],
        "safety_reason": safety["reason"],
        "safety_scope": "Metadata only; no video/audio review",
        "safety_flags": flags,
        "capability_signals": {
            "format_lift": format_lift,
            "comment_depth": comment_depth,
            "expertise": expertise,
            "demonstration_video_ids": sorted(format_ids),
        },
        "capabilities": {},
        "capability_evidence": capabilities["evidence"],
        "content_embedding": content_proxy,
        "comment_embedding": comment_proxy,
    }

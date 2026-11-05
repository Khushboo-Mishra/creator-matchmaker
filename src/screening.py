"""Deterministic discovery/screening combination and measurable gates."""

from datetime import datetime
from math import isfinite, log
from statistics import median


def additive_screen(discovery_relevance, screening_score):
    """Combine normalized discovery evidence (40%) and screening (60%)."""
    return round(
        0.40 * max(0, min(1, discovery_relevance))
        + 0.60 * max(0, min(1, screening_score)),
        4,
    )


def usable_videos(channel, at):
    videos = []
    for video in channel.get("videos", []):
        try:
            date = datetime.fromisoformat(video["published_at"].replace("Z", "+00:00"))
            stats = [video.get(k) for k in ("views", "likes", "comments")]
            if (
                date <= at
                and all(
                    isinstance(x, (float, int))
                    and not isinstance(x, bool)
                    and isfinite(x)
                    and x >= 0
                    for x in stats
                )
                and video["views"] > 0
            ):
                videos.append(video)
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(videos, key=lambda v: v["published_at"], reverse=True)


def measurable_gates(channel, at):
    videos = usable_videos(channel, at)
    reasons = []
    if not channel.get("channel_id"):
        reasons.append("Channel could not be resolved")
    if len(videos) < 8:
        reasons.append("Fewer than 8 uploads with usable statistics")
    if (
        not videos
        or (
            at
            - datetime.fromisoformat(videos[0]["published_at"].replace("Z", "+00:00"))
        ).days
        > 180
    ):
        reasons.append("No usable upload within 180 days")
    return reasons


def raw_metrics(channel, at):
    videos = usable_videos(channel, at)
    window = videos[:15]
    rates = [(v["likes"] + v["comments"]) / v["views"] for v in window]
    # 8-14 uploads use all available prior uploads; counts remain visible.
    recent, prior = window[:5], window[5:]
    denominator = median(v["views"] for v in prior) if prior else 0
    return {
        "engagement": sum(rates) / len(rates) if rates else None,
        "momentum": (
            median(v["views"] for v in recent) / denominator if denominator else None
        ),
        "speed_to_activate": sum(
            0
            <= (
                at - datetime.fromisoformat(v["published_at"].replace("Z", "+00:00"))
            ).days
            <= 90
            for v in videos
        ),
        "median_views": median(v["views"] for v in window) if window else None,
        "usable_uploads": len(videos),
        "recent_count": len(recent),
        "prior_count": len(prior),
    }


def relative(value, population):
    if value is None:
        return None
    values = [v for v in population if v is not None]
    low, high = min(values), max(values)
    return 0.5 if low == high else (value - low) / (high - low)


def discovery_relevance(matches, cap=4):
    best = {}
    for match in matches:
        rank = match.get("rank")
        if not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
            raise ValueError("Discovery evidence requires positive 1-based ranks")
        query = match["query"]
        best[query] = max(best.get(query, 0), 1 / log(rank + 1))
    return sum(sorted(best.values(), reverse=True)[:cap])


def screen(channels, at):
    records, excluded = [], []
    for channel in channels:
        reasons = measurable_gates(channel, at)
        if reasons:
            excluded.append(
                {"channel_id": channel.get("channel_id"), "reasons": reasons}
            )
            continue
        records.append(
            {
                "channel": channel,
                "raw": raw_metrics(channel, at),
                "relevance": discovery_relevance(
                    channel.get("discovery", {}).get("matches", [])
                ),
            }
        )
    for record in records:
        normalized = {
            d: relative(record["raw"][d], [r["raw"][d] for r in records])
            for d in ("engagement", "momentum", "speed_to_activate")
        }
        record["normalized_health_components"] = normalized
        record["health"] = (
            0.4 * normalized["engagement"]
            + 0.4 * normalized["momentum"]
            + 0.2 * normalized["speed_to_activate"]
        )
        record["screening_score"] = additive_screen(
            relative(record["relevance"], [r["relevance"] for r in records]),
            record["health"],
        )
    ranked = sorted(
        records, key=lambda r: (-r["screening_score"], r["channel"]["channel_id"])
    )
    selected = ranked[:15]
    for r in selected:
        r["selection_reason"] = "Top combined discovery and health"
    remaining = ranked[15:]
    for i in range(min(5, len(remaining))):
        dimension = ("engagement", "momentum", "speed_to_activate")[i % 3]
        winner = max(
            remaining, key=lambda r: r["normalized_health_components"][dimension]
        )
        winner["selection_reason"] = f"{dimension} specialist"
        selected.append(winner)
        remaining.remove(winner)
    return selected, {"excluded": excluded, "eligible": records}

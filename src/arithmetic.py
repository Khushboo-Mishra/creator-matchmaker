"""The three dimensions that need no model at all.

Owner: data lane.

Median, never mean: one viral video should not rescue a dead channel.
Scores are normalised against FIXED anchors, not against the candidate pool.
Pool-relative normalisation would mean adding one channel silently changes
everyone else's score, which is indefensible when someone asks why a ranking moved.
"""
import statistics
from datetime import datetime, timezone

# Fixed anchors. A value at or above the anchor scores 10.
ENGAGEMENT_ANCHOR = 0.08      # (likes + comments) / views
MOMENTUM_ANCHOR = 1.8         # recent median views / prior median views
UPLOADS_90D_ANCHOR = 26       # roughly twice a week


def _clamp10(value, anchor):
    return round(max(0.0, min(10.0, (value / anchor) * 10)), 2)


def engagement(videos):
    """(likes + comments) / views, averaged over recent uploads.

    Falls with channel size, so a large channel will always score lower here.
    Either keep that as a deliberate bias toward mid-size creators or normalise
    within a size tier, but say which one in the write-up.
    """
    rates = [
        (v["likes"] + v["comments"]) / v["views"]
        for v in videos
        if v.get("views")
    ]
    if not rates:
        return 0.0, "no videos with view counts"
    mean_rate = sum(rates) / len(rates)
    return (
        _clamp10(mean_rate, ENGAGEMENT_ANCHOR),
        f"{mean_rate*100:.2f}% engagement across the last {len(rates)} uploads",
    )


def momentum(videos):
    """Median views of the last 5 uploads over the median of the 10 before."""
    if len(videos) < 15:
        return 0.0, f"needs 15 uploads to compare, found {len(videos)}"
    recent = statistics.median(v["views"] for v in videos[:5])
    prior = statistics.median(v["views"] for v in videos[5:15])
    if prior == 0:
        return 0.0, "no prior views to compare against"
    ratio = recent / prior
    direction = "rising" if ratio > 1 else "fading"
    return (
        _clamp10(ratio, MOMENTUM_ANCHOR),
        f"last 5 uploads median {ratio:.2f}x the previous 10, {direction}",
    )


def speed_to_activate(videos):
    """Uploads in the last 90 days. Weekly posters can react to a trend, monthly cannot."""
    now = datetime.now(timezone.utc)
    count = 0
    for v in videos:
        published = datetime.fromisoformat(v["published_at"].replace("Z", "+00:00"))
        if (now - published).days <= 90:
            count += 1
    return (
        _clamp10(count, UPLOADS_90D_ANCHOR),
        f"{count} uploads in the last 90 days",
    )


def compute(channel_record):
    """Return the three arithmetic dimensions in the shape scores.schema.json expects."""
    videos = channel_record.get("videos", [])
    out = {}
    for name, fn in (
        ("engagement", engagement),
        ("momentum", momentum),
        ("speed_to_activate", speed_to_activate),
    ):
        score, reason = fn(videos)
        out[name] = {"score": score, "reason": reason, "source": "arithmetic", "evidence": []}
    return out

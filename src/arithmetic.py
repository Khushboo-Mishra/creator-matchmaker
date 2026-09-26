"""The three dimensions that need no model at all.

Owner: data lane.

A dimension that cannot be computed returns None, never 0.0. Zero is a real
score meaning "measured, and bad"; None means "not measurable on this channel".
Collapsing the two made a nine-upload channel rank as if it were dying.
rank_correlation.tool_ranking() skips None and renormalises the weights, so a
channel is ranked on the dimensions it does have.

Medians for view counts: one viral video should not rescue a dead channel.
Engagement is the exception and is a mean, because it averages per-video RATES,
which are already bounded and far less spiky than raw views. Say so if asked.
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

# pull.py caches 50 uploads. Rate and trend dimensions read a fixed 15-upload
# window so the number means the same thing on every channel; only
# speed_to_activate reads the full cache, because it is a frequency count and
# a 15-upload cap made it impossible to score above 5.8.
RATE_WINDOW = 15
MOMENTUM_RECENT = 5
MOMENTUM_PRIOR = 10


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
        for v in videos[:RATE_WINDOW]
        if v.get("views")
    ]
    if not rates:
        return None, "not measurable: no uploads with view counts"
    mean_rate = sum(rates) / len(rates)
    return (
        _clamp10(mean_rate, ENGAGEMENT_ANCHOR),
        f"{mean_rate*100:.2f}% engagement across the last {len(rates)} uploads",
    )


def momentum(videos):
    """Median views of the last 5 uploads over the median of the 10 before."""
    if len(videos) < RATE_WINDOW:
        return None, (
            f"not measurable: needs {RATE_WINDOW} uploads to compare, "
            f"found {len(videos)}"
        )
    recent = statistics.median(v["views"] for v in videos[:MOMENTUM_RECENT])
    prior = statistics.median(
        v["views"] for v in videos[MOMENTUM_RECENT:RATE_WINDOW]
    )
    if prior == 0:
        return None, "not measurable: no prior views to compare against"
    ratio = recent / prior
    direction = "rising" if ratio > 1 else "fading"
    return (
        _clamp10(ratio, MOMENTUM_ANCHOR),
        f"last {MOMENTUM_RECENT} uploads median {ratio:.2f}x "
        f"the previous {MOMENTUM_PRIOR}, {direction}",
    )


def speed_to_activate(videos):
    """Uploads in the last 90 days. Weekly posters can react to a trend, monthly cannot.

    Reads every cached upload, not the 15-upload window the rate dimensions use:
    a frequency count capped at 15 cannot reach its own anchor of 26.
    """
    if not videos:
        return None, "not measurable: no uploads cached"
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

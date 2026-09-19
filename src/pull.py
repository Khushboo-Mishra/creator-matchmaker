"""Pull channel data from the YouTube Data API into data/channels/<handle>.json.

Owner: data lane.

Quota notes, read before editing:
  search.list has its own small daily bucket and is NOT used here on purpose.
  channels.list, playlistItems.list, videos.list and commentThreads.list each
  cost 1 unit against a separate pool, so resolving by handle is far cheaper
  than searching. Never re-pull during a live demo: read the cached JSON.

  We pull 50 uploads, not 15. A playlistItems page costs 1 unit whether it
  returns 1 item or 50, and videos.list takes 50 ids in a single call, so the
  wider window is free. It is needed because speed_to_activate counts uploads
  in the last 90 days: capped at 15, a daily poster and a twice-weekly poster
  scored identically. Scoring windows live in arithmetic.py, not here.

Usage:
    python -m src.pull            # every handle in data/handles.txt
    python -m src.pull @somebody  # one handle
"""
import json
import re
import sys
from datetime import datetime, timezone

import requests

from .config import CHANNELS, YOUTUBE_API_KEY, read_handles

API = "https://www.googleapis.com/youtube/v3"
RECENT_VIDEOS = 50
COMMENT_VIDEOS = 3
COMMENTS_PER_VIDEO = 40


def _get(endpoint, **params):
    params["key"] = YOUTUBE_API_KEY
    r = requests.get(f"{API}/{endpoint}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def resolve_channel(handle):
    """Handle to channel metadata. 1 quota unit."""
    data = _get(
        "channels",
        part="snippet,statistics,contentDetails",
        forHandle=handle.lstrip("@"),
    )
    items = data.get("items") or []
    if not items:
        raise LookupError(f"no channel for handle {handle}")
    return items[0]


def recent_video_ids(uploads_playlist_id, limit=RECENT_VIDEOS):
    """Newest uploads from the uploads playlist, newest first. 1 unit per page of 50."""
    data = _get(
        "playlistItems",
        part="contentDetails",
        playlistId=uploads_playlist_id,
        maxResults=min(limit, 50),
    )
    return [i["contentDetails"]["videoId"] for i in data.get("items", [])]


_DURATION = re.compile(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def _duration_seconds(iso):
    """ISO 8601 duration to whole seconds. Declared in channel.schema.json."""
    m = _DURATION.fullmatch(iso or "")
    if not m:
        return 0
    days, hours, minutes, seconds = (int(g or 0) for g in m.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def video_details(video_ids):
    """Up to 50 videos in a single call. 1 unit."""
    if not video_ids:
        return []
    data = _get(
        "videos",
        part="snippet,statistics,contentDetails",
        id=",".join(video_ids),
    )
    out = []
    for item in data.get("items", []):
        stats = item.get("statistics", {})
        out.append(
            {
                "video_id": item["id"],
                "duration_seconds": _duration_seconds(
                    item.get("contentDetails", {}).get("duration", "")
                ),
                "title": item["snippet"]["title"],
                "description": item["snippet"].get("description", ""),
                "published_at": item["snippet"]["publishedAt"],
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "url": f"https://www.youtube.com/watch?v={item['id']}",
            }
        )
    return out


def sample_comments(videos, n_videos=COMMENT_VIDEOS, per_video=COMMENTS_PER_VIDEO):
    """Top-level comments from the highest-view videos. 1 unit per video."""
    top = sorted(videos, key=lambda v: v["views"], reverse=True)[:n_videos]
    out = []
    for v in top:
        try:
            data = _get(
                "commentThreads",
                part="snippet",
                videoId=v["video_id"],
                maxResults=per_video,
                order="relevance",
                textFormat="plainText",
            )
        except requests.HTTPError:
            continue  # comments disabled is common and not an error worth stopping for
        for item in data.get("items", []):
            out.append(
                item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]
            )
    return out


def pull(handle):
    ch = resolve_channel(handle)
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    videos = video_details(recent_video_ids(uploads))
    record = {
        "handle": handle,
        "channel_id": ch["id"],
        "title": ch["snippet"]["title"],
        "description": ch["snippet"].get("description", ""),
        "subscribers": int(ch["statistics"].get("subscriberCount", 0)),
        "uploads_playlist_id": uploads,
        "pulled_at": datetime.now(timezone.utc).isoformat(),
        "videos": videos,
        "sampled_comments": sample_comments(videos),
    }
    CHANNELS.mkdir(parents=True, exist_ok=True)
    path = CHANNELS / f"{handle.lstrip('@')}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
    return path


def main():
    handles = sys.argv[1:] or read_handles()
    for h in handles:
        try:
            print(f"ok   {h} -> {pull(h).name}")
        except Exception as exc:  # keep going, one bad handle should not stop a batch
            print(f"fail {h}: {exc}")


if __name__ == "__main__":
    main()

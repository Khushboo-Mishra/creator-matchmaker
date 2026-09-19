"""Pull channel data from the YouTube Data API into data/channels/<channel_id>.json.

Owner: data lane.

Supports two input paths:
  1. Automatic discovery using channel IDs from discovered_candidates.json.
  2. Manual fallback using handles from data/handles.txt.

Never re-pull during a live demo: read the cached JSON.

Usage:
    python -m src.pull
        Pull automatically discovered candidates if available.

    python -m src.pull @somebody
        Pull one creator by handle.

    python -m src.pull UCxxxxxxxx
        Pull one creator by channel ID.
"""

import json
import sys
from datetime import datetime, timezone

import requests

from .config import (
    CHANNELS,
    DISCOVERED_FILE,
    YOUTUBE_API_KEY,
    read_handles,
)

API = "https://www.googleapis.com/youtube/v3"

RECENT_VIDEOS = 15
COMMENT_VIDEOS = 3
COMMENTS_PER_VIDEO = 40


def _get(endpoint, **params):
    params["key"] = YOUTUBE_API_KEY

    r = requests.get(
        f"{API}/{endpoint}",
        params=params,
        timeout=30,
    )

    r.raise_for_status()

    return r.json()


def resolve_channel(handle):
    """Handle to channel metadata."""

    data = _get(
        "channels",
        part="snippet,statistics,contentDetails",
        forHandle=handle.lstrip("@"),
    )

    items = data.get("items") or []

    if not items:
        raise LookupError(f"no channel for handle {handle}")

    return items[0]


def resolve_channel_id(channel_id):
    """Channel ID to channel metadata."""

    data = _get(
        "channels",
        part="snippet,statistics,contentDetails",
        id=channel_id,
    )

    items = data.get("items") or []

    if not items:
        raise LookupError(f"no channel for ID {channel_id}")

    return items[0]


def recent_video_ids(uploads_playlist_id, limit=RECENT_VIDEOS):
    """Newest uploads from the uploads playlist."""

    data = _get(
        "playlistItems",
        part="contentDetails",
        playlistId=uploads_playlist_id,
        maxResults=min(limit, 50),
    )

    return [
        item["contentDetails"]["videoId"]
        for item in data.get("items", [])
    ]


def video_details(video_ids):
    """Fetch details for up to 50 videos in one request."""

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


def sample_comments(
    videos,
    n_videos=COMMENT_VIDEOS,
    per_video=COMMENTS_PER_VIDEO,
):
    """Sample top-level comments from the highest-view videos."""

    top = sorted(
        videos,
        key=lambda video: video["views"],
        reverse=True,
    )[:n_videos]

    out = []

    for video in top:
        try:
            data = _get(
                "commentThreads",
                part="snippet",
                videoId=video["video_id"],
                maxResults=per_video,
                order="relevance",
                textFormat="plainText",
            )

        except requests.HTTPError:
            continue

        for item in data.get("items", []):
            out.append(
                item["snippet"]["topLevelComment"]["snippet"][
                    "textDisplay"
                ]
            )

    return out


def pull_channel(channel, discovery=None):
    """Build and cache one normalized channel record."""

    uploads = channel["contentDetails"]["relatedPlaylists"]["uploads"]

    videos = video_details(
        recent_video_ids(uploads)
    )

    snippet = channel["snippet"]

    record = {
        "channel_id": channel["id"],
        "title": snippet["title"],
        "description": snippet.get("description", ""),
        "subscribers": int(
            channel["statistics"].get("subscriberCount", 0)
        ),
        "uploads_playlist_id": uploads,
        "pulled_at": datetime.now(timezone.utc).isoformat(),
        "videos": videos,
        "sampled_comments": sample_comments(videos),
    }

    # Preserve the handle/custom URL when YouTube provides one.
    custom_url = snippet.get("customUrl")

    if custom_url:
        record["handle"] = custom_url
    else:
        record["handle"] = None

    # Preserve evidence explaining why automatic discovery found
    # this creator.
    if discovery is not None:
        record["discovery"] = {
            "matches": discovery.get("matches", [])
        }

    CHANNELS.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = CHANNELS / f"{channel['id']}.json"

    path.write_text(
        json.dumps(
            record,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return path


def pull_by_id(channel_id, discovery=None):
    """Pull one creator using the canonical YouTube channel ID."""

    channel = resolve_channel_id(channel_id)

    return pull_channel(
        channel,
        discovery=discovery,
    )


def pull_by_handle(handle):
    """Manual fallback: pull one creator using a YouTube handle."""

    channel = resolve_channel(handle)

    return pull_channel(channel)


def read_discovered_candidates():
    """Read the cached automatic discovery candidate pool."""

    if not DISCOVERED_FILE.exists():
        return []

    data = json.loads(
        DISCOVERED_FILE.read_text(
            encoding="utf-8"
        )
    )

    return data.get("candidates", [])


def main():
    supplied = sys.argv[1:]

    # Explicit command-line input.
    if supplied:
        for identifier in supplied:
            try:
                if identifier.startswith("@"):
                    path = pull_by_handle(identifier)
                else:
                    path = pull_by_id(identifier)

                print(
                    f"ok   {identifier} -> {path.name}"
                )

            except Exception as exc:
                print(
                    f"fail {identifier}: {exc}"
                )

        return

    # Automatic discovery is the primary workflow.
    discovered = read_discovered_candidates()

    if discovered:
        print(
            f"Using {len(discovered)} "
            "automatically discovered candidates."
        )

        for candidate in discovered:
            channel_id = candidate["channel_id"]

            try:
                path = pull_by_id(
                    channel_id,
                    discovery=candidate,
                )

                print(
                    f"ok   {candidate['channel_title']} "
                    f"-> {path.name}"
                )

            except Exception as exc:
                print(
                    f"fail {candidate['channel_title']}: "
                    f"{exc}"
                )

        return

    # Manual handles remain available as a fallback.
    print(
        "No discovery cache found. "
        "Falling back to data/handles.txt."
    )

    for handle in read_handles():
        try:
            path = pull_by_handle(handle)

            print(
                f"ok   {handle} -> {path.name}"
            )

        except Exception as exc:
            print(
                f"fail {handle}: {exc}"
            )


if __name__ == "__main__":
    main()
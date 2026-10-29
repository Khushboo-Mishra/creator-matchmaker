"""Automatically discover YouTube creator candidates from campaign rules."""

import json
import math
import time
import argparse
from datetime import datetime, timezone
from pathlib import Path

import requests

from .config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    RULES_FILE,
    YOUTUBE_API_KEY,
    DISCOVERED_FILE,
)


GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/"
    "v1beta/models/{model}:generateContent"
)

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"


QUERY_SCHEMA = {
    "type": "object",
    "properties": {
        "queries": {
            "type": "array",
            "items": {"type": "string"},
        }
    },
    "required": ["queries"],
}


def generate_search_queries(campaign=None):
    """Use Gemini to turn campaign rules into YouTube discovery queries."""

    rules_text = json.dumps(campaign.canonical(), ensure_ascii=False) if campaign else RULES_FILE.read_text()

    prompt = f"""
You are helping discover YouTube creators for a brand campaign.

CAMPAIGN RULES

{rules_text}

Generate 8 diverse YouTube search queries that could surface creators
whose content and audiences are relevant to this campaign.

Search for creator workflows, problems, and content topics rather than
the brand name itself.

Cover different relevant creator niches instead of producing minor
variations of the same query.

Return only the requested structured output.
"""

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": QUERY_SCHEMA,
            "temperature": 0.3,
        },
    }

    # Gemini can occasionally return a temporary 503 Service Unavailable.
    # Retry with exponential backoff before giving up.
    for attempt in range(4):
        response = requests.post(
            GEMINI_ENDPOINT.format(model=GEMINI_MODEL),
            headers={
                "x-goog-api-key": GEMINI_API_KEY,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=60,
        )

        if response.status_code != 503:
            break

        wait_seconds = 2 ** attempt
        print(f"Gemini unavailable. Retrying in {wait_seconds}s...")
        time.sleep(wait_seconds)

    response.raise_for_status()

    raw = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    result = json.loads(raw)

    return result["queries"]


def search_youtube(query, max_results=20):
    """Search YouTube videos for one discovery query."""

    response = requests.get(
        f"{YOUTUBE_API}/search",
        params={
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": max_results,
            "key": YOUTUBE_API_KEY,
        },
        timeout=30,
    )

    response.raise_for_status()

    return response.json().get("items", [])

def extract_candidates(search_results, query):
    """Convert YouTube video search results into creator candidates."""

    candidates = []

    for rank, item in enumerate(search_results, 1):
        candidate = {
            "channel_id": item["snippet"]["channelId"],
            "channel_title": item["snippet"]["channelTitle"],
            "matched_query": query,
            "matched_video_id": item["id"]["videoId"],
            "matched_video_title": item["snippet"]["title"],
            "rank": rank,
        }

        candidates.append(candidate)

    return candidates

def deduplicate_candidates(candidates):
    """Merge duplicate channels while preserving discovery evidence."""

    unique = {}

    for candidate in candidates:
        channel_id = candidate["channel_id"]

        match = {
            "query": candidate["matched_query"],
            "video_id": candidate["matched_video_id"],
            "video_title": candidate["matched_video_title"],
            "rank": candidate["rank"],
            "relevance_score": 1.0 / math.log(candidate["rank"] + 1),
        }

        if channel_id not in unique:
            unique[channel_id] = {
                "channel_id": channel_id,
                "channel_title": candidate["channel_title"].strip(),
                "matches": [],
            }

        if match not in unique[channel_id]["matches"]:
            unique[channel_id]["matches"].append(match)

    # Screening uses the best result for each query, with an additive 40/60
    # split between discovery relevance and later creator screening.
    for candidate in unique.values():
        by_query = {}
        for match in candidate["matches"]:
            by_query[match["query"]] = max(by_query.get(match["query"], 0), match["relevance_score"])
        candidate["discovery_relevance"] = sum(sorted(by_query.values(), reverse=True)[:4])

    return list(unique.values())

def discover_candidates(max_results_per_query=10, campaign=None):
    """Run campaign-driven creator discovery across all generated queries."""

    queries = list(dict.fromkeys(generate_search_queries(campaign)))
    all_candidates = []

    print(f"Generated {len(queries)} discovery queries.\n")

    for query in queries:
        print(f"Searching: {query}")

        results = search_youtube(
            query,
            max_results=max_results_per_query,
        )

        candidates = extract_candidates(results, query)
        all_candidates.extend(candidates)

        print(f"  Found {len(candidates)} video matches.")

    unique_candidates = deduplicate_candidates(all_candidates)

    print(
        f"\n{len(all_candidates)} video matches -> "
        f"{len(unique_candidates)} unique creator candidates."
    )

    return {
        "queries": queries,
        "candidates": unique_candidates,
    }

def main(argv=None):
    from .campaign import Campaign
    from .discovery_file import validate_discovery

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--output", default=str(DISCOVERED_FILE))
    args = parser.parse_args(argv)
    campaign = Campaign(**json.loads(Path(args.campaign).read_text(encoding="utf-8")))
    discovery = discover_candidates(max_results_per_query=10, campaign=campaign)
    discovery["campaign_fingerprint"] = campaign.fingerprint()
    discovery["discovered_at"] = datetime.now(timezone.utc).isoformat()
    validate_discovery(discovery, campaign)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(discovery, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\nSaved discovery results to {output}")


if __name__ == "__main__":
    main()

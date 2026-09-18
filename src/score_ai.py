"""The three dimensions that need judgement.

Owner: AI lane.

Develop this against a single file in data/channels/ committed by the data lane.
You do not need the full pull to exist before this works.

Three things that matter more than prompt wording:
  1. Force JSON. responseMimeType application/json plus a responseSchema.
  2. Every score carries a one-sentence reason, or the ranking cannot be defended.
  3. Calibrate with three hand-scored examples in the prompt, a 9, a 5 and a 2,
     each with the reasoning. This beats any amount of rewording.
"""
import json

import requests

from .config import GEMINI_API_KEY, GEMINI_MODEL, RULES_FILE

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        dim: {
            "type": "object",
            "properties": {
                "score": {"type": "number"},
                "reason": {"type": "string"},
            },
            "required": ["score", "reason"],
        }
        for dim in ("audience_relevance", "brand_fit", "trend_fit")
    },
    "required": ["audience_relevance", "brand_fit", "trend_fit"],
}

# TODO(ai lane): replace with three real hand-scored channels and your reasoning.
CALIBRATION = """
Examples of how to score, so your numbers stay consistent:

9  A channel whose comments are full of people asking which product was used, and
   whose last ten videos sit squarely in the category. Reason cites the comments.
5  A channel in an adjacent category with an audience that overlaps only partly.
   Reason names the overlap and the gap.
2  A channel with a large audience and no topical connection at all. Reason says
   plainly that reach is not relevance.
"""


def build_prompt(channel_record, rules_text):
    titles = "\n".join(f"- {v['title']}" for v in channel_record["videos"][:10])
    comments = "\n".join(f"- {c}" for c in channel_record.get("sampled_comments", [])[:60])
    return f"""You are scoring one YouTube channel as a candidate for a campaign.

CAMPAIGN RULES
{rules_text}

CHANNEL: {channel_record['title']} ({channel_record['handle']})
Subscribers: {channel_record['subscribers']}

RECENT VIDEO TITLES
{titles}

SAMPLED COMMENTS
{comments}

Score three dimensions 0 to 10:
  audience_relevance  Does this audience care about this product category?
                      Judge from the comments, not the subscriber count.
  brand_fit           Can this brand sit beside this content without risk?
                      Apply the banned claims and the tone in the rules above.
  trend_fit           Do the channel's recent subjects overlap with what is
                      currently rising in this category?

{CALIBRATION}

Give every score a single sentence of reasoning that cites something concrete
from the material above. Never invent a fact you were not given.
"""


def score(channel_record, rules_text=None):
    """Return the three model dimensions in the shape scores.schema.json expects."""
    rules_text = rules_text if rules_text is not None else RULES_FILE.read_text()
    body = {
        "contents": [{"parts": [{"text": build_prompt(channel_record, rules_text)}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
            "temperature": 0.2,
        },
    }
    r = requests.post(
        ENDPOINT.format(model=GEMINI_MODEL),
        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
        json=body,
        timeout=90,
    )
    r.raise_for_status()
    raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    parsed = json.loads(raw)
    return {
        dim: {
            "score": parsed[dim]["score"],
            "reason": parsed[dim]["reason"],
            "source": "model",
            "evidence": [],
        }
        for dim in ("audience_relevance", "brand_fit", "trend_fit")
    }

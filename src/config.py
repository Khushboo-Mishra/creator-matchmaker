"""Shared paths and environment. Import this rather than hardcoding paths."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CHANNELS = DATA / "channels"
SCORES = DATA / "scores"
HANDLES_FILE = DATA / "handles.txt"
# Written once by src/discover.py, committed, and read here. Not gitignored:
# it is an input, not pulled data.
DISCOVERED_FILE = DATA / "discovered_candidates.json"
RULES_FILE = ROOT / "config" / "rules.md"
# Grounded trend topics keyed by a hash of rules.md, so a build_scores run and a
# later stability.py run share one search call instead of re-grounding each time.
TREND_CACHE_FILE = DATA / "trend_cache.json"

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

DIMENSIONS = (
    "audience_relevance",
    "engagement",
    "brand_fit",
    "momentum",
    "speed_to_activate",
    "trend_fit",
)

ARITHMETIC_DIMENSIONS = ("engagement", "momentum", "speed_to_activate")
MODEL_DIMENSIONS = ("audience_relevance", "brand_fit", "trend_fit")


def read_handles():
    """Return handles from data/handles.txt, ignoring blanks and # comments."""
    out = []
    for line in HANDLES_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out

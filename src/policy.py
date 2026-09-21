"""Deterministic policy gate.

Owner: shared, touches build_scores.py, flag changes to the team before pushing.

Hard stops are reserved for checks backed by concrete evidence: a named
competitor, or a counted fraction of low-signal comments. Anything that needs
human judgement instead -- whether a sentence amounts to an unsupported claim,
whether a spoken disclosure happened on camera -- comes back as a warning, so
a wrong guess here can never silently disqualify a good channel.
"""
import re

SPONSOR_KEYWORDS = (
    "sponsored", "paid partnership", "affiliate link", "promo code",
    "in partnership with", "gifted by", "brand deal",
)

# Generic, low-signal comments. Not exhaustive, meant to catch the obvious bot filler.
GENERIC_COMMENTS = {
    "nice", "cool", "love this", "love it", "first", "amazing",
    "great video", "so good", "wow", "omg", "yes", "same", "fire",
}

EMOJI_PATTERN = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]+")

# Short, common words that would overlap by coincidence rather than by echoing a claim.
STOPWORDS = {
    "about", "after", "before", "claim", "claims", "creator", "creators",
    "genuinely", "other", "their", "these", "those", "unsupported", "using",
    "which", "while", "would", "could", "should",
}


def _section(rules_text, heading):
    """Body text under a '## heading' in rules.md, or '' if that heading is absent."""
    pattern = rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s+|\Z)"
    match = re.search(pattern, rules_text, re.MULTILINE | re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else ""


def _bullets(section_text):
    return [
        line.lstrip("-*").strip()
        for line in section_text.splitlines()
        if line.strip().startswith(("-", "*"))
    ]


def _keywords(text):
    """Distinctive words (5+ letters, minus common stopwords), for a soft overlap check."""
    return {w for w in re.findall(r"[a-z']+", text.lower()) if len(w) >= 5 and w not in STOPWORDS}


def _extract_banned_claims(rules_text):
    """Raw banned-claim bullets from rules.md.

    The real rules describe judgement calls ("unsupported claims about AI
    capabilities") that no string match can verify reliably, so these feed a
    soft keyword-overlap warning, never a hard stop.
    """
    return _bullets(_section(rules_text, "Banned claims"))


def _extract_competitors(rules_text):
    """Empty until rules.md gets a '## Competitors' section listing real names."""
    return [b.lower() for b in _bullets(_section(rules_text, "Competitors"))]


def _mentions_sponsorship(text):
    low = text.lower()
    return any(kw in low for kw in SPONSOR_KEYWORDS)


def _is_low_signal_comment(comment):
    stripped = comment.strip()
    if not stripped:
        return True
    without_emoji = EMOJI_PATTERN.sub("", stripped).strip()
    if not without_emoji:
        return True
    normalized = re.sub(r"[^\w\s]", "", without_emoji).strip().lower()
    return normalized in GENERIC_COMMENTS


def disclosure_warnings(videos):
    """Sponsored-looking videos, flagged for a human to confirm the required
    in-video spoken disclosure actually happened: that can't be read from text.
    """
    return [
        f'video {v.get("video_id", "?")} mentions a sponsorship; confirm the '
        "required spoken disclosure appears in the video itself"
        for v in videos
        if _mentions_sponsorship(f"{v.get('title', '')} {v.get('description', '')}")
    ]


def banned_claim_warnings(videos, rules_text):
    """Videos that share distinctive words with a banned-claims bullet.

    A soft signal for a human to check, not a hard stop: word overlap is not
    the same as verifying a claim was actually made.
    """
    warnings = []
    for bullet in _extract_banned_claims(rules_text):
        bullet_words = _keywords(bullet)
        if not bullet_words:
            continue
        for v in videos:
            text = f"{v.get('title', '')} {v.get('description', '')}"
            overlap = bullet_words & _keywords(text)
            if len(overlap) >= 2:
                warnings.append(
                    f'video {v.get("video_id", "?")} shares wording with a banned '
                    f'claim ("{bullet.strip().rstrip(".;")}"): {", ".join(sorted(overlap))}'
                )
    return warnings


def competitor_hard_stops(videos, rules_text):
    """Hard stop candidates, each with the evidence backing it: a named competitor."""
    hits = []
    for name in _extract_competitors(rules_text):
        for v in videos:
            text = f"{v.get('title', '')} {v.get('description', '')}".lower()
            if name and name in text:
                hits.append({
                    "reason": f'video {v.get("video_id", "?")} mentions competitor "{name}"',
                    "evidence": [v.get("video_id", "?")],
                })
    return hits


def fake_engagement_hard_stop(sampled_comments):
    """A hard stop candidate when most sampled comments are emoji-only or
    generic, with the offending comments as evidence. None if not triggered.
    """
    if not sampled_comments:
        return None
    low_signal = [c for c in sampled_comments if _is_low_signal_comment(c)]
    if len(low_signal) / len(sampled_comments) <= 0.5:
        return None
    return {
        "reason": f"{len(low_signal)}/{len(sampled_comments)} sampled comments are emoji-only or generic",
        "evidence": low_signal,
    }


def evaluate(channel_record, rules_text):
    """Run every deterministic check and merge the results.

    Combined with the model's own hard_stop in build_scores.py: either one
    stopping is enough to disqualify the channel. Warnings never disqualify;
    they're surfaced for a human to look at.
    """
    videos = channel_record.get("videos", [])

    hard_stops = list(competitor_hard_stops(videos, rules_text))
    fake = fake_engagement_hard_stop(channel_record.get("sampled_comments", []))
    if fake:
        hard_stops.append(fake)

    warnings = disclosure_warnings(videos) + banned_claim_warnings(videos, rules_text)

    return {
        "hard_stop": bool(hard_stops),
        "hard_stop_reason": "; ".join(h["reason"] for h in hard_stops) if hard_stops else None,
        "warnings": warnings,
    }


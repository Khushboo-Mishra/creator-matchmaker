"""Deterministic policy gate.

Owner: shared, touches build_scores.py, flag changes to the team before pushing.

Some disqualifications are more reliable and easier to defend on stage as plain
code than as model judgement. This reads the same config/rules.md src/score_ai.py
does, but decides purely with string matching, so a rejection can always be
explained in one sentence with no model in the loop.
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

# "Any claim that/about ..." style lead-ins stripped so the rest of the bullet
# can be matched as a phrase, since nobody writes video copy as full sentences.
LEAD_INS = ("any claim that ", "any claim about ", "any comparison naming ", "any implication that ")


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


def _extract_banned_phrases(rules_text):
    phrases = []
    for bullet in _bullets(_section(rules_text, "Banned claims")):
        low = bullet.lower()
        for lead in LEAD_INS:
            if low.startswith(lead):
                low = low[len(lead):]
                break
        phrases.append(low.rstrip("."))
    return phrases


def _extract_competitors(rules_text):
    """Empty until rules.md gets a '## Competitors' section listing real names."""
    return [b.lower() for b in _bullets(_section(rules_text, "Competitors"))]


def _looks_sponsored(description):
    low = description.lower()
    return any(kw in low for kw in SPONSOR_KEYWORDS)


def _has_disclosure(description):
    return description.strip().lower().startswith("#ad")


def _is_low_signal_comment(comment):
    stripped = comment.strip()
    if not stripped:
        return True
    without_emoji = EMOJI_PATTERN.sub("", stripped).strip()
    if not without_emoji:
        return True
    normalized = re.sub(r"[^\w\s]", "", without_emoji).strip().lower()
    return normalized in GENERIC_COMMENTS


def missing_disclosure(videos):
    """Sponsored-looking descriptions that don't open with #ad, per the disclosure rule."""
    return [
        f'video {v.get("video_id", "?")} looks sponsored but its description '
        "does not open with #ad"
        for v in videos
        if _looks_sponsored(v.get("description", "")) and not _has_disclosure(v.get("description", ""))
    ]


def banned_phrase_matches(videos, rules_text):
    """Titles or descriptions that match a banned claim from rules.md."""
    reasons = []
    phrases = _extract_banned_phrases(rules_text)
    for v in videos:
        text = f"{v.get('title', '')} {v.get('description', '')}".lower()
        for phrase in phrases:
            if phrase and phrase in text:
                reasons.append(f'video {v.get("video_id", "?")} matches a banned claim: "{phrase}"')
                break
    return reasons


def competitor_mentions(videos, rules_text):
    """Titles or descriptions naming a listed competitor."""
    reasons = []
    names = _extract_competitors(rules_text)
    for v in videos:
        text = f"{v.get('title', '')} {v.get('description', '')}".lower()
        for name in names:
            if name and name in text:
                reasons.append(f'video {v.get("video_id", "?")} mentions competitor "{name}"')
                break
    return reasons


def fake_engagement(sampled_comments):
    """A reason string when most sampled comments are emoji-only or generic, else None."""
    if not sampled_comments:
        return None
    low_signal = [c for c in sampled_comments if _is_low_signal_comment(c)]
    if len(low_signal) / len(sampled_comments) <= 0.5:
        return None
    return f"{len(low_signal)}/{len(sampled_comments)} sampled comments are emoji-only or generic"


def evaluate(channel_record, rules_text):
    """Run every deterministic check and merge them into one hard_stop decision.

    Combined with the model's own hard_stop in build_scores.py: either one
    stopping is enough to disqualify the channel.
    """
    videos = channel_record.get("videos", [])
    reasons = []
    reasons += missing_disclosure(videos)
    reasons += banned_phrase_matches(videos, rules_text)
    reasons += competitor_mentions(videos, rules_text)
    fake_reason = fake_engagement(channel_record.get("sampled_comments", []))
    if fake_reason:
        reasons.append(fake_reason)

    return {
        "hard_stop": bool(reasons),
        "hard_stop_reason": "; ".join(reasons) if reasons else None,
    }

"""Validate reusable discovery before any channel pulls."""


def validate_discovery(data, campaign):
    if not isinstance(data, dict):
        raise ValueError("Discovery must be a JSON object")
    if data.get("campaign_fingerprint") != campaign.fingerprint():
        raise ValueError(
            "Discovery campaign fingerprint missing or mismatched; rerun discovery with --campaign"
        )
    queries = data.get("queries")
    if (
        not isinstance(queries, list)
        or not queries
        or not all(isinstance(q, str) and q.strip() for q in queries)
    ):
        raise ValueError("Discovery requires nonempty query strings")
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("Discovery requires a nonempty candidate list")
    for candidate in candidates:
        if (
            not isinstance(candidate, dict)
            or not isinstance(candidate.get("channel_id"), str)
            or not candidate["channel_id"].strip()
        ):
            raise ValueError("Discovery candidate requires a channel_id")
        matches = candidate.get("matches")
        if not isinstance(matches, list) or not matches:
            raise ValueError("Discovery candidate requires query/rank provenance")
        for match in matches:
            if not isinstance(match, dict):
                raise ValueError("Invalid discovery match")
            rank = match.get("rank")
            if match.get("query") not in queries or type(rank) is not int or rank < 1:
                raise ValueError(
                    "Discovery match requires a known query and positive integer rank"
                )
    return data

"""Relative ranking, health gates, shortlist and roster selection."""

from .campaign import DIMENSIONS, CAPABILITIES, validate_controls
from copy import deepcopy
from .screening import relative


def weighted_score(channel, weights):
    validate_controls(weights, {k: 1 for k in CAPABILITIES})
    dims = channel.get("dimensions", channel)
    total = weight_sum = 0.0
    for dim in DIMENSIONS:
        value = (
            dims.get(dim, {}).get("score")
            if isinstance(dims.get(dim), dict)
            else dims.get(dim)
        )
        if value is not None:
            total += value * weights[dim]
            weight_sum += weights[dim]
    return round(total / weight_sum, 4) if weight_sum else None


def safety_gate(channel):
    status = channel.get("brand_safety", channel.get("safety", "REVIEW"))
    return status if status in {"PASS", "REVIEW", "FAIL"} else "REVIEW"


def select_roster(candidates, priorities, size=4):
    """Greedy quality .50 + coverage .35 - similarity .15; priorities stay continuous."""
    validate_controls({d: 1 for d in DIMENSIONS}, priorities)
    selected = []
    remaining = [
        c
        for c in candidates
        if safety_gate(c) != "FAIL" and c.get("combined_score") is not None
    ]
    while remaining and len(selected) < size:
        best = max(
            remaining,
            key=lambda c: marginal_components(c, priorities, selected)["total"],
        )
        item = deepcopy(best)
        item["marginal_components"] = marginal_components(best, priorities, selected)
        selected.append(item)
        remaining.remove(best)
    return selected


def capability(c, key):
    values = c.get("capabilities", {})
    return values.get(key, 0) if isinstance(values, dict) else float(key in values)


def marginal_components(c, priorities, selected):
    quality = c["combined_score"] / 10
    if not selected:
        return {
            "quality": quality,
            "coverage_gain": 0.0,
            "max_similarity": 0.0,
            "total": quality,
            "selection_rule": "quality_anchor",
        }
    priority_total = sum(priorities.values())
    gain = (
        sum(
            priorities[k]
            * max(
                0,
                capability(c, k) - max((capability(o, k) for o in selected), default=0),
            )
            for k in CAPABILITIES
        )
        / priority_total
        if priority_total
        else 0.0
    )
    similarity = max(
        (c.get("similarity", {}).get(o["handle"], 0) for o in selected), default=0
    )
    return {
        "quality": quality,
        "coverage_gain": gain,
        "max_similarity": similarity,
        "total": 0.50 * quality + 0.35 * gain - 0.15 * similarity,
        "selection_rule": "marginal_teammate",
    }


def relative_scores(candidates, weights):
    candidates = [c for c in candidates if safety_gate(c) != "FAIL"]
    result = deepcopy(candidates)
    # Use exactly this frozen shortlist as the comparison cohort.
    for c in result:
        c["raw_dimensions"] = deepcopy(c["dimensions"])
        for d in DIMENSIONS:
            value = relative(
                c["dimensions"][d]["score"],
                [x["dimensions"][d]["score"] for x in candidates],
            )
            c["dimensions"][d]["score"] = None if value is None else value * 10
        c["combined_score"] = weighted_score(c, weights)
        c["missing_dimensions"] = [
            d for d in DIMENSIONS if c["dimensions"][d]["score"] is None
        ]
    return sorted(
        result,
        key=lambda c: (
            -(c["combined_score"] if c["combined_score"] is not None else -1),
            c["handle"],
        ),
    )


def manual_swap(roster, candidates, outgoing, incoming, priorities):
    if outgoing not in [c["handle"] for c in roster] or incoming in [
        c["handle"] for c in roster
    ]:
        raise ValueError(
            "Swap must replace a roster member with a new shortlisted creator"
        )
    replacement = next((c for c in candidates if c["handle"] == incoming), None)
    if (
        replacement is None
        or safety_gate(replacement) == "FAIL"
        or replacement.get("combined_score") is None
    ):
        raise ValueError("Replacement must be an eligible scored shortlisted creator")
    result = []
    for old in roster:
        item = deepcopy(replacement if old["handle"] == outgoing else old)
        item["marginal_components"] = marginal_components(item, priorities, result)
        result.append(item)
    return result

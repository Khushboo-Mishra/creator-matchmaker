"""Relative ranking, health gates, shortlist and roster selection."""
from .campaign import DIMENSIONS, CAPABILITIES, validate_controls

def creator_health(channel):
    """Locked health mix: engagement 40%, momentum 40%, activity 20%."""
    scores = channel.get("dimensions", channel)
    values = [scores.get(k, {}).get("score") if isinstance(scores.get(k), dict) else scores.get(k) for k in ("engagement", "momentum", "speed_to_activate")]
    if any(v is None for v in values): return None
    return round(values[0] * .4 + values[1] * .4 + values[2] * .2, 4)

def weighted_score(channel, weights):
    validate_controls(weights, {k: 1 for k in CAPABILITIES})
    dims = channel.get("dimensions", channel)
    total = weight_sum = 0.0
    for dim in DIMENSIONS:
        value = dims.get(dim, {}).get("score") if isinstance(dims.get(dim), dict) else dims.get(dim)
        if value is not None:
            total += value * weights[dim]; weight_sum += weights[dim]
    return round(total / weight_sum, 4) if weight_sum else None

def safety_gate(channel):
    status = channel.get("brand_safety", channel.get("safety", "REVIEW"))
    return status if status in {"PASS", "REVIEW", "FAIL"} else "REVIEW"

def shortlist(channels, weights, top_n=15, specialist_n=5):
    eligible = [c for c in channels if safety_gate(c) != "FAIL" and creator_health(c) is not None]
    ranked = sorted(eligible, key=lambda c: weighted_score(c, weights) or -1, reverse=True)
    top = ranked[:top_n]
    chosen = {c.get("handle") for c in top}
    specialists = sorted((c for c in eligible if c.get("handle") not in chosen), key=lambda c: max((c.get("dimensions", {}).get(d, {}).get("score") or 0) for d in CAPABILITIES), reverse=True)[:specialist_n]
    return top + specialists

def select_roster(candidates, priorities, size=4):
    """Greedy quality .50 + coverage .35 - similarity .15; priorities stay continuous."""
    validate_controls({d: 1 for d in DIMENSIONS}, priorities)
    selected, covered = [], set()
    remaining = list(candidates)
    while remaining and len(selected) < size:
        best = max(remaining, key=lambda c: _roster_value(c, priorities, covered, selected))
        selected.append(best); remaining.remove(best)
        covered |= set(best.get("capabilities", []))
    return selected

def _roster_value(c, priorities, covered, selected):
    quality = c.get("combined_score", weighted_score(c, {d: 1 for d in DIMENSIONS})) or 0
    caps = set(c.get("capabilities", []))
    coverage = sum(priorities.get(x, 0) for x in caps - covered)
    similarity = max((c.get("similarity", {}).get(o.get("handle"), 0) for o in selected), default=0)
    return .50 * quality + .35 * coverage - .15 * similarity

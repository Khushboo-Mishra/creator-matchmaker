"""Deterministic discovery/screening combination and measurable gates."""
def additive_screen(discovery_relevance, screening_score):
    """Combine normalized discovery evidence (40%) and screening (60%)."""
    return round(.40 * max(0, min(1, discovery_relevance)) + .60 * max(0, min(1, screening_score)), 4)

def passes_gates(candidate, min_health=4.0, safety="PASS"):
    health = candidate.get("creator_health")
    return (health is not None and health >= min_health and candidate.get("brand_safety", "REVIEW") == safety and not candidate.get("hard_stop", False))

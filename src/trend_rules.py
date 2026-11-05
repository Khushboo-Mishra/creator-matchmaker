"""Pre-registered trend rules enforced at run time.

Kept outside evaluation.py on purpose: evaluation.py is hash-pinned by the
checkpoint migration, and this rule only adds a rejection for snapshots that
record min_lift. Snapshots without min_lift (imported before 2026-11-05) keep
the legacy recent > previous rule already enforced by valid_trends.
"""


def check_min_lift(snapshot):
    """Raise if any retained rising topic is below the snapshot's recorded min_lift."""
    if snapshot is None:
        return None
    for trend in snapshot.get("trends", []):
        min_lift = trend.get("min_lift")
        if min_lift is None:
            continue
        before, after = trend["previous_interest"], trend["recent_interest"]
        if before <= 0 or (after - before) / before < min_lift:
            raise ValueError(
                f"Verified trend {trend.get('topic')!r} rises less than "
                f"the recorded minimum lift of {min_lift:.0%}"
            )
    return snapshot

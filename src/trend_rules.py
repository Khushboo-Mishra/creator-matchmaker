"""Pre-registered trend rules enforced at run time.

Kept outside evaluation.py on purpose: evaluation.py is hash-pinned by the
checkpoint migration, and this rule only adds a rejection for snapshots that
record min_lift. Snapshots without min_lift (imported before 2026-11-05) keep
the legacy recent > previous rule already enforced by valid_trends.
"""

MIN_LIFT = 0.05  # pre-registered 2026-11-05: recent half must beat previous half by >= 5%


def lift(before, after):
    """Relative rise from before to after, or None when before is not positive."""
    if before <= 0:
        return None
    return (after - before) / before


def meets_min_lift(before, after, min_lift=MIN_LIFT):
    rise = lift(before, after)
    return rise is not None and rise >= min_lift


def check_min_lift(snapshot):
    """Raise if any retained rising topic is below the pre-registered minimum lift.

    A recorded min_lift is only honoured if it is a real number at or above
    MIN_LIFT, so editing the snapshot cannot weaken the rule.
    """
    if snapshot is None:
        return None
    for trend in snapshot.get("trends", []):
        topic = trend.get("topic")
        min_lift = trend.get("min_lift")
        if min_lift is None:
            continue
        if isinstance(min_lift, bool) or not isinstance(min_lift, (int, float)):
            raise ValueError(f"Verified trend {topic!r} has a non-numeric min_lift")
        if min_lift < MIN_LIFT:
            raise ValueError(
                f"Verified trend {topic!r} records a minimum lift of {min_lift:.0%}, "
                f"below the pre-registered {MIN_LIFT:.0%}"
            )
        before, after = trend["previous_interest"], trend["recent_interest"]
        if lift(before, after) is None:
            raise ValueError(
                f"Verified trend {topic!r} has a zero baseline, so its lift is undefined"
            )
        if not meets_min_lift(before, after, min_lift):
            raise ValueError(
                f"Verified trend {topic!r} rises less than "
                f"the recorded minimum lift of {min_lift:.0%}"
            )
    return snapshot

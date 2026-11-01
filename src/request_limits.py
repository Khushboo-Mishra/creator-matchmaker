"""Transport-only pacing and bounded retry policy; no scoring changes."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
import threading
import time


class EmbeddingPacer:
    """Space request starts by 0.8s (~75/minute) within one process."""

    def __init__(self, interval=0.8):
        self.interval = interval
        self.last_start = None
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = time.monotonic()
            if self.last_start is not None:
                delay = self.interval - (now - self.last_start)
                if delay > 0:
                    time.sleep(delay)
            self.last_start = time.monotonic()


def retry_delay(response, fallback):
    """Return delay or None: don't retry known daily quotas or waits over 60s."""
    delays = [float(fallback)]
    header = getattr(response, "headers", {}).get("Retry-After")
    if header:
        try:
            seconds = float(header)
        except (ValueError, TypeError):
            try:
                seconds = (
                    parsedate_to_datetime(header) - datetime.now(timezone.utc)
                ).total_seconds()
            except (ValueError, TypeError, OverflowError):
                seconds = 0
        if math.isfinite(seconds):
            delays.append(max(0, seconds))
    try:
        body = response.json()
    except (ValueError, AttributeError):
        body = {}
    error = body.get("error", {}) if isinstance(body, dict) else {}
    details = error.get("details", []) if isinstance(error, dict) else []
    for detail in details if isinstance(details, list) else []:
        if not isinstance(detail, dict):
            continue
        if detail.get("@type", "").endswith("google.rpc.QuotaFailure"):
            for violation in detail.get("violations", []):
                if (
                    isinstance(violation, dict)
                    and "perday" in str(violation.get("quotaId", "")).lower()
                ):
                    return None
        if detail.get("@type", "").endswith("google.rpc.RetryInfo"):
            try:
                seconds = float(str(detail.get("retryDelay", "")).removesuffix("s"))
                if math.isfinite(seconds):
                    delays.append(max(0, seconds))
            except ValueError:
                pass
    delay = max(delays)
    return delay if delay <= 60 else None

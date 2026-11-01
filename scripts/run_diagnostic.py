"""Run the existing CLI with sanitized HTTP error details; no extra API calls."""

import json
from pathlib import Path
import re
import sys

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import GEMINI_API_KEY, YOUTUBE_API_KEY
from src.matchmaker import main


def http_details(exc, secrets=()):
    response = exc.response
    if response is None:
        return "HTTP request failed without a response."
    payload = {"http_status": response.status_code}
    if response.headers.get("Retry-After"):
        payload["retry_after"] = response.headers["Retry-After"]
    try:
        body = response.json()
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict):
            payload["error"] = {
                key: error[key]
                for key in ("code", "status", "message", "details")
                if key in error
            }
        else:
            payload["note"] = "No structured error object returned."
    except ValueError:
        payload["note"] = "Non-JSON response omitted to avoid exposing request data."
    text = json.dumps(payload, indent=2, ensure_ascii=True)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
            text = text.replace(json.dumps(secret)[1:-1], "[REDACTED]")
    return re.sub(r"AIza[A-Za-z0-9_-]+", "[REDACTED]", text)


def diagnostic_main(argv=None):
    try:
        main(argv)
    except requests.HTTPError as exc:
        print("Run failed: external API rejected the request.", file=sys.stderr)
        print(http_details(exc, (GEMINI_API_KEY, YOUTUBE_API_KEY)), file=sys.stderr)
        print("Keep your checkpoint. Completed work remains saved.", file=sys.stderr)
        return 1
    except (ValueError, KeyError, OSError) as exc:
        print(f"Run failed ({type(exc).__name__}); no HTTP response details available.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(diagnostic_main())

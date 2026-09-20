"""Tests for how the pull chooses what to fetch. No network, no key.

The point of these is the seam with discovery: records stay keyed by handle
even when the input was a channel id, because data/scores/<handle>.json has to
pair with data/channels/<handle>.json.
"""
import json

import pytest

from src import pull


def channel(channel_id="UCabc123", custom_url="@someone"):
    return {
        "id": channel_id,
        "snippet": {"title": "T", "customUrl": custom_url},
        "statistics": {"subscriberCount": "1000"},
        "contentDetails": {"relatedPlaylists": {"uploads": "UUabc123"}},
    }


class TestHandleResolution:
    def test_custom_url_becomes_the_handle(self):
        assert pull._handle_of(channel(custom_url="@studiobinder")) == "@studiobinder"

    def test_custom_url_without_an_at_gets_one(self):
        assert pull._handle_of(channel(custom_url="studiobinder")) == "@studiobinder"

    def test_no_custom_url_falls_back_to_the_id_never_to_null(self):
        """A null handle would break the channels/scores pairing and the schema."""
        handle = pull._handle_of(channel(channel_id="UCxyz", custom_url=""))
        assert handle == "UCxyz"
        assert isinstance(handle, str)

    def test_missing_custom_url_key_is_not_an_error(self):
        ch = channel()
        del ch["snippet"]["customUrl"]
        assert pull._handle_of(ch) == "UCabc123"

    def test_explicit_handle_wins_over_a_stale_custom_url(self):
        assert pull._handle_of(channel(custom_url=""), fallback="@asked") == "@asked"


class TestTargetSelection:
    def test_command_line_arguments_win(self, monkeypatch):
        monkeypatch.setattr(pull, "read_discovered_candidates", lambda: [{"channel_id": "UC1"}])
        assert pull._targets(["@me"]) == [("@me", None)]

    def test_discovery_is_preferred_over_handles(self, monkeypatch):
        candidate = {"channel_id": "UC1", "channel_title": "One", "matches": []}
        monkeypatch.setattr(pull, "read_discovered_candidates", lambda: [candidate])
        monkeypatch.setattr(pull, "read_handles", lambda: ["@fallback"])
        targets = pull._targets([])
        assert targets == [("UC1", candidate)]

    def test_handles_are_the_fallback_when_discovery_has_not_run(self, monkeypatch):
        monkeypatch.setattr(pull, "read_discovered_candidates", lambda: [])
        monkeypatch.setattr(pull, "read_handles", lambda: ["@fallback"])
        assert pull._targets([]) == [("@fallback", None)]

    def test_absent_discovery_file_is_not_an_error(self, monkeypatch, tmp_path):
        monkeypatch.setattr(pull, "DISCOVERED_FILE", tmp_path / "nope.json")
        assert pull.read_discovered_candidates() == []

    def test_reads_the_candidates_key(self, monkeypatch, tmp_path):
        f = tmp_path / "d.json"
        f.write_text(json.dumps({"queries": ["q"], "candidates": [{"channel_id": "UC1"}]}))
        monkeypatch.setattr(pull, "DISCOVERED_FILE", f)
        assert pull.read_discovered_candidates() == [{"channel_id": "UC1"}]


class TestQuota:
    def test_quota_exceeded_is_distinguished_from_an_ordinary_403(self):
        class Response:
            status_code = 403
            def json(self):
                return {"error": {"errors": [{"reason": "quotaExceeded"}]}}
        assert pull._reason(Response()) == "quotaExceeded"

    def test_an_unparseable_error_body_does_not_crash(self):
        class Response:
            status_code = 403
            def json(self):
                raise ValueError("not json")
        assert pull._reason(Response()) == ""

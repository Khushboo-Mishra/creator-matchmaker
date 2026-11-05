import json

import requests

from scripts import run_diagnostic as diagnostic


def test_quota_details_and_secrets():
    response = requests.Response()
    response.status_code = 429
    response.headers["Retry-After"] = "60"
    response._content = json.dumps({"error": {
        "code": 429, "status": "RESOURCE_EXHAUSTED",
        "message": "quota exceeded secret-test-key AIzaExampleSecret",
        "details": [{"quotaId": "RequestsPerMinute", "retryDelay": "60s"}],
    }}).encode()
    output = diagnostic.http_details(requests.HTTPError(response=response), ("secret-test-key",))
    assert "secret-test-key" not in output
    assert "AIzaExampleSecret" not in output
    assert "RequestsPerMinute" in output
    assert "60s" in output
    assert json.loads(output)["http_status"] == 429


def test_non_json_response_is_not_dumped():
    response = requests.Response()
    response.status_code = 503
    response._content = b"<html>private request data</html>"
    assert "private request data" not in diagnostic.http_details(requests.HTTPError(response=response))


def test_launcher_forwards_args_once_and_reports_failure(monkeypatch, capsys):
    calls = []
    response = requests.Response()
    response.status_code = 429
    response._content = b'{"error":{"message":"quota exceeded"}}'

    def fail(args):
        calls.append(args)
        raise requests.HTTPError(response=response)

    monkeypatch.setattr(diagnostic, "main", fail)
    assert diagnostic.diagnostic_main(["run", "--resume"]) == 1
    assert calls == [["run", "--resume"]]
    assert "quota exceeded" in capsys.readouterr().err


def test_launcher_success(monkeypatch):
    monkeypatch.setattr(diagnostic, "main", lambda args: None)
    assert diagnostic.diagnostic_main([]) == 0

import pytest

from src import request_limits, score_ai


class Response:
    def __init__(self, status=429, headers=None, details=None):
        self.status_code = status
        self.headers = headers or {}
        self.details = details or []

    def json(self):
        return {"error": {"details": self.details}}


def test_pacing_with_fake_clock(monkeypatch):
    now = [0.0]
    sleeps = []
    monkeypatch.setattr(request_limits.time, "monotonic", lambda: now[0])

    def sleep(delay):
        sleeps.append(delay)
        now[0] += delay

    monkeypatch.setattr(request_limits.time, "sleep", sleep)
    pacer = request_limits.EmbeddingPacer()
    for _ in range(76):
        pacer.wait()
    assert now[0] == pytest.approx(60)
    assert len(sleeps) == 75
    now[0] += 2
    pacer.wait()
    assert len(sleeps) == 75


def test_retry_guidance_and_daily_quota():
    response = Response(
        headers={"Retry-After": "12"},
        details=[
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "30s"}
        ],
    )
    assert request_limits.retry_delay(response, 2) == 30
    assert (
        request_limits.retry_delay(Response(headers={"Retry-After": "120"}), 2) is None
    )
    daily = Response(
        details=[
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [{"quotaId": "RequestsPerDayPerProject"}],
            }
        ]
    )
    assert request_limits.retry_delay(daily, 2) is None
    assert (
        request_limits.retry_delay(Response(headers={"Retry-After": "garbage"}), 4) == 4
    )


def test_retries_paced_and_server_wait_used(monkeypatch):
    waits, pacing = [], []
    responses = iter([Response(headers={"Retry-After": "20"}), Response(200)])
    monkeypatch.setattr(score_ai.requests, "post", lambda **kw: next(responses))
    monkeypatch.setattr(score_ai.time, "sleep", waits.append)
    monkeypatch.setattr(score_ai._embedding_pacer, "wait", lambda: pacing.append(1))
    assert (
        score_ai._post_with_retry(url="https://example.test:embedContent").status_code
        == 200
    )
    assert waits == [20]
    assert len(pacing) == 2


def test_cached_embedding_does_not_wait_or_call_api(monkeypatch):
    calls, pacing = [], []

    class EmbeddingResponse(Response):
        def raise_for_status(self):
            pass

        def json(self):
            return {"embedding": {"values": [0.1, 0.2]}}

    def post(**kwargs):
        calls.append(kwargs)
        return EmbeddingResponse(200)

    monkeypatch.setattr(score_ai.requests, "post", post)
    monkeypatch.setattr(score_ai._embedding_pacer, "wait", lambda: pacing.append(1))
    score_ai.embed_text.cache_clear()
    try:
        assert score_ai.embed_text("cached") == score_ai.embed_text("cached")
        assert len(calls) == len(pacing) == 1
    finally:
        score_ai.embed_text.cache_clear()


def test_daily_limit_stops_without_retry(monkeypatch):
    response = Response(
        details=[
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [{"quotaId": "RequestsPerDay"}],
            }
        ]
    )
    calls = []

    def post(**kwargs):
        calls.append(1)
        return response

    monkeypatch.setattr(score_ai.requests, "post", post)
    monkeypatch.setattr(score_ai.time, "sleep", lambda _: pytest.fail("No retry sleep"))
    assert score_ai._post_with_retry(url="generation") is response
    assert len(calls) == 1

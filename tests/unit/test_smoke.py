from collections.abc import Iterator

import pytest

from scripts.smoke import HttpResponse, SmokeFailure, run_smoke


def test_smoke_checks_health_readiness_and_documents() -> None:
    seen: list[str] = []

    def fetch(url: str, _timeout: float) -> HttpResponse:
        seen.append(url)
        if url.endswith("/health"):
            return HttpResponse(200, {"status": "ok", "version": "abc123"})
        if url.endswith("/ready"):
            return HttpResponse(200, {"status": "ready", "checks": {"database": True}})
        return HttpResponse(200, {"items": [{"id": "001"}]})

    lines = run_smoke(
        "https://attackpath.example/",
        expected_version="abc123",
        fetch=fetch,
        clock=lambda: 0.0,
        sleep=lambda _seconds: None,
    )

    assert lines == [
        "ok   /health -> 200, version abc123",
        "ok   /ready -> 200 {'status': 'ready', 'checks': {'database': True}}",
        "ok   /v1/documents?limit=1 -> 200",
    ]
    assert seen == [
        "https://attackpath.example/health",
        "https://attackpath.example/ready",
        "https://attackpath.example/v1/documents?limit=1",
    ]


def test_smoke_waits_until_expected_version_is_live() -> None:
    health_responses: Iterator[HttpResponse] = iter(
        [
            HttpResponse(200, {"status": "ok", "version": "old"}),
            HttpResponse(200, {"status": "ok", "version": "new"}),
        ]
    )
    sleeps: list[float] = []

    def fetch(url: str, _timeout: float) -> HttpResponse:
        if url.endswith("/health"):
            return next(health_responses)
        if url.endswith("/ready"):
            return HttpResponse(200, {"status": "ready", "checks": {"database": True}})
        return HttpResponse(200, {"items": [{"id": "001"}]})

    run_smoke(
        "https://attackpath.example",
        expected_version="new",
        fetch=fetch,
        clock=lambda: 0.0,
        sleep=sleeps.append,
    )

    assert sleeps == [5.0]


def test_smoke_rejects_an_unready_database() -> None:
    def fetch(url: str, _timeout: float) -> HttpResponse:
        if url.endswith("/health"):
            return HttpResponse(200, {"status": "ok", "version": "abc"})
        return HttpResponse(503, {"status": "not_ready", "checks": {"database": False}})

    with pytest.raises(SmokeFailure, match="/ready returned 503"):
        run_smoke(
            "https://attackpath.example",
            fetch=fetch,
            clock=lambda: 0.0,
            sleep=lambda _seconds: None,
        )

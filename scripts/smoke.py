"""Smoke-test a deployed ATTACKpath service.

Run: uv run python scripts/smoke.py https://attackpath.onrender.com
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

DEFAULT_TIMEOUT_SECONDS = 180.0
DEFAULT_INTERVAL_SECONDS = 5.0


class SmokeFailure(RuntimeError):
    """Raised when the deployed service does not satisfy a smoke-check."""


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    payload: Any


FetchJson = Callable[[str, float], HttpResponse]
Clock = Callable[[], float]
Sleeper = Callable[[float], None]


def _service_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def fetch_json(url: str, timeout: float) -> HttpResponse:
    """Fetch one JSON endpoint without requiring an HTTP client dependency."""
    try:
        with urlopen(url, timeout=timeout) as response:  # noqa: S310 - URL is explicit CLI input.
            status_code = response.status
            raw = response.read()
    except HTTPError as exc:
        status_code = exc.code
        raw = exc.read()
    except URLError as exc:
        raise SmokeFailure(f"could not reach {url}: {exc.reason}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SmokeFailure(f"{url} returned invalid JSON") from exc
    return HttpResponse(status_code=status_code, payload=payload)


def _health_is_ready(response: HttpResponse, expected_version: str | None) -> bool:
    if response.status_code != 200 or not isinstance(response.payload, dict):
        return False
    if response.payload.get("status") != "ok":
        return False
    return expected_version is None or response.payload.get("version") == expected_version


def wait_for_health(
    base_url: str,
    *,
    expected_version: str | None,
    timeout_seconds: float,
    interval_seconds: float,
    fetch: FetchJson = fetch_json,
    clock: Clock = time.monotonic,
    sleep: Sleeper = time.sleep,
) -> HttpResponse:
    """Wait for /health, and optionally for the newly deployed commit to appear."""
    health_url = _service_url(base_url, "/health")
    deadline = clock() + timeout_seconds
    last_result = "no response"

    while True:
        try:
            response = fetch(health_url, min(interval_seconds, timeout_seconds))
        except SmokeFailure as exc:
            last_result = str(exc)
        else:
            if _health_is_ready(response, expected_version):
                return response
            version = (
                response.payload.get("version") if isinstance(response.payload, dict) else None
            )
            last_result = f"{response.status_code}, version {version!r}"

        remaining = deadline - clock()
        if remaining <= 0:
            expected = f" version {expected_version}" if expected_version else " a healthy response"
            raise SmokeFailure(
                f"/health did not report{expected} within {timeout_seconds:g}s ({last_result})"
            )
        sleep(min(interval_seconds, remaining))


def run_smoke(
    base_url: str,
    *,
    expected_version: str | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    fetch: FetchJson = fetch_json,
    clock: Clock = time.monotonic,
    sleep: Sleeper = time.sleep,
) -> list[str]:
    """Return successful smoke-test lines or raise SmokeFailure."""
    if timeout_seconds <= 0 or interval_seconds <= 0:
        raise ValueError("timeout and interval must both be positive")

    health = wait_for_health(
        base_url,
        expected_version=expected_version,
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
        fetch=fetch,
        clock=clock,
        sleep=sleep,
    )
    version = health.payload.get("version")
    lines = [f"ok   /health -> 200, version {version}"]

    ready = fetch(_service_url(base_url, "/ready"), interval_seconds)
    if ready.status_code != 200 or not isinstance(ready.payload, dict):
        raise SmokeFailure(f"/ready returned {ready.status_code}: {ready.payload!r}")
    database_ready = ready.payload.get("checks", {}).get("database") is True
    if ready.payload.get("status") != "ready" or not database_ready:
        raise SmokeFailure(f"/ready did not report a ready database: {ready.payload!r}")
    lines.append(f"ok   /ready -> 200 {ready.payload}")

    documents = fetch(_service_url(base_url, "/v1/documents?limit=1"), interval_seconds)
    if documents.status_code != 200:
        raise SmokeFailure(f"/v1/documents?limit=1 returned {documents.status_code}")
    lines.append("ok   /v1/documents?limit=1 -> 200")
    return lines


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Public base URL, for example https://attackpath.onrender.com")
    parser.add_argument("--expect-version", help="Require /health to report this Git commit SHA")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        for line in run_smoke(
            args.url,
            expected_version=args.expect_version,
            timeout_seconds=args.timeout,
            interval_seconds=args.interval,
        ):
            print(line)
    except (SmokeFailure, ValueError) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    print("Smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

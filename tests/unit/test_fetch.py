from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from attackpath.ingest.fetch import (
    CONTACT,
    USER_AGENT,
    DownloadError,
    Manifest,
    Source,
    backoff_delay,
    discover_sitemap,
    fetch_all,
    fetch_one,
    file_stem,
    make_client,
    pick_ext,
    read_sources,
    register_manual,
    retry_after_seconds,
    slug,
)


def test_identity_is_project_specific() -> None:
    assert "examate-student-bot/0.1" in USER_AGENT
    assert CONTACT in USER_AGENT


def test_slug_is_safe() -> None:
    assert slug("A report / 2026!.pdf") == "a-report-2026-pdf"


def test_file_stem_is_stable() -> None:
    assert file_stem("https://example.test/a/report.pdf") == file_stem(
        "https://example.test/a/report.pdf"
    )
    assert file_stem("https://example.test/a/report.pdf") != file_stem(
        "https://example.test/a/other.pdf"
    )


def test_pick_ext_prefers_url_suffix() -> None:
    assert pick_ext("https://example.test/file.pdf", "text/html") == ".pdf"


def test_pick_ext_uses_content_type() -> None:
    assert pick_ext("https://example.test/file", "application/pdf; charset=binary") == ".pdf"


def test_backoff_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("attackpath.ingest.fetch.random.uniform", lambda low, high: high)
    assert backoff_delay(10, cap=3) == 3


def test_retry_after_seconds_accepts_seconds() -> None:
    assert retry_after_seconds("12") == 12
    assert retry_after_seconds(None) is None


def test_read_sources_ignores_comments_and_deduplicates(tmp_path: Path) -> None:
    path = tmp_path / "sources.csv"
    path.write_text(
        "# note\nurl,source,licence,title\nhttps://a.test/a,a,MITRE,A\nhttps://a.test/a,a,MITRE,A\n",
        encoding="utf-8",
    )
    assert read_sources(path) == [Source("https://a.test/a", "a", "MITRE", "A")]


def test_read_sources_requires_licence(tmp_path: Path) -> None:
    path = tmp_path / "sources.csv"
    path.write_text("url,source,licence,title\nhttps://a.test/a,a,,A\n", encoding="utf-8")
    with pytest.raises(ValueError, match="licence"):
        read_sources(path)


def test_read_sources_requires_http_url(tmp_path: Path) -> None:
    path = tmp_path / "sources.csv"
    path.write_text("url,source,licence,title\n/a,a,MITRE,A\n", encoding="utf-8")
    with pytest.raises(ValueError, match="http"):
        read_sources(path)


def test_manifest_repairs_truncated_last_line(tmp_path: Path) -> None:
    path = tmp_path / "manifest.jsonl"
    path.write_text('{"url":"https://a"}', encoding="utf-8")
    Manifest(path)
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_manifest_done_requires_file(tmp_path: Path) -> None:
    manifest = Manifest(tmp_path / "manifest.jsonl")
    manifest.add({"url": "https://a", "status": "downloaded", "path": "data/raw/a.txt"})
    assert not manifest.done("https://a", tmp_path)


def test_make_client_has_user_agent() -> None:
    client = make_client()
    assert client.headers["user-agent"] == USER_AGENT


def test_fetch_one_downloads_atomically(tmp_path: Path) -> None:
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(200, headers={"Content-Type": "text/plain"}, content=b"hello")

    async def run() -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            from attackpath.ingest.fetch import HostGate, Robots

            return await fetch_one(
                client,
                Source("https://example.test/doc.txt", "example", "MITRE"),
                root=tmp_path,
                raw_dir=tmp_path / "data" / "raw",
                robots=Robots(client),
                gate=HostGate(0, asyncio.sleep),
                slots=asyncio.Semaphore(1),
                max_attempts=1,
                sleep=asyncio.sleep,
            )

    record = asyncio.run(run())
    assert record["status"] == "downloaded"
    assert (tmp_path / record["path"]).read_bytes() == b"hello"
    assert not list((tmp_path / "data" / "raw").rglob("*.part"))
    assert calls == ["/robots.txt", "/doc.txt"]


def test_fetch_one_blocks_disallowed_source(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: examate-student-bot\nDisallow: /\n")
        raise AssertionError("blocked URL was requested")

    async def run() -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            from attackpath.ingest.fetch import HostGate, Robots

            return await fetch_one(
                client,
                Source("https://example.test/doc", "example", "MITRE"),
                root=tmp_path,
                raw_dir=tmp_path / "raw",
                robots=Robots(client),
                gate=HostGate(0, asyncio.sleep),
                slots=asyncio.Semaphore(1),
                max_attempts=1,
                sleep=asyncio.sleep,
            )

    assert asyncio.run(run())["status"] == "blocked"


def test_fetch_all_skips_completed_source(tmp_path: Path) -> None:
    target = tmp_path / "data" / "raw" / "example" / "doc.txt"
    target.parent.mkdir(parents=True)
    target.write_text("already", encoding="utf-8")
    manifest = Manifest(tmp_path / "data" / "manifest.jsonl")
    manifest.add(
        {
            "url": "https://example.test/doc.txt",
            "status": "downloaded",
            "path": "data/raw/example/doc.txt",
        }
    )

    async def run() -> dict[str, int]:
        return await fetch_all(
            [Source("https://example.test/doc.txt", "example", "MITRE")], root=tmp_path
        )

    assert asyncio.run(run()) == {"downloaded": 0, "skipped": 1, "blocked": 0, "failed": 0}


def test_fetch_all_retries_transient_failure(tmp_path: Path) -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        attempts += 1
        return httpx.Response(503 if attempts == 1 else 200, content=b"ok")

    async def run() -> dict[str, int]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_all(
                [Source("https://example.test/doc", "example", "MITRE")],
                root=tmp_path,
                client=client,
                max_attempts=2,
                sleep=lambda _: asyncio.sleep(0),
            )

    assert asyncio.run(run())["downloaded"] == 1
    assert attempts == 2


def test_fetch_all_records_failed_status(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(404)

    async def run() -> dict[str, int]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_all(
                [Source("https://example.test/doc", "example", "MITRE")],
                root=tmp_path,
                client=client,
                max_attempts=1,
            )

    assert asyncio.run(run())["failed"] == 1
    assert json.loads((tmp_path / "data" / "manifest.jsonl").read_text())["status"] == "failed"


def test_discover_sitemap_filters_without_downloading() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/sitemap.xml"
        return httpx.Response(
            200,
            text="<urlset><url><loc>https://a.test/docs/a</loc></url><url><loc>https://a.test/blog/b</loc></url></urlset>",
        )

    async def run() -> list[str]:
        from unittest.mock import patch

        with patch(
            "attackpath.ingest.fetch.make_client",
            lambda _: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        ):
            return await discover_sitemap("https://a.test/sitemap.xml", include=("/docs/",))

    assert asyncio.run(run()) == ["https://a.test/docs/a"]


def test_register_manual_records_files(tmp_path: Path) -> None:
    folder = tmp_path / "data" / "raw" / "manual"
    folder.mkdir(parents=True)
    (folder / "one.txt").write_text("one", encoding="utf-8")
    assert (
        register_manual(
            folder,
            from_url="https://example.test/page",
            source="manual",
            licence="personal terms",
            root=tmp_path,
        )
        == 1
    )
    record = json.loads((tmp_path / "data" / "manifest.jsonl").read_text())
    assert record["via"] == "manual"


def test_download_error_keeps_retry_metadata() -> None:
    error = DownloadError("busy", code=429, retry_after=4)
    assert error.code == 429
    assert error.retry_after == 4

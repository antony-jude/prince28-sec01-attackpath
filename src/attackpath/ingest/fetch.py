"""Polite, resumable downloader for the ATTACKpath corpus.

The downloader is deliberately conservative: it checks robots.txt before a
request, limits concurrency and per-host rate, retries only transient errors,
and writes a manifest only after an atomic ``.part`` file has completed.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import random
import re
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx
from protego import Protego

CONTACT = "https://github.com/antony-jude/prince28-sec01-attackpath"
ROBOTS_TOKEN = "examate-student-bot"
USER_AGENT = f"{ROBOTS_TOKEN}/0.1 (student project; +{CONTACT})"
RETRYABLE = {408, 425, 429, 500, 502, 503, 504}
MAX_WAIT = 120.0
MAX_BYTES = 200 * 1024 * 1024
ATTEMPT_TIMEOUT = 300.0
KNOWN_EXT = {
    ".pdf",
    ".html",
    ".htm",
    ".json",
    ".txt",
    ".md",
    ".mdx",
    ".rst",
    ".adoc",
    ".csv",
    ".xml",
    ".yaml",
    ".yml",
    ".zip",
    ".docx",
    ".xlsx",
    ".xls",
}
EXT_BY_TYPE = {
    "application/pdf": ".pdf",
    "text/html": ".html",
    "application/json": ".json",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
    "application/xml": ".xml",
    "text/xml": ".xml",
    "application/zip": ".zip",
    "application/yaml": ".yaml",
}
Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class Source:
    """One licensed source row."""

    url: str
    source: str
    licence: str
    title: str = ""


class DownloadError(Exception):
    """An HTTP response that may or may not be retryable."""

    def __init__(self, message: str, *, code: int | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def slug(text: str, limit: int = 60) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:limit] or "file"


def file_stem(url: str) -> str:
    parts = urlsplit(url)
    last = unquote(parts.path.rstrip("/").rsplit("/", 1)[-1]) or parts.netloc
    name = last.rsplit(".", 1)[0] if "." in last else last
    return f"{slug(name)}-{hashlib.sha256(url.encode()).hexdigest()[:8]}"


def pick_ext(url: str, content_type: str) -> str:
    suffix = Path(urlsplit(url).path).suffix.lower()
    return (
        suffix
        if suffix in KNOWN_EXT
        else EXT_BY_TYPE.get(content_type.split(";")[0].strip().lower(), ".bin")
    )


def backoff_delay(attempt: int, *, base: float = 1.0, cap: float = 60.0) -> float:
    return random.uniform(0, min(cap, base * 2**attempt))


def retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def read_sources(path: Path) -> list[Source]:
    """Read a CSV while ignoring comment lines and rejecting incomplete rows."""
    sources: list[Source] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        lines = (line for line in handle if line.strip() and not line.lstrip().startswith("#"))
        for number, row in enumerate(csv.DictReader(lines), start=1):
            url = (row.get("url") or "").strip()
            name = (row.get("source") or "").strip()
            licence = (row.get("licence") or "").strip()
            if urlsplit(url).scheme not in {"http", "https"}:
                raise ValueError(f"sources row {number}: not an http(s) URL: {url!r}")
            if not name or not licence:
                raise ValueError(f"sources row {number}: source and licence are required: {url}")
            if url not in seen:
                seen.add(url)
                sources.append(Source(url, name, licence, (row.get("title") or "").strip()))
    return sources


class Manifest:
    """Append-only provenance log; the newest record for a URL wins."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.records: dict[str, dict] = {}
        if path.exists():
            text = path.read_text(encoding="utf-8")
            for line in text.splitlines():
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "url" in record:
                    self.records[record["url"]] = record
            if text and not text.endswith("\n"):
                with path.open("a", encoding="utf-8") as handle:
                    handle.write("\n")

    def done(self, url: str, root: Path) -> bool:
        record = self.records.get(url)
        return bool(
            record and record.get("status") == "downloaded" and (root / record["path"]).is_file()
        )

    def add(self, record: dict) -> None:
        self.records[record["url"]] = record
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


class Robots:
    """Fetch and cache one robots policy per origin."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self.rules: dict[str, Protego | None] = {}
        self.locks: dict[str, asyncio.Lock] = {}

    async def _load(self, origin: str) -> Protego | None:
        try:
            response = await self.client.get(origin + "/robots.txt")
        except httpx.HTTPError:
            return None
        if response.status_code == 429 or response.status_code >= 500:
            return None
        if response.status_code >= 400:
            return Protego.parse("")
        return Protego.parse(response.text)

    async def check(self, url: str) -> tuple[bool, float]:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        async with self.locks.setdefault(origin, asyncio.Lock()):
            if origin not in self.rules:
                self.rules[origin] = await self._load(origin)
        rules = self.rules[origin]
        if rules is None:
            return False, 0.0
        return rules.can_fetch(url, ROBOTS_TOKEN), float(rules.crawl_delay(ROBOTS_TOKEN) or 0.0)


class HostGate:
    """Leave a configurable gap between requests to one host."""

    def __init__(self, delay: float, sleep: Sleep) -> None:
        self.delay = delay
        self.sleep = sleep
        self.next_ok: dict[str, float] = {}
        self.locks: dict[str, asyncio.Lock] = {}

    async def wait(self, host: str, crawl_delay: float = 0.0) -> None:
        async with self.locks.setdefault(host, asyncio.Lock()):
            pause = self.next_ok.get(host, 0.0) - time.monotonic()
            if pause > 0:
                await self.sleep(pause)
            self.next_ok[host] = time.monotonic() + max(self.delay, crawl_delay)


def make_client(max_concurrency: int = 4) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(30.0, connect=10.0),
        limits=httpx.Limits(max_connections=max_concurrency),
        follow_redirects=True,
    )


async def _download(client: httpx.AsyncClient, src: Source, root: Path, raw_dir: Path) -> dict:
    async with client.stream("GET", src.url) as response:
        if response.status_code != 200:
            raise DownloadError(
                f"HTTP {response.status_code}",
                code=response.status_code,
                retry_after=retry_after_seconds(response.headers.get("Retry-After")),
            )
        content_type = response.headers.get("Content-Type", "")
        name = file_stem(src.url) + pick_ext(src.url, content_type)
        target = raw_dir / slug(src.source) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(name + ".part")
        digest, size = hashlib.sha256(), 0
        try:
            with part.open("wb") as handle:
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise DownloadError(f"larger than {MAX_BYTES // 2**20} MB")
                    digest.update(chunk)
                    handle.write(chunk)
            part.replace(target)
        finally:
            part.unlink(missing_ok=True)
    return {
        "path": target.relative_to(root).as_posix(),
        "bytes": size,
        "sha256": digest.hexdigest(),
        "content_type": content_type.split(";")[0].strip(),
        "http_status": 200,
        "etag": response.headers.get("ETag", ""),
    }


async def fetch_one(
    client: httpx.AsyncClient,
    src: Source,
    *,
    root: Path,
    raw_dir: Path,
    robots: Robots,
    gate: HostGate,
    slots: asyncio.Semaphore,
    max_attempts: int,
    sleep: Sleep,
) -> dict:
    record = {
        "url": src.url,
        "source": src.source,
        "licence": src.licence,
        "title": src.title,
        "via": "http",
    }
    allowed, crawl_delay = await robots.check(src.url)
    if not allowed:
        return record | {"status": "blocked", "error": "robots.txt", "fetched_at": now_iso()}
    host = urlsplit(src.url).netloc
    error, code, attempt = "", None, 0
    for attempt in range(1, max_attempts + 1):
        wait = backoff_delay(attempt - 1)
        async with slots:
            await gate.wait(host, crawl_delay)
            try:
                async with asyncio.timeout(ATTEMPT_TIMEOUT):
                    fields = await _download(client, src, root, raw_dir)
                return (
                    record
                    | fields
                    | {"status": "downloaded", "attempts": attempt, "fetched_at": now_iso()}
                )
            except DownloadError as exc:
                error, code = str(exc), exc.code
                if code not in RETRYABLE:
                    break
                if exc.retry_after is not None:
                    if exc.retry_after > MAX_WAIT:
                        error = f"{error}: asked to wait {exc.retry_after:.0f} s, run again later"
                        break
                    wait = max(wait, exc.retry_after)
            except (httpx.TransportError, TimeoutError) as exc:
                error, code = type(exc).__name__, None
            except httpx.HTTPError as exc:
                error, code = type(exc).__name__, None
                break
        if attempt < max_attempts:
            await sleep(min(wait, MAX_WAIT))
    return record | {
        "status": "failed",
        "http_status": code,
        "error": error,
        "attempts": attempt,
        "fetched_at": now_iso(),
    }


async def fetch_all(
    sources: list[Source],
    *,
    root: Path = Path("."),
    max_concurrency: int = 4,
    per_host_delay: float = 0.5,
    max_attempts: int = 4,
    client: httpx.AsyncClient | None = None,
    sleep: Sleep = asyncio.sleep,
    on_result: Callable[[dict], None] | None = None,
) -> dict[str, int]:
    """Download every source not already complete and return status counts."""
    raw_dir = root / "data" / "raw"
    manifest = Manifest(root / "data" / "manifest.jsonl")
    todo = [src for src in sources if not manifest.done(src.url, root)]
    counts = {"downloaded": 0, "skipped": len(sources) - len(todo), "blocked": 0, "failed": 0}
    own_client = client is None
    active = client or make_client(max_concurrency)
    robots = Robots(active)
    gate = HostGate(per_host_delay, sleep)
    slots = asyncio.Semaphore(max_concurrency)
    try:
        tasks = [
            asyncio.create_task(
                fetch_one(
                    active,
                    src,
                    root=root,
                    raw_dir=raw_dir,
                    robots=robots,
                    gate=gate,
                    slots=slots,
                    max_attempts=max_attempts,
                    sleep=sleep,
                )
            )
            for src in todo
        ]
        for finished in asyncio.as_completed(tasks):
            record = await finished
            counts[record["status"]] += 1
            before = manifest.records.get(record["url"], {})
            same_problem = (before.get("status"), before.get("error")) == (
                record["status"],
                record.get("error"),
            )
            if record["status"] == "downloaded" or not same_problem:
                manifest.add(record)
            if on_result:
                on_result(record)
    finally:
        if own_client:
            await active.aclose()
    return counts


async def discover_sitemap(
    url: str, *, include: Iterable[str] = (), exclude: Iterable[str] = (), limit: int = 300
) -> list[str]:
    """Read a sitemap and return filtered URLs; this door never downloads files."""
    async with make_client(1) as client:
        response = await client.get(url)
        response.raise_for_status()
    urls = re.findall(r"<loc>\s*(.*?)\s*</loc>", response.text, flags=re.IGNORECASE)
    includes, excludes = tuple(include), tuple(exclude)
    return [
        candidate
        for candidate in urls
        if all(part in candidate for part in includes)
        and not any(part in candidate for part in excludes)
    ][:limit]


async def repo_sources(
    owner_repo: str,
    *,
    path: str,
    ext: str,
    source: str,
    licence: str,
    ref: str = "master",
    limit: int = 300,
) -> list[Source]:
    """Discover files in a public GitHub tree as Source rows."""
    api = f"https://api.github.com/repos/{owner_repo}/git/trees/{ref}?recursive=1"
    async with make_client(1) as client:
        response = await client.get(api, headers={"Accept": "application/vnd.github+json"})
        response.raise_for_status()
        payload = response.json()
    prefix = path.strip("/") + "/" if path.strip("/") else ""
    rows = [
        item
        for item in payload.get("tree", [])
        if item.get("type") == "blob"
        and item.get("path", "").startswith(prefix)
        and item["path"].endswith(ext)
    ]
    return [
        Source(
            f"https://raw.githubusercontent.com/{owner_repo}/{ref}/{item['path']}",
            source,
            licence,
            item["path"],
        )
        for item in rows[:limit]
    ]


def register_manual(
    folder: Path, *, from_url: str, source: str, licence: str, root: Path = Path(".")
) -> int:
    """Register browser-downloaded files without pretending they were fetched by HTTP."""
    manifest = Manifest(root / "data" / "manifest.jsonl")
    added = 0
    for file in sorted(folder.glob("**/*")):
        if not file.is_file() or file.name.endswith(".part"):
            continue
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        relative = file.relative_to(root).as_posix()
        record = {
            "url": from_url,
            "source": source,
            "licence": licence,
            "title": file.name,
            "via": "manual",
            "path": relative,
            "bytes": file.stat().st_size,
            "sha256": digest,
            "status": "downloaded",
            "attempts": 1,
            "fetched_at": now_iso(),
        }
        manifest.add(record)
        added += 1
    return added

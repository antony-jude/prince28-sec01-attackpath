"""Command line doors for the ATTACKpath corpus fetcher."""

from __future__ import annotations

import argparse
import asyncio
import csv
from pathlib import Path

from attackpath.ingest.fetch import (
    Source,
    discover_sitemap,
    fetch_all,
    read_sources,
    register_manual,
    repo_sources,
)

ROOT = Path(__file__).resolve().parents[1]


def add_source_rows(path: Path, sources: list[Source]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        for source in sources:
            writer.writerow([source.url, source.source, source.licence, source.title])
    return len(sources)


def print_result(record: dict) -> None:
    if record["status"] == "downloaded":
        path = record.get("path", "")
        print(
            f"[{record.get('attempts', 1):4}] downloaded {record.get('bytes', 0):10,} bytes  {path}"
        )
    else:
        print(f"[{record['status']:>10}] {record['url']} {record.get('error', '')}")


async def main_async(args: argparse.Namespace) -> int:
    if args.door == "urls":
        sources = read_sources(ROOT / args.csv)
        counts = await fetch_all(
            sources,
            root=ROOT,
            max_concurrency=args.max_concurrency,
            per_host_delay=args.delay,
            on_result=print_result,
        )
        summary = (
            f"sources={len(sources)} downloaded={counts['downloaded']} "
            f"skipped={counts['skipped']} blocked={counts['blocked']} "
            f"failed={counts['failed']}"
        )
        print(summary)
        return 0 if counts["failed"] == 0 else 1
    if args.door == "repo":
        sources = await repo_sources(
            args.owner_repo,
            path=args.path,
            ext=args.ext,
            source=args.source,
            licence=args.licence,
            ref=args.ref,
            limit=args.limit,
        )
        added = add_source_rows(ROOT / args.csv, sources)
        print(f"repo={args.owner_repo} discovered={len(sources)} added_to_sources={added}")
        return 0
    if args.door == "sitemap":
        urls = await discover_sitemap(
            args.url, include=args.include, exclude=args.exclude, limit=args.limit
        )
        sources = [Source(url, args.source, args.licence, "") for url in urls]
        added = add_source_rows(ROOT / args.csv, sources)
        print(f"sitemap_urls={len(urls)} added_to_sources={added}")
        return 0
    added = register_manual(
        ROOT / args.folder,
        from_url=args.from_url,
        source=args.source,
        licence=args.licence,
        root=ROOT,
    )
    print(f"folder={args.folder} added={added}")
    return 0


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="door", required=True)
    urls = sub.add_parser("urls", help="download licensed rows from data/sources.csv")
    urls.add_argument("csv", nargs="?", default="data/sources.csv")
    urls.add_argument("--delay", type=float, default=0.5)
    urls.add_argument("--max-concurrency", type=int, default=4)
    repo = sub.add_parser("repo", help="discover files in a public GitHub repository")
    repo.add_argument("owner_repo")
    repo.add_argument("--path", required=True)
    repo.add_argument("--ext", required=True)
    repo.add_argument("--source", required=True)
    repo.add_argument("--licence", required=True)
    repo.add_argument("--ref", default="master")
    repo.add_argument("--limit", type=int, default=300)
    repo.add_argument("--csv", default="data/sources.csv")
    sitemap = sub.add_parser("sitemap", help="discover URLs without downloading files")
    sitemap.add_argument("url")
    sitemap.add_argument("--include", action="append", default=[])
    sitemap.add_argument("--exclude", action="append", default=[])
    sitemap.add_argument("--limit", type=int, default=300)
    sitemap.add_argument("--source", required=True)
    sitemap.add_argument("--licence", required=True)
    sitemap.add_argument("--csv", default="data/sources.csv")
    manual = sub.add_parser("manual", help="register browser-downloaded files")
    manual.add_argument("folder")
    manual.add_argument("--from-url", required=True)
    manual.add_argument("--source", required=True)
    manual.add_argument("--licence", required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async(parser().parse_args())))

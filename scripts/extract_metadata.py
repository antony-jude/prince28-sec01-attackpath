import argparse
import asyncio

from attackpath.config import get_settings
from attackpath.db.session import make_engine, make_sessionmaker
from attackpath.llm.doc_meta import DocMeta
from attackpath.llm.extract import run
from attackpath.llm.gateway import build_gateway
from attackpath.llm.prompts import latest, read_prompt


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--rpm", type=float, default=12)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--schema", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    engine = make_engine(settings)
    version = latest(settings.prompts_dir, "extract")
    counts = await run(
        make_sessionmaker(engine),
        build_gateway(settings),
        DocMeta,
        read_prompt(settings.prompts_dir, version),
        version,
        limit=args.limit,
        rpm=args.rpm,
        retry_failed=args.retry_failed,
        native=args.schema,
    )
    print(f"prompt={version} {dict(counts)}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

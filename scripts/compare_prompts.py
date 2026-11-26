"""Score versioned classifier prompts, caching replies by prompt and question."""

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

from attackpath.config import get_settings
from attackpath.llm.classify import classify, find_leaks
from attackpath.llm.gateway import build_gateway
from attackpath.llm.prompts import read_prompt, versions


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpm", type=float, default=12)
    args = parser.parse_args()
    root = Path(__file__).parents[1]
    cache_dir = root / "eval/cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        json.loads(line) for line in (root / "eval/prompt_testset.jsonl").read_text().splitlines()
    ]
    settings = get_settings()
    gateway = build_gateway(settings)
    for version in versions(settings.prompts_dir, "classify"):
        prompt = read_prompt(settings.prompts_dir, version)
        assert not find_leaks(prompt, [r["question"] for r in rows]), f"LEAK in {version}"
        answers = []
        matrix = Counter()
        for row in rows:
            key = f"{version}:{row['question']}"
            path = cache_dir / (str(abs(hash(key))) + ".json")
            if path.exists():
                got = json.loads(path.read_text())["got"]
            else:
                got, _ = await classify(gateway, prompt, version, row["question"])
                path.write_text(json.dumps({"got": got}))
            answers.append(got)
            matrix[(row["label"], got)] += 1
            await asyncio.sleep(60 / args.rpm)
        score = sum(got == row["label"] for got, row in zip(answers, rows, strict=True))
        print(f"{version} {score}/{len(rows)} {score / len(rows):.0%}")
        for (wanted, got), count in sorted(matrix.items()):
            print(f"  {wanted} -> {got}: {count}")


if __name__ == "__main__":
    asyncio.run(main())

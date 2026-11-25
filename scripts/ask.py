import argparse
import asyncio
import json
import time

import httpx


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("message")
    p.add_argument("--url", default="http://localhost:8000")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    async with httpx.AsyncClient(timeout=120) as client:
        if a.json:
            response = await client.post(
                a.url.rstrip("/") + "/v1/chat", json={"message": a.message, "stream": False}
            )
            print(json.dumps(response.json(), ensure_ascii=False, indent=2))
            return
        started = time.perf_counter()
        first = None
        async with client.stream(
            "POST", a.url.rstrip("/") + "/v1/chat", json={"message": a.message, "stream": True}
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    item = json.loads(line[6:])
                    if "delta" in item:
                        if first is None:
                            first = time.perf_counter()
                            print(f"first words after {first - started:.2f}s")
                        print(item["delta"], end="", flush=True)
                    elif "provider" in item:
                        print(
                            f"\n--- {item['provider']} / {item['model']} cost Rs {item['cost_inr']}"
                        )
        print()


if __name__ == "__main__":
    asyncio.run(main())

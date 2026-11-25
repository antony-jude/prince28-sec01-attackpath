import asyncio
import time

from attackpath.config import get_settings
from attackpath.llm.gateway import OpenAICompatProvider


async def main():
    s = get_settings()
    for name, url, key, model in [
        ("gemini", s.llm_primary_base_url, s.gemini_api_key, s.llm_primary_model),
        ("groq", s.llm_fallback_base_url, s.groq_api_key, s.llm_fallback_model),
    ]:
        if not key:
            print(f"{name} NO KEY")
            continue
        started = time.perf_counter()
        try:
            reply = await OpenAICompatProvider(
                name, url, key, model, timeout=s.llm_timeout_seconds
            ).generate([{"role": "user", "content": "Say pong"}])
            print(
                f"{name} OK {model} said {reply.text!r} in {int((time.perf_counter() - started) * 1000)} ms tokens in={reply.tokens_in} out={reply.tokens_out}"
            )
        except Exception as exc:
            print(f"{name} FAILED {exc}")


if __name__ == "__main__":
    asyncio.run(main())

"""Small OpenAI-compatible gateway with retry, fallback and cost accounting."""

import asyncio
import json
import logging
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import httpx

from attackpath.config import Settings
from attackpath.logging_setup import request_id_ctx

log = logging.getLogger("attackpath.llm")
PRICES_USD = {
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "openai/gpt-oss-20b": (0.075, 0.30),
    "openai/gpt-oss-120b": (0.15, 0.60),
}
Message = dict[str, str]
Recorder = Callable[[dict], Awaitable[None]]


class LLMError(Exception):
    def __init__(self, message: str, *, retryable: bool, retry_after: float | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


class LLMUnavailable(Exception):
    pass


@dataclass
class Reply:
    text: str = ""
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    attempts: int
    fallback_used: bool
    cost_inr: float


def cost_inr(model: str, tokens_in: int, tokens_out: int, usd_inr: float) -> float:
    pin, pout = PRICES_USD.get(model, (0.0, 0.0))
    return round((tokens_in * pin + tokens_out * pout) / 1_000_000 * usd_inr, 6)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class OpenAICompatProvider:
    def __init__(self, name, base_url, api_key, model, *, timeout=30.0, client=None):
        self.name, self.model = name, model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0))

    def _body(self, messages, temperature, stream):
        body = {"model": self.model, "messages": messages, "temperature": temperature}
        if stream:
            body |= {"stream": True, "stream_options": {"include_usage": True}}
        return body

    @staticmethod
    def _error(response):
        wait = response.headers.get("retry-after", "")
        retry_after = float(wait) if wait.replace(".", "", 1).isdigit() else None
        return LLMError(
            f"HTTP {response.status_code}: {response.text[:200]}",
            retryable=response.status_code in {408, 429} or response.status_code >= 500,
            retry_after=retry_after,
        )

    async def generate(self, messages, *, temperature=0.2):
        try:
            response = await self._client.post(
                self._url, headers=self._headers, json=self._body(messages, temperature, False)
            )
        except httpx.TransportError as exc:
            raise LLMError(
                type(exc).__name__, retryable=not isinstance(exc, httpx.TimeoutException)
            ) from exc
        if response.status_code != 200:
            raise self._error(response)
        data = response.json()
        usage = data.get("usage") or {}
        return Reply(
            data["choices"][0]["message"].get("content") or "",
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
        )

    async def stream(self, messages, usage, *, temperature=0.2) -> AsyncIterator[str]:
        try:
            async with self._client.stream(
                "POST",
                self._url,
                headers=self._headers,
                json=self._body(messages, temperature, True),
            ) as response:
                if response.status_code != 200:
                    await response.aread()
                    raise self._error(response)
                finished = False
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        finished = True
                        break
                    chunk = json.loads(payload)
                    if chunk.get("usage"):
                        usage.tokens_in = chunk["usage"].get("prompt_tokens", 0)
                        usage.tokens_out = chunk["usage"].get("completion_tokens", 0)
                    for choice in chunk.get("choices") or []:
                        finished = finished or bool(choice.get("finish_reason"))
                        piece = (choice.get("delta") or {}).get("content")
                        if piece:
                            yield piece
                if not finished:
                    raise LLMError("the stream ended early", retryable=True)
        except httpx.TransportError as exc:
            raise LLMError(
                type(exc).__name__, retryable=not isinstance(exc, httpx.TimeoutException)
            ) from exc


class FakeLLM:
    def __init__(self, name="fake", model="fake-1", script=None):
        self.name, self.model, self.script, self.calls = name, model, list(script or []), 0

    def _next(self):
        self.calls += 1
        return self.script.pop(0) if self.script else "A fake answer."

    async def generate(self, messages, *, temperature=0.2):
        item = self._next()
        if isinstance(item, Exception):
            raise item
        return Reply(str(item), 12, len(str(item).split()))

    async def stream(self, messages, usage, *, temperature=0.2):
        item = self._next()
        error = item[1] if isinstance(item, tuple) else None
        if isinstance(item, Exception):
            raise item
        words = ("Half an answer" if error else str(item)).split()
        for word in words:
            yield word + " "
        if error:
            raise error
        usage.tokens_in, usage.tokens_out = 12, len(words)


class CircuitBreaker:
    def __init__(self, threshold=3, cooldown=30.0, clock=time.monotonic):
        self.threshold, self.cooldown, self._clock, self.failures, self._opened_at = (
            threshold,
            cooldown,
            clock,
            0,
            None,
        )

    @property
    def state(self):
        if self._opened_at is None:
            return "closed"
        return "half-open" if self._clock() - self._opened_at >= self.cooldown else "open"

    def allow(self):
        return self.state != "open"

    def success(self):
        self.failures, self._opened_at = 0, None

    def failure(self):
        self.failures += 1
        if self.failures >= self.threshold:
            self._opened_at = self._clock()


class LLMGateway:
    def __init__(
        self,
        providers,
        *,
        recorder=None,
        usd_inr=95.0,
        max_attempts=2,
        sleep=asyncio.sleep,
        clock=time.monotonic,
        breaker_threshold=3,
        breaker_cooldown=30.0,
    ):
        self.providers = providers
        self.breakers = {
            p.name: CircuitBreaker(breaker_threshold, breaker_cooldown, clock) for p in providers
        }
        self._recorder, self._usd_inr, self._max_attempts, self._sleep, self._clock = (
            recorder,
            usd_inr,
            max_attempts,
            sleep,
            clock,
        )

    async def _record(self, provider, purpose, prompt_version, **fields):
        row = {
            "request_id": request_id_ctx.get(),
            "provider": provider.name,
            "model": provider.model,
            "purpose": purpose,
            "prompt_version": prompt_version,
            **fields,
        }
        log.info("llm call %s %s %s", provider.name, provider.model, fields.get("status"))
        if self._recorder:
            try:
                await self._recorder(row)
            except Exception:
                log.exception("could not record the llm call")

    def _result(self, provider, messages, reply, started, attempts, index):
        ti = reply.tokens_in or estimate_tokens(" ".join(m["content"] for m in messages))
        to = reply.tokens_out or estimate_tokens(reply.text)
        return LLMResult(
            reply.text,
            provider.name,
            provider.model,
            ti,
            to,
            int((self._clock() - started) * 1000),
            attempts,
            index > 0,
            cost_inr(provider.model, ti, to, self._usd_inr),
        )

    async def generate(self, messages, *, purpose="chat", prompt_version="", **options):
        problems = []
        for index, provider in enumerate(self.providers):
            breaker = self.breakers[provider.name]
            if not breaker.allow():
                problems.append(f"{provider.name}: circuit open")
                continue
            started = self._clock()
            last = None
            for attempt in range(1, self._max_attempts + 1):
                try:
                    reply = await provider.generate(messages, **options)
                    breaker.success()
                    result = self._result(provider, messages, reply, started, attempt, index)
                    await self._record(
                        provider,
                        purpose,
                        prompt_version,
                        status="ok",
                        tokens_in=result.tokens_in,
                        tokens_out=result.tokens_out,
                        latency_ms=result.latency_ms,
                        cost_inr=result.cost_inr,
                        fallback_used=result.fallback_used,
                    )
                    return result
                except LLMError as exc:
                    last = exc
                    if not exc.retryable or attempt == self._max_attempts:
                        break
                    await self._sleep(min(exc.retry_after or random.uniform(0, 2**attempt), 20.0))
            breaker.failure()
            problems.append(f"{provider.name}: {last}")
            await self._record(
                provider,
                purpose,
                prompt_version,
                status="error",
                error=str(last),
                tokens_in=0,
                tokens_out=0,
                latency_ms=int((self._clock() - started) * 1000),
                cost_inr=0,
                fallback_used=index > 0,
            )
        raise LLMUnavailable("; ".join(problems) or "no LLM provider is configured")

    async def stream(self, messages, *, purpose="chat", prompt_version="", **options):
        for index, provider in enumerate(self.providers):
            breaker = self.breakers[provider.name]
            if not breaker.allow():
                continue
            usage, started, pieces = Reply(), self._clock(), []
            try:
                async for piece in provider.stream(messages, usage, **options):
                    pieces.append(piece)
                    yield piece
                breaker.success()
                result = self._result(
                    provider,
                    messages,
                    Reply("".join(pieces), usage.tokens_in, usage.tokens_out),
                    started,
                    1,
                    index,
                )
                await self._record(
                    provider,
                    purpose,
                    prompt_version,
                    status="ok",
                    tokens_in=result.tokens_in,
                    tokens_out=result.tokens_out,
                    latency_ms=result.latency_ms,
                    cost_inr=result.cost_inr,
                    fallback_used=result.fallback_used,
                )
                yield result
                return
            except LLMError as exc:
                breaker.failure()
                await self._record(
                    provider,
                    purpose,
                    prompt_version,
                    status="error",
                    error=str(exc),
                    tokens_in=0,
                    tokens_out=0,
                    latency_ms=int((self._clock() - started) * 1000),
                    cost_inr=0,
                    fallback_used=index > 0,
                )
                if pieces:
                    raise LLMUnavailable(f"stream failed after partial answer: {exc}") from exc
        raise LLMUnavailable("no provider could answer")


def build_gateway(settings: Settings, recorder=None):
    wanted = [
        (
            "gemini",
            settings.llm_primary_base_url,
            settings.gemini_api_key,
            settings.llm_primary_model,
        ),
        (
            "groq",
            settings.llm_fallback_base_url,
            settings.groq_api_key,
            settings.llm_fallback_model,
        ),
    ]
    return LLMGateway(
        [
            OpenAICompatProvider(*item, timeout=settings.llm_timeout_seconds)
            for item in wanted
            if item[2]
        ],
        recorder=recorder,
        usd_inr=settings.usd_inr,
    )

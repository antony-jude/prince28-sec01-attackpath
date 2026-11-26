import asyncio

import pytest

from attackpath.llm.gateway import (
    FakeLLM,
    LLMError,
    LLMGateway,
    LLMUnavailable,
)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_generate_falls_back_after_primary_failure():
    primary = FakeLLM("gemini", script=[LLMError("primary down", retryable=False)])
    fallback = FakeLLM("groq", script=["fallback answer"])
    gateway = LLMGateway([primary, fallback], max_attempts=1)

    result = asyncio.run(gateway.generate([{"role": "user", "content": "hello"}]))

    assert result.text == "fallback answer"
    assert result.provider == "groq"
    assert result.fallback_used is True
    assert primary.calls == fallback.calls == 1


def test_circuit_opens_then_half_opens_and_recovers():
    clock = Clock()
    primary = FakeLLM(
        "gemini",
        script=[
            LLMError("down", retryable=False),
            LLMError("down", retryable=False),
            LLMError("down", retryable=False),
            "recovered",
        ],
    )
    fallback = FakeLLM("groq", script=["backup"] * 4)
    gateway = LLMGateway(
        [primary, fallback],
        max_attempts=1,
        clock=clock,
        breaker_threshold=3,
        breaker_cooldown=30,
    )

    for _ in range(3):
        result = asyncio.run(gateway.generate([{"role": "user", "content": "hello"}]))
        assert result.provider == "groq"
    assert gateway.breakers["gemini"].state == "open"
    skipped = asyncio.run(gateway.generate([{"role": "user", "content": "hello"}]))
    assert skipped.provider == "groq"
    assert primary.calls == 3

    clock.now = 30
    recovered = asyncio.run(gateway.generate([{"role": "user", "content": "hello"}]))
    assert recovered.provider == "gemini"
    assert gateway.breakers["gemini"].state == "closed"


def test_stream_never_switches_provider_after_partial_answer():
    primary = FakeLLM(
        "gemini",
        script=[("partial answer", LLMError("stream broke", retryable=True))],
    )
    fallback = FakeLLM("groq", script=["fallback should not appear"])
    gateway = LLMGateway([primary, fallback], max_attempts=1)

    async def consume():
        pieces = []
        with pytest.raises(LLMUnavailable, match="partial answer"):
            async for piece in gateway.stream([{"role": "user", "content": "hello"}]):
                pieces.append(piece)
        return pieces

    pieces = asyncio.run(consume())

    assert pieces == ["Half ", "an ", "answer "]
    assert fallback.calls == 0

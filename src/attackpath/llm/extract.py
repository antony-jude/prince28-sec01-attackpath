"""Ask, parse, validate, repair, and store structured document metadata."""

import asyncio
import json
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from attackpath.db.models import Document, Page
from attackpath.llm.gateway import LLMGateway, LLMUnavailable

RESERVED = {"source", "path", "parser", "pages", "tables", "chars", "extract"}


def parse_json(reply: str) -> dict:
    start, end = reply.find("{"), reply.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("the reply contains no JSON object")
    value = json.loads(reply[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("the JSON is not an object")
    return value


def explain(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "; ".join(
            f"{'.'.join(map(str, p['loc'])) or 'object'}: {p['msg']}" for p in error.errors()[:6]
        )
    return str(error)


@dataclass
class Extraction:
    record: BaseModel | None
    attempts: int = 0
    errors: list[str] = field(default_factory=list)
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_inr: float = 0.0


async def extract(
    gateway: LLMGateway,
    schema: type[BaseModel],
    prompt: str,
    version: str,
    title: str,
    text: str,
    *,
    max_attempts: int = 3,
    native_schema: bool = False,
) -> Extraction:
    json_schema = schema.model_json_schema()
    system = f"{prompt}\n\nThe JSON object must match this JSON schema:\n{json.dumps(json_schema)}"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Title: {title}\n<document>\n{text}\n</document>"},
    ]
    options: dict = {"temperature": 0}
    if native_schema:
        options["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "schema": json_schema},
        }
    out = Extraction(record=None)
    for attempt in range(1, max_attempts + 1):
        result = await gateway.generate(
            messages, purpose="extract", prompt_version=version, **options
        )
        out.attempts, out.model = attempt, result.model
        out.tokens_in += result.tokens_in
        out.tokens_out += result.tokens_out
        out.cost_inr += result.cost_inr
        try:
            out.record = schema.model_validate(parse_json(result.text))
            return out
        except (ValueError, ValidationError) as error:
            out.errors.append(explain(error))
            messages += [
                {"role": "assistant", "content": result.text},
                {
                    "role": "user",
                    "content": (
                        f"That reply was rejected: {out.errors[-1]}. "
                        "Reply again with only corrected JSON."
                    ),
                },
            ]
    return out


async def pending(
    session: AsyncSession, version: str, *, limit: int = 0, retry_failed: bool = False
) -> list[Document]:
    note = Document.metadata_["extract"]
    stmt = select(Document).where(Document.doc_type != "record")
    stmt = stmt.where(
        or_(note["prompt"].astext.is_distinct_from(version), note["error"].astext.is_not(None))
        if retry_failed
        else note["prompt"].astext.is_distinct_from(version)
    )
    return list(
        await session.scalars(
            stmt.order_by(Document.id).limit(limit) if limit else stmt.order_by(Document.id)
        )
    )


async def document_text(session: AsyncSession, document: Document, chars: int = 6000) -> str:
    stmt = select(Page.text).where(Page.document_id == document.id).order_by(Page.page_no).limit(3)
    return "\n\n".join(await session.scalars(stmt))[:chars]


async def save(session: AsyncSession, document: Document, result: Extraction, version: str) -> None:
    note = {"prompt": version, "model": result.model, "attempts": result.attempts}
    fields = result.record.model_dump(mode="json") if result.record else {}
    if result.record is None:
        note["error"] = result.errors[-1][:300]
    document.metadata_ = {**document.metadata_, **fields, "extract": note}
    await session.commit()


async def run(
    sessionmaker: async_sessionmaker,
    gateway: LLMGateway,
    schema: type[BaseModel],
    prompt: str,
    version: str,
    *,
    limit: int = 0,
    rpm: float = 12,
    chars: int = 6000,
    retry_failed: bool = False,
    native: bool = False,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    echo: Callable[[str], None] = print,
) -> Counter:
    clash = RESERVED & set(schema.model_fields)
    if clash:
        raise ValueError(f"rename these fields, the parser already uses them: {sorted(clash)}")
    counts = Counter()
    async with sessionmaker() as session:
        todo = await pending(session, version, limit=limit, retry_failed=retry_failed)
        counts["pending"] = len(todo)
        for number, document in enumerate(todo, 1):
            text = await document_text(session, document, chars)
            try:
                result = await extract(
                    gateway, schema, prompt, version, document.title, text, native_schema=native
                )
            except LLMUnavailable as error:
                echo(f"stopped: no model can answer ({error})")
                counts["stopped"] = 1
                return counts
            await save(session, document, result, version)
            counts["ok" if result.record else "failed"] += 1
            counts["repaired"] += result.attempts > 1
            counts["tokens_in"] += result.tokens_in
            counts["tokens_out"] += result.tokens_out
            counts["cost_inr"] += result.cost_inr
            if number % 10 == 0:
                echo(f"... {number} of {len(todo)} documents")
            if number < len(todo):
                await sleep(60 / rpm)
    return counts

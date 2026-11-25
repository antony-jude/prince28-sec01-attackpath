import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from attackpath.api.deps import check_db, get_repository
from attackpath.api.main import create_app
from attackpath.config import Settings

SAMPLE: list[dict[str, Any]] = [
    {"id": "001", "title": "Alpha guideline", "year": 2023},
    {"id": "002", "title": "Beta circular", "year": 2024},
    {"id": "003", "title": "Gamma notice", "year": 2025},
]


@pytest.fixture
def data_file(tmp_path: Path) -> Path:
    path = tmp_path / "records.json"
    path.write_text(json.dumps(SAMPLE), encoding="utf-8")
    return path


@pytest.fixture
def db_state() -> dict[str, bool]:
    return {"up": True}


@pytest.fixture
def client(data_file: Path, db_state: dict[str, bool]) -> Iterator[TestClient]:
    settings = Settings(app_env="ci", data_file=data_file, _env_file=None)
    with TestClient(create_app(settings)) as test_client:

        class FakeRepository:
            async def list(self, *, q, filters, limit, offset, sort="external_id"):
                items = [
                    record
                    for record in SAMPLE
                    if (not q or q.casefold() in json.dumps(record).casefold())
                    and all(str(record.get(key)) == value for key, value in filters.items())
                ]
                descending = sort.startswith("-")
                sort_field = sort.removeprefix("-")
                if sort_field in {"title", "published_on", "external_id"}:
                    items.sort(
                        key=lambda record: str(record.get(sort_field, record["id"])),
                        reverse=descending,
                    )
                return len(items), items[offset : offset + limit]

            async def get(self, external_id):
                for record in SAMPLE:
                    if record["id"] == external_id:
                        return record
                return None

            async def get_page(self, external_id, page_no):
                if external_id == "001" and page_no == 1:
                    return {
                        "document_id": external_id,
                        "page_no": page_no,
                        "headings": ["Guidelines"],
                        "text": "Alpha page",
                    }
                return None

        class FakeSession:
            async def execute(self, *_args, **_kwargs):
                return None

        class FakeSessionContext:
            async def __aenter__(self):
                return FakeSession()

            async def __aexit__(self, *_args):
                return False

        test_client.app.state.session_factory = lambda: FakeSessionContext()
        test_client.app.dependency_overrides[get_repository] = lambda: FakeRepository()
        test_client.app.dependency_overrides[check_db] = lambda: db_state["up"]
        yield test_client

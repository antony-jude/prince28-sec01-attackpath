import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

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
def client(data_file: Path) -> Iterator[TestClient]:
    settings = Settings(app_env="ci", data_file=data_file, _env_file=None)
    with TestClient(create_app(settings)) as test_client:
        yield test_client

import importlib.util
from pathlib import Path

loader_path = Path(__file__).parents[2] / "scripts" / "load_db.py"
loader_spec = importlib.util.spec_from_file_location("load_db", loader_path)
assert loader_spec and loader_spec.loader
loader = importlib.util.module_from_spec(loader_spec)
loader_spec.loader.exec_module(loader)

stale_document_ids = loader.stale_document_ids
to_row = loader.to_row


def test_stale_document_ids_returns_only_missing_records() -> None:
    source = [{"id": "001"}, {"id": "002"}]

    assert stale_document_ids(source, {"001", "002", "003", "004"}) == ["003", "004"]


def test_to_row_promotes_technique_id() -> None:
    row = to_row({"id": "001", "technique_id": "T1059.001", "name": "PowerShell"})

    assert row["technique_id"] == "T1059.001"

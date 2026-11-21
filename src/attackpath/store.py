import json
from pathlib import Path
from typing import Any

Record = dict[str, Any]


def load_records(path: Path) -> list[Record]:
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("The records file must contain a JSON array.")

    seen_ids: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            raise ValueError(f"Record at index {index} must be an object with a string id.")
        if record["id"] in seen_ids:
            raise ValueError(f"Duplicate record id '{record['id']}'.")
        seen_ids.add(record["id"])
    return records

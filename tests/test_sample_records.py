import json
from pathlib import Path


def test_sample_records_have_twenty_unique_attck_techniques() -> None:
    sample_path = Path(__file__).parents[1] / "data" / "sample_records.json"
    records = json.loads(sample_path.read_text(encoding="utf-8"))

    assert len(records) == 20
    assert len({record["id"] for record in records}) == 20
    assert all(record["technique_id"].startswith("T") for record in records)
    assert all(record["name"] and record["tactic"] and record["platforms"] for record in records)
    assert all(record["data_sources"] for record in records)
    assert all(record["detection"] for record in records)
    assert all(
        record["mitigations"] is None or isinstance(record["mitigations"], list)
        for record in records
    )
    assert all(
        record["source_url"].startswith("https://attack.mitre.org/techniques/T")
        for record in records
    )

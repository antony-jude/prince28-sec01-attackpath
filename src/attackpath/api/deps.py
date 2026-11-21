from fastapi import HTTPException, Request

from attackpath.store import Record


def get_records(request: Request) -> list[Record]:
    records: list[Record] | None = getattr(request.app.state, "records", None)
    if records is None:
        raise HTTPException(status_code=503, detail="Records are not loaded.")
    return records

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from attackpath.api.deps import get_records
from attackpath.store import Record

router = APIRouter(prefix="/v1/documents", tags=["documents"])
RecordsDependency = Annotated[list[Record], Depends(get_records)]


@router.get("")
def list_documents(
    records: RecordsDependency,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    filtered = records
    if q:
        search_term = q.casefold()
        filtered = [record for record in records if search_term in str(record).casefold()]
    return {
        "items": filtered[offset : offset + limit],
        "total": len(filtered),
        "limit": limit,
        "offset": offset,
    }


@router.get("/{document_id}")
def get_document(
    document_id: str,
    records: RecordsDependency,
) -> Record:
    for record in records:
        if record["id"] == document_id:
            return record
    raise HTTPException(status_code=404, detail=f"No document with id '{document_id}'.")

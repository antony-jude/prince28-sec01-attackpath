from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from attackpath.api.deps import get_repository
from attackpath.db.repository import FILTER_KEY, DocumentRepository

router = APIRouter(prefix="/v1/documents", tags=["documents"])
RepositoryDependency = Annotated[DocumentRepository, Depends(get_repository)]


@router.get("")
async def list_documents(
    request: Request,
    repository: RepositoryDependency,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    reserved = {"q", "limit", "offset"}
    filters: dict[str, str] = {}
    for key, value in request.query_params.multi_items():
        if key in reserved:
            continue
        if not FILTER_KEY.fullmatch(key):
            raise HTTPException(status_code=400, detail=f"Invalid filter name '{key}'.")
        filters[key] = value
    total, items = await repository.list(q=q, filters=filters, limit=limit, offset=offset)
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "filters": filters,
    }


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    repository: RepositoryDependency,
) -> dict[str, Any]:
    document = await repository.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"No document with id '{document_id}'.")
    return document

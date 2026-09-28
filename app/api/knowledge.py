"""Managing the knowledge base: the documents replies are grounded in.

Until now a knowledge base could only be loaded by an operator running a
script, which meant nobody could onboard themselves.
"""
from fastapi import APIRouter, Depends, HTTPException

from app.core.security import CurrentUser, get_current_user, require_admin
from app.models.knowledge import (
    SourceDetail,
    SourceList,
    UpsertSourceRequest,
    UpsertSourceResponse,
)
from app.services.ingest import (
    IngestError,
    delete_source,
    get_source,
    list_sources,
    slugify,
    upsert_source,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("", response_model=SourceList)
async def list_knowledge(
    current_user: CurrentUser = Depends(get_current_user),
) -> SourceList:
    """Readable by any role: a reviewer needs to see what a reply was
    grounded in, even though they cannot change it."""
    sources = await list_sources(current_user.tenant_id)
    return SourceList(sources=[s.__dict__ for s in sources])


@router.get("/{source_id}", response_model=SourceDetail)
async def get_knowledge_source(
    source_id: str, current_user: CurrentUser = Depends(get_current_user)
) -> SourceDetail:
    source = await get_source(current_user.tenant_id, source_id)
    if source is None:
        raise HTTPException(404, "No such document")
    return SourceDetail(**source)


@router.put("", response_model=UpsertSourceResponse)
async def upsert_knowledge_source(
    request: UpsertSourceRequest,
    current_user: CurrentUser = Depends(require_admin),
) -> UpsertSourceResponse:
    source_id = (request.source_id or slugify(request.title)).strip()
    try:
        chunk_count = await upsert_source(
            current_user.tenant_id,
            source_id=source_id,
            title=request.title,
            content=request.content,
        )
    except IngestError as e:
        raise HTTPException(400, str(e)) from e
    return UpsertSourceResponse(source_id=source_id, chunk_count=chunk_count)


@router.delete("/{source_id}", status_code=204)
async def delete_knowledge_source(
    source_id: str, current_user: CurrentUser = Depends(require_admin)
) -> None:
    if not await delete_source(current_user.tenant_id, source_id):
        raise HTTPException(404, "No such document")

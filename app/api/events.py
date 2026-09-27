"""The review queue API, which the console is built on.

Every route derives the tenant from the verified JWT, never from a path or
query parameter, so one tenant's console cannot address another's queue even
by guessing an event id - and row-level security is a second line behind
that, not the only one.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import CurrentUser, get_current_user, require_reviewer
from app.models.review import EventDetail, QueuePage, ReviewRequest
from app.services.events import (
    ReviewError,
    apply_review,
    get_event,
    list_events,
)

router = APIRouter(prefix="/events", tags=["review"])


@router.get("", response_model=QueuePage)
async def list_queue(
    status: str | None = Query(None, description="Filter by status, e.g. needs_review"),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None, description="created_at of the last item seen"),
    current_user: CurrentUser = Depends(get_current_user),
) -> QueuePage:
    try:
        items, next_cursor = await list_events(
            current_user.tenant_id, status=status, limit=limit, cursor=cursor
        )
    except ReviewError as e:
        raise HTTPException(400, str(e)) from e
    return QueuePage(items=items, next_cursor=next_cursor)


@router.get("/{event_id}", response_model=EventDetail)
async def get_queue_item(
    event_id: str, current_user: CurrentUser = Depends(get_current_user)
) -> EventDetail:
    event = await get_event(current_user.tenant_id, event_id)
    if event is None:
        # 404 rather than 403 for another tenant's id: distinguishing "exists
        # but not yours" from "does not exist" tells an attacker which ids are
        # real.
        raise HTTPException(404, "No such event")
    return EventDetail(**event)


@router.post("/{event_id}/review", response_model=EventDetail)
async def review_queue_item(
    event_id: str,
    request: ReviewRequest,
    current_user: CurrentUser = Depends(require_reviewer),
) -> EventDetail:
    try:
        await apply_review(
            tenant_id=current_user.tenant_id,
            event_id=event_id,
            action=request.action,
            actor_user_id=current_user.user_id,
            final_reply=request.final_reply,
            note=request.note,
        )
    except ReviewError as e:
        # A stale console tab acting on something already handled is a normal
        # race, not a server fault: 409 tells the client to reload.
        raise HTTPException(409, str(e)) from e

    event = await get_event(current_user.tenant_id, event_id)
    if event is None:
        raise HTTPException(404, "No such event")
    return EventDetail(**event)

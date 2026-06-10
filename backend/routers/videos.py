"""Legacy FastAPI video router.

The active runtime uses `backend.api_handler` instead of this router layer.
"""
from fastapi import APIRouter, HTTPException, Query
from ..models import VideoResponse, PaginatedVideos, FilterOptions
from .. import database as db

router = APIRouter(prefix="/api/videos", tags=["videos"])


@router.get("", response_model=PaginatedVideos)
def list_videos(
    keyword: str = "",
    source_id: int = Query(None),
    tag: str = "",
    category: str = "",
    favorite: int = Query(0),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
):
    items, total = db.query_videos(
        keyword=keyword,
        source_id=source_id,
        tag=tag,
        category=category,
        favorite_only=bool(favorite),
        page=page,
        page_size=page_size,
    )
    return PaginatedVideos(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total else 0,
    )


@router.get("/filters", response_model=FilterOptions)
def get_filters():
    sources = db.get_sources()
    return FilterOptions(
        tags=db.get_distinct_tags(),
        categories=db.get_distinct_categories(),
        sources=[{"id": s["id"], "name": s["name"]} for s in sources],
    )


@router.put("/{video_id}/favorite")
def toggle_favorite(video_id: int):
    result = db.toggle_favorite(video_id)
    if not result:
        raise HTTPException(404, "视频不存在")
    return result


@router.put("/{video_id}/watch")
def set_watch(video_id: int, status: str = Query(..., pattern="^(watched|unwatched)$")):
    result = db.set_watch_status(video_id, status)
    if not result:
        raise HTTPException(404, "视频不存在")
    return result

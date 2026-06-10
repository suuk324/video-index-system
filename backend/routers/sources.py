"""Legacy FastAPI source router.

The active runtime uses `backend.api_handler` instead of this router layer.
"""
from fastapi import APIRouter, HTTPException
from ..models import SourceCreate, SourceUpdate, SourceResponse
from .. import database as db

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("", response_model=list[SourceResponse])
def list_sources():
    return db.get_sources()


@router.post("", response_model=SourceResponse, status_code=201)
def create_source(data: SourceCreate):
    return db.create_source(data.model_dump())


@router.get("/{source_id}", response_model=SourceResponse)
def get_source(source_id: int):
    source = db.get_source(source_id)
    if not source:
        raise HTTPException(404, "视频源不存在")
    return source


@router.put("/{source_id}", response_model=SourceResponse)
def update_source(source_id: int, data: SourceUpdate):
    result = db.update_source(source_id, data.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(404, "视频源不存在")
    return result


@router.delete("/{source_id}")
def delete_source(source_id: int):
    if not db.delete_source(source_id):
        raise HTTPException(404, "视频源不存在")
    return {"ok": True}

"""Legacy FastAPI scan router.

The active runtime uses `backend.api_handler` instead of this router layer.
"""
from fastapi import APIRouter, HTTPException
from ..models import ScanResult
from ..services.scanner import scan_source, scan_all_enabled
from ..database import get_source

router = APIRouter(prefix="/api/scan", tags=["scan"])


@router.post("/{source_id}", response_model=ScanResult)
async def trigger_scan(source_id: int):
    source = get_source(source_id)
    if not source:
        raise HTTPException(404, "视频源不存在")
    return await scan_source(source_id)


@router.post("", response_model=list[ScanResult])
async def trigger_scan_all():
    return await scan_all_enabled()

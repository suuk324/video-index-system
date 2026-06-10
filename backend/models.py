"""Pydantic 数据模型"""
from pydantic import BaseModel, Field
from typing import Optional


# ── 视频源 ─────────────────────────────────────────────────────────

class SourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    category: str = ""
    url: str = Field(..., min_length=1)
    refresh_interval: int = Field(default=3600, ge=60)
    enabled: int = 1
    adapter_type: str = "generic"
    selector_title: str = ""
    selector_cover: str = ""
    selector_link: str = ""
    selector_desc: str = ""


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    url: Optional[str] = None
    refresh_interval: Optional[int] = None
    enabled: Optional[int] = None
    adapter_type: Optional[str] = None
    selector_title: Optional[str] = None
    selector_cover: Optional[str] = None
    selector_link: Optional[str] = None
    selector_desc: Optional[str] = None


class SourceResponse(BaseModel):
    id: int
    name: str
    category: str
    url: str
    refresh_interval: int
    enabled: int
    adapter_type: str
    selector_title: str
    selector_cover: str
    selector_link: str
    selector_desc: str
    created_at: str
    updated_at: str


# ── 视频 ───────────────────────────────────────────────────────────

class VideoResponse(BaseModel):
    id: int
    source_id: int
    title: str
    cover_url: str
    description: str
    tags: str
    keywords: str
    publish_time: str
    detail_url: str
    play_url: str
    play_type: str
    source_name: str
    is_favorite: int
    watch_status: str
    created_at: str
    updated_at: str


class PaginatedVideos(BaseModel):
    items: list[VideoResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ── 扫描 ───────────────────────────────────────────────────────────

class ScanResult(BaseModel):
    source_id: int
    source_name: str
    total_found: int
    new_added: int
    updated: int
    errors: list[str] = []


# ── 筛选项 ─────────────────────────────────────────────────────────

class FilterOptions(BaseModel):
    tags: list[str]
    categories: list[str]
    sources: list[dict]

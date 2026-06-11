"""Pydantic models for the promking router."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Site = Literal["fxv", "pkt"]
EmbedType = Literal["mp4", "hls"]
TaxonomyKind = Literal["actors", "studios", "categories"]


class TermRef(BaseModel):
    id: int
    name: str
    slug: str


class VideoListItem(BaseModel):
    id: int
    site: Site
    title: str
    slug: str
    thumbnail_url: Optional[str] = None
    preview_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    views: int = 0
    created_at: datetime
    actors: list[TermRef] = Field(default_factory=list)
    studios: list[TermRef] = Field(default_factory=list)
    qualities: Optional[list[dict]] = None


class VideoDetail(VideoListItem):
    source: str
    source_url: str
    embed_url: str
    embed_type: EmbedType
    categories: list[TermRef] = Field(default_factory=list)
    updated_at: datetime


class FetchRunRequest(BaseModel):
    site: Site
    source: str
    pages: int = Field(ge=1, le=100, default=3)


class FetchRunHandle(BaseModel):
    run_id: str
    site: Site
    source: str
    pages: int
    started_at: datetime


class FetchRunSummary(BaseModel):
    id: int
    site: Site
    source: str
    started_at: datetime
    finished_at: Optional[datetime]
    fetched: int
    added: int
    skipped: int
    errors: int


class SettingsPayload(BaseModel):
    """Per-site settings — free-form JSON-able dict."""
    values: dict


class StatsResponse(BaseModel):
    videos_total: dict[str, int] = Field(default_factory=dict)  # site -> count
    videos_per_source: list[dict] = Field(default_factory=list)
    fetch_runs_recent: list[FetchRunSummary] = Field(default_factory=list)

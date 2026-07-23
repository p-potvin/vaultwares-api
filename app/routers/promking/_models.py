"""Pydantic models for the promking router."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Site = Literal["fxv", "pkt", "oneporn", "sexyprn"]
EmbedType = Literal["mp4", "hls"]
TaxonomyKind = Literal["pornstars", "studios", "categories"]
WriteTaxonomyKind = Literal["pornstars", "studios", "categories"]
GenderValue = Literal["male", "female", "unknown"]


class TermRef(BaseModel):
    id: int
    name: str
    slug: str
    image_url: Optional[str] = None
    gender: Optional[str] = None
    disabled: bool = False


class BatchVideoIdsRequest(BaseModel):
    video_ids: list[int] = Field(min_length=1)


class BatchChangeSourceRequest(BatchVideoIdsRequest):
    new_source: str = Field(min_length=1, max_length=80)


class BatchMetadataUpdateRequest(BatchVideoIdsRequest):
    updates: dict[str, object] = Field(min_length=1)


class BatchAddTaxonomyRequest(BatchVideoIdsRequest):
    kind: WriteTaxonomyKind
    term_ids: list[int] = Field(min_length=1)


class BatchRemoveTaxonomyRequest(BatchAddTaxonomyRequest):
    pass


class BatchCountResponse(BaseModel):
    count: int
    skipped: list[int] = Field(default_factory=list)


class BatchError(BaseModel):
    video_id: int
    reason: str


class BatchMetadataResponse(BaseModel):
    count: int
    errors: list[BatchError] = Field(default_factory=list)


class TaxonomyRename(BaseModel):
    term_id: int
    new_name: str = Field(min_length=1, max_length=160)


class BatchTaxonomyRenameRequest(BaseModel):
    renames: list[TaxonomyRename] = Field(min_length=1)


class TaxonomySlugUpdate(BaseModel):
    term_id: int
    new_slug: str = Field(min_length=1, max_length=180)


class BatchTaxonomySlugUpdateRequest(BaseModel):
    updates: list[TaxonomySlugUpdate] = Field(min_length=1)


class TaxonomyConflict(BaseModel):
    term_id: int
    reason: str


class BatchTaxonomyUpdateResponse(BaseModel):
    count: int
    conflicts: list[TaxonomyConflict] = Field(default_factory=list)
    errors: list[TaxonomyConflict] = Field(default_factory=list)


class BatchTaxonomyMergeRequest(BaseModel):
    primary_id: int
    merge_from: list[int] = Field(min_length=1)


class BatchTaxonomyMergeResponse(BaseModel):
    merged_count: int
    video_recount: int


class BatchTaxonomyDeleteRequest(BaseModel):
    term_ids: list[int] = Field(min_length=1)


class BatchTaxonomyDeleteResponse(BaseModel):
    deleted_count: int
    videos_orphaned: int


class BatchTaxonomyDisableRequest(BaseModel):
    term_ids: list[int] = Field(min_length=1)


class BatchTaxonomyDisableResponse(BaseModel):
    count: int


class TaxonomyGenderUpdate(BaseModel):
    pornstar_id: int
    gender: Optional[GenderValue] = None


class BatchTaxonomyGenderUpdateRequest(BaseModel):
    updates: list[TaxonomyGenderUpdate] = Field(min_length=1)


class BatchTaxonomyGenderUpdateResponse(BaseModel):
    count: int
    errors: list[TaxonomyConflict] = Field(default_factory=list)


class VideoListItem(BaseModel):
    id: int
    site: Optional[Site] = None
    source: Optional[str] = None
    title: str
    slug: str
    thumbnail_url: Optional[str] = None
    preview_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    views: int = 0
    created_at: datetime
    disabled_at: Optional[datetime] = None
    pornstars: list[TermRef] = Field(default_factory=list)
    studios: list[TermRef] = Field(default_factory=list)
    qualities: Optional[list[dict]] = None


class VideoDetail(VideoListItem):
    source: str
    source_url: str
    embed_url: str
    embed_type: EmbedType
    description: Optional[str] = None
    categories: list[TermRef] = Field(default_factory=list)
    updated_at: datetime


TermType = Literal["pornstar", "studio", "category"]


class FetchRunRequest(BaseModel):
    site: Site
    source: str
    pages: int = Field(ge=1, le=100, default=3)
    start_page: int = Field(ge=1, default=1)
    # Term-scoped fetch (studio / pornstar / category archive). When term_type
    # is set the run ignores the manual cursor and walks the archive from
    # page 1 sequentially. fetch_all keeps paging until an empty page.
    term_type: Optional[TermType] = None
    term_name: Optional[str] = None
    term_slug: Optional[str] = None
    fetch_all: bool = False


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
    query: Optional[str] = None


class SettingsPayload(BaseModel):
    """Per-site settings — free-form JSON-able dict."""
    values: dict


class TopVideoRef(BaseModel):
    id: int
    slug: str
    title: str
    views: int
    duration_seconds: Optional[int] = None
    thumbnail_url: Optional[str] = None


class TopTermRef(BaseModel):
    id: int
    name: str
    slug: str
    video_count: int
    view_sum: int


class ViewsSummary(BaseModel):
    total: int
    avg_per_video: float
    max_single: int
    videos_with_views: int  # count of videos where views > 0


class CatalogHealth(BaseModel):
    total: int
    disabled: int
    missing_thumbnail: int
    missing_duration: int
    missing_description: int


class FetchActivity(BaseModel):
    """Last-N-day fetcher aggregate. N is 7 by default; the client displays it."""
    window_days: int
    runs: int
    fetched: int
    added: int
    skipped: int
    errors: int


class CatalogGrowth(BaseModel):
    added_24h: int
    added_7d: int
    added_30d: int


class TpdbEnrichment(BaseModel):
    enriched_count: int
    enrichment_pct: float


class DiscoveryHealthStats(BaseModel):
    no_categories: int
    no_pornstars: int
    no_studios: int


class SearchQuerySummary(BaseModel):
    query: str
    n: int


class DeadEndSearchSummary(BaseModel):
    query: str
    n: int


class ConversionSummary(BaseModel):
    total_conversions: int
    total_payout: float


class StatsResponse(BaseModel):
    videos_total: dict[str, int] = Field(default_factory=dict)  # site -> count
    videos_per_source: list[dict] = Field(default_factory=list)
    fetch_runs_recent: list[FetchRunSummary] = Field(default_factory=list)
    # New in v0.2.24 — richer per-site breakdown for the Stats tab.
    views: Optional[ViewsSummary] = None
    catalog_health: Optional[CatalogHealth] = None
    fetch_activity_7d: Optional[FetchActivity] = None
    top_videos: list[TopVideoRef] = Field(default_factory=list)
    top_studios: list[TopTermRef] = Field(default_factory=list)
    top_pornstars: list[TopTermRef] = Field(default_factory=list)
    top_categories: list[TopTermRef] = Field(default_factory=list)
    favourites_total: int = 0
    # Added in v0.3.0
    catalog_growth: Optional[CatalogGrowth] = None
    tpdb_enrichment: Optional[TpdbEnrichment] = None
    discovery_health: Optional[DiscoveryHealthStats] = None
    fetch_error_rate_7d: float = 0.0
    top_searches: list[SearchQuerySummary] = Field(default_factory=list)
    top_dead_end_searches: list[DeadEndSearchSummary] = Field(default_factory=list)
    conversions: Optional[ConversionSummary] = None


class SearchLogRequest(BaseModel):
    site: Site
    query: str
    results_count: int


class AdClickRequest(BaseModel):
    site: Site
    ad_id: str
    placement: Optional[str] = None


class VideoReactionRequest(BaseModel):
    anon_id: Optional[str] = None
    user_id: Optional[int] = None
    reaction_type: str  # 'like' or 'dislike'


class VideoPlayRequest(BaseModel):
    site: Site
    anon_id: Optional[str] = None
    user_id: Optional[int] = None
    duration_watched: Optional[int] = None
    completed: int = 0  # 0 or 1


class PostbackRequest(BaseModel):
    site: Site
    offer_id: Optional[str] = None
    offer_name: Optional[str] = None
    aff_click_id: Optional[str] = None
    transaction_id: Optional[str] = None
    payout: Optional[str] = None
    currency: Optional[str] = None
    source: Optional[str] = None
    ip: Optional[str] = None
    ran: Optional[str] = None
    raw_params: dict


class QueryRequest(BaseModel):
    sql: str



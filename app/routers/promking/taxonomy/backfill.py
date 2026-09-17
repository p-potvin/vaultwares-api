"""High-performance taxonomy backfill engine for Prom-King database."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Dict, List, Optional, Set, Tuple

import asyncpg

from .classifier import TaxonomyClassifier
from .dictionaries import clean_title_for_search, extract_categories_from_title
from ..taxonomies import slugify

logger = logging.getLogger(__name__)


async def get_or_create_category_ids(conn: asyncpg.Connection, category_names: List[str]) -> Dict[str, int]:
    """Ensure categories exist and return a map of {lower_name: id}."""
    if not category_names:
        return {}

    unique_names = list({c.strip() for c in category_names if c.strip()})
    lower_map = {c.lower(): c for c in unique_names}
    keys = list(lower_map.keys())

    existing_rows = await conn.fetch(
        "SELECT id, lower(name) AS l_name FROM categories WHERE lower(name) = ANY($1::text[])",
        keys,
    )
    result = {r["l_name"]: r["id"] for r in existing_rows}
    missing = [lower_map[k] for k in keys if k not in result]

    if missing:
        for name in missing:
            slug = slugify(name)
            # Ensure unique slug
            row = await conn.fetchrow(
                """
                INSERT INTO categories (name, slug)
                VALUES ($1, $2)
                ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                name,
                slug,
            )
            result[name.lower()] = row["id"]

    return result


async def run_stage_1_reclassify_studios(
    conn: asyncpg.Connection,
    dry_run: bool = False,
) -> dict:
    """Stage 1: Reclassify performers erroneously filed as studios.

    Moves links from video_studios to video_pornstars, and soft-deletes empty rogue studios.
    """
    t0 = time.time()
    # Find all studios whose name matches a known pornstar
    overlap_rows = await conn.fetch(
        """
        SELECT s.id AS studio_id, s.name AS studio_name, p.id AS pornstar_id, p.name AS pornstar_name,
               COUNT(vs.video_id) AS video_count
          FROM studios s
          JOIN pornstars p ON lower(p.name) = lower(s.name) AND p.deleted_at IS NULL
          LEFT JOIN video_studios vs ON vs.studio_id = s.id
         WHERE s.deleted_at IS NULL
         GROUP BY s.id, s.name, p.id, p.name
        """
    )

    reclassified_links = 0
    studios_cleaned = 0

    for r in overlap_rows:
        s_id = r["studio_id"]
        p_id = r["pornstar_id"]
        v_count = r["video_count"]
        if v_count > 0:
            if not dry_run:
                # 1. Insert into video_pornstars
                inserted = await conn.execute(
                    """
                    INSERT INTO video_pornstars (video_id, pornstar_id)
                    SELECT video_id, $1 FROM video_studios WHERE studio_id = $2
                    ON CONFLICT DO NOTHING
                    """,
                    p_id,
                    s_id,
                )
                # 2. Delete from video_studios
                await conn.execute("DELETE FROM video_studios WHERE studio_id = $1", s_id)
            reclassified_links += v_count

        if not dry_run:
            # Soft delete the rogue studio record
            await conn.execute("UPDATE studios SET deleted_at = NOW() WHERE id = $1", s_id)
        studios_cleaned += 1

    duration = round(time.time() - t0, 3)
    logger.info(f"Stage 1 complete in {duration}s: {len(overlap_rows)} overlapping studios, {reclassified_links} links moved.")
    return {
        "stage": 1,
        "dry_run": dry_run,
        "overlapping_studios_found": len(overlap_rows),
        "links_reclassified": reclassified_links,
        "studios_cleaned": studios_cleaned,
        "duration_seconds": duration,
    }


async def run_stage_2_title_categories(
    conn: asyncpg.Connection,
    limit: Optional[int] = None,
    batch_size: int = 2000,
    dry_run: bool = False,
) -> dict:
    """Stage 2: 100% Offline title category mining across untagged videos.

    Scans videos with 0 categories, mines categories from the title text,
    and bulk-inserts into video_categories.
    """
    t0 = time.time()
    # Find untagged videos
    query = """
        SELECT v.id, v.title
          FROM videos v
         WHERE v.disabled_at IS NULL
           AND NOT EXISTS (SELECT 1 FROM video_categories vc WHERE vc.video_id = v.id)
         ORDER BY v.id DESC
    """
    if limit:
        query += f" LIMIT {limit}"

    rows = await conn.fetch(query)
    total_videos = len(rows)
    if total_videos == 0:
        return {"stage": 2, "videos_processed": 0, "categories_linked": 0, "duration_seconds": 0}

    # Extract categories for each video
    video_cat_pairs: List[Tuple[int, str]] = []
    all_needed_cats: Set[str] = set()

    for r in rows:
        vid_id = r["id"]
        title = r["title"] or ""
        mined = extract_categories_from_title(title)
        for cat in mined:
            video_cat_pairs.append((vid_id, cat))
            all_needed_cats.add(cat)

    if not video_cat_pairs:
        return {
            "stage": 2,
            "videos_scanned": total_videos,
            "videos_enriched": 0,
            "categories_linked": 0,
            "duration_seconds": round(time.time() - t0, 3),
        }

    # Ensure all categories exist in DB and get their IDs
    cat_id_map = await get_or_create_category_ids(conn, list(all_needed_cats))

    # Prepare arrays for bulk unnest insert
    v_ids: List[int] = []
    c_ids: List[int] = []
    unique_vids: Set[int] = set()

    for vid_id, cat_name in video_cat_pairs:
        cid = cat_id_map.get(cat_name.lower())
        if cid:
            v_ids.append(vid_id)
            c_ids.append(cid)
            unique_vids.add(vid_id)

    total_inserted = 0
    if not dry_run and v_ids:
        # Batch bulk insert
        for i in range(0, len(v_ids), batch_size):
            b_vids = v_ids[i : i + batch_size]
            b_cids = c_ids[i : i + batch_size]
            await conn.execute(
                """
                INSERT INTO video_categories (video_id, category_id)
                SELECT * FROM UNNEST($1::bigint[], $2::int[])
                ON CONFLICT DO NOTHING
                """,
                b_vids,
                b_cids,
            )
            total_inserted += len(b_vids)

    duration = round(time.time() - t0, 3)
    logger.info(f"Stage 2 complete in {duration}s: {len(unique_vids)}/{total_videos} videos enriched with {len(v_ids)} category links.")
    return {
        "stage": 2,
        "dry_run": dry_run,
        "videos_scanned": total_videos,
        "videos_enriched": len(unique_vids),
        "category_links_created": len(v_ids),
        "duration_seconds": duration,
    }


async def run_stage_3_title_entities(
    conn: asyncpg.Connection,
    limit: Optional[int] = None,
    batch_size: int = 2000,
    dry_run: bool = False,
) -> dict:
    """Stage 3: Offline title performer and studio mining.

    Matches known performers and studios (>= 4 chars) against video titles.
    """
    t0 = time.time()
    # Load known performers with names of at least 4 chars (to avoid single-word common noise)
    p_rows = await conn.fetch(
        "SELECT id, name FROM pornstars WHERE length(name) >= 4 AND deleted_at IS NULL AND disabled = false"
    )
    # Compile regex pattern for top 5,000 performers to keep memory & speed optimal
    top_pornstars = sorted(p_rows, key=lambda r: len(r["name"]), reverse=True)[:5000]
    
    # Map lowercase to ID and sort by length descending so longer names match first
    performer_map = {r["name"].lower(): r["id"] for r in top_pornstars}
    names_sorted = sorted(performer_map.keys(), key=len, reverse=True)
    if not names_sorted:
        return {"stage": 3, "videos_scanned": 0, "videos_enriched": 0, "performer_links_created": 0, "duration_seconds": 0}

    pattern = re.compile(r"\b(" + "|".join(re.escape(n) for n in names_sorted) + r")\b", re.IGNORECASE)

    # Query videos with 0 pornstars
    query = """
        SELECT v.id, v.title
          FROM videos v
         WHERE v.disabled_at IS NULL
           AND NOT EXISTS (SELECT 1 FROM video_pornstars vp WHERE vp.video_id = v.id)
         ORDER BY v.id DESC
    """
    if limit:
        query += f" LIMIT {limit}"

    rows = await conn.fetch(query)
    total_videos = len(rows)

    v_ids: List[int] = []
    p_ids: List[int] = []
    enriched_vids: Set[int] = set()

    for r in rows:
        vid_id = r["id"]
        title = r["title"] or ""
        m = pattern.search(title)
        if m:
            matched_name = m.group(1).lower()
            pid = performer_map.get(matched_name)
            if pid:
                v_ids.append(vid_id)
                p_ids.append(pid)
                enriched_vids.add(vid_id)

    if not dry_run and v_ids:
        for i in range(0, len(v_ids), batch_size):
            b_vids = v_ids[i : i + batch_size]
            b_pids = p_ids[i : i + batch_size]
            await conn.execute(
                """
                INSERT INTO video_pornstars (video_id, pornstar_id)
                SELECT * FROM UNNEST($1::bigint[], $2::int[])
                ON CONFLICT DO NOTHING
                """,
                b_vids,
                b_pids,
            )

    duration = round(time.time() - t0, 3)
    logger.info(f"Stage 3 complete in {duration}s: {len(enriched_vids)}/{total_videos} videos enriched with performers.")
    return {
        "stage": 3,
        "dry_run": dry_run,
        "videos_scanned": total_videos,
        "videos_enriched": len(enriched_vids),
        "performer_links_created": len(v_ids),
        "duration_seconds": duration,
    }

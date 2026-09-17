#!/usr/bin/env python3
"""CLI driver for the high-performance taxonomy backfill engine.

Usage:
    python scripts/backfill_taxonomies.py [--stage 1,2,3] [--limit 1000] [--dry-run]
"""
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import asyncpg
from app.routers.promking.taxonomy.backfill import (
    run_stage_1_reclassify_studios,
    run_stage_2_title_categories,
    run_stage_3_title_entities,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("backfill")

DEFAULT_DB_URL = os.environ.get(
    "PROMKING_DB_URL",
    "postgres://postgres:USIpIIfFC-edPvJqp5nxFsLySo8JpDp0@127.0.0.1:5433/promking",
)


async def main():
    parser = argparse.ArgumentParser(description="Prom-King Taxonomy Backfill Engine")
    parser.add_argument("--db-url", default=DEFAULT_DB_URL, help="Postgres connection string")
    parser.add_argument("--stages", default="1,2,3", help="Comma-separated stages to run (e.g. 1,2 or 2)")
    parser.add_argument("--limit", type=int, default=None, help="Max videos to process per stage")
    parser.add_argument("--batch-size", type=int, default=2000, help="Batch insert size")
    parser.add_argument("--dry-run", action="store_true", help="Inspect and count without writing to DB")

    args = parser.parse_args()
    stages = [int(s.strip()) for s in args.stages.split(",") if s.strip()]

    print(f"Connecting to database: {args.db_url.split('@')[-1]}", flush=True)
    conn = await asyncpg.connect(args.db_url)

    try:
        # Pre-flight metrics
        total_vids = await conn.fetchval("SELECT count(*) FROM videos WHERE disabled_at IS NULL")
        vids_with_cats = await conn.fetchval(
            "SELECT count(DISTINCT video_id) FROM video_categories vc JOIN videos v ON v.id = vc.video_id WHERE v.disabled_at IS NULL"
        )
        print(f"Initial State: {total_vids} videos, {vids_with_cats} with categories ({(vids_with_cats/total_vids*100):.1f}%)", flush=True)

        if 1 in stages:
            print("=== Running Stage 1: Reclassify Performers wrongly filed as Studios ===", flush=True)
            res1 = await run_stage_1_reclassify_studios(conn, dry_run=args.dry_run)
            print(f"Stage 1 Result: {res1}", flush=True)

        if 2 in stages:
            print("=== Running Stage 2: 100% Offline Title Category Mining ===", flush=True)
            res2 = await run_stage_2_title_categories(
                conn, limit=args.limit, batch_size=args.batch_size, dry_run=args.dry_run
            )
            print(f"Stage 2 Result: {res2}", flush=True)

        if 3 in stages:
            print("=== Running Stage 3: Title Performer & Studio Mining ===", flush=True)
            res3 = await run_stage_3_title_entities(
                conn, limit=args.limit, batch_size=args.batch_size, dry_run=args.dry_run
            )
            print(f"Stage 3 Result: {res3}", flush=True)

        # Post-flight metrics
        if not args.dry_run:
            new_vids_with_cats = await conn.fetchval(
                "SELECT count(DISTINCT video_id) FROM video_categories vc JOIN videos v ON v.id = vc.video_id WHERE v.disabled_at IS NULL"
            )
            gained = new_vids_with_cats - vids_with_cats
            print(
                f"Final State: {new_vids_with_cats}/{total_vids} videos with categories ({(new_vids_with_cats/total_vids*100):.1f}%, +{gained} newly categorized!)",
                flush=True
            )
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

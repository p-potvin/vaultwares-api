"""
Deduplicate videos with hex hash suffixes (e.g. `some-slug-a1b2c3`) in the Prom-King database.

For videos with a hash suffix:
1. If a primary clean video exists with the base slug:
   - Merges favourites, video_plays, video_reactions, video_sites, short_links, tpdb_scenes.
   - Cleans up child taxonomy relations.
   - Deletes the duplicate video row.
2. If NO primary video exists with the base slug:
   - Renames the slug to the clean base slug so the video is preserved without a hash.

Usage:
  python scripts/dedupe_videos.py            # Dry-run (prints plan without modifying DB)
  python scripts/dedupe_videos.py --execute  # Applies the changes in transactions
"""
import argparse
import asyncio
import logging
import re
import sys
from pathlib import Path

# Add the parent directory and cwd to sys.path so we can import app modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path.cwd()))
sys.path.insert(0, "/opt/vaultwares-api")

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
load_dotenv("/opt/vaultwares-api/.env")
load_dotenv()

from app.routers.promking.db import get_pool

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("dedupe_videos")

HASH_SLUG_RE = re.compile(r"-[a-f0-9]{6}$")


async def run_deduplication(execute: bool = False):
    pool = await get_pool()
    async with pool.acquire() as conn:
        print("Scanning for hashed duplicate videos in `videos`...", flush=True)
        rows = await conn.fetch(
            """
            SELECT dup.id AS dup_id, dup.slug AS dup_slug, dup.title AS dup_title,
                   base.id AS base_id, base.slug AS base_slug,
                   regexp_replace(dup.slug, '-[a-f0-9]{6}$', '') AS clean_slug
            FROM videos dup
            LEFT JOIN videos base
              ON base.slug = regexp_replace(dup.slug, '-[a-f0-9]{6}$', '')
             AND base.id != dup.id
            WHERE dup.slug ~ '-[a-f0-9]{6}$'
            ORDER BY dup.id ASC
            """
        )

        total_hashed = len(rows)
        print(f"Found {total_hashed} videos with hash suffixes.", flush=True)
        if total_hashed == 0:
            print("No hashed duplicate videos found. Database is clean!", flush=True)
            return

        to_merge: list[tuple[dict, dict]] = []
        to_rename: list[tuple[dict, str]] = []

        for r in rows:
            dup = {"id": r["dup_id"], "slug": r["dup_slug"], "title": r["dup_title"]}
            if r["base_id"] is not None:
                base = {"id": r["base_id"], "slug": r["base_slug"]}
                to_merge.append((dup, base))
            else:
                to_rename.append((dup, r["clean_slug"]))

        print(
            f"Plan: {len(to_merge)} videos to merge into existing primary videos, {len(to_rename)} videos to rename to clean slug.",
            flush=True,
        )

        if not execute:
            print("Dry-run complete. Run with --execute to apply changes.", flush=True)
            return

        # Execute merges in batches
        merged_count = 0
        renamed_count = 0

        print(f"Starting merge operations for {len(to_merge)} duplicates...", flush=True)
        for dup, base in to_merge:
            dup_id = dup["id"]
            base_id = base["id"]

            async with conn.transaction():
                # 0. Preserve preview_url (especially with sound), thumbnail, views, duration, qualities
                dup_v = await conn.fetchrow(
                    "SELECT preview_url, thumbnail_url, duration_seconds, views, qualities, description FROM videos WHERE id = $1",
                    dup_id,
                )
                base_v = await conn.fetchrow(
                    "SELECT preview_url, thumbnail_url, duration_seconds, views, qualities, description FROM videos WHERE id = $1",
                    base_id,
                )
                if dup_v and base_v:
                    updates = []
                    params = [base_id]
                    dup_prev = dup_v["preview_url"]
                    base_prev = base_v["preview_url"]
                    if dup_prev and (not base_prev or "promking" in dup_prev or "internal" in dup_prev):
                        params.append(dup_prev)
                        updates.append(f"preview_url = ${len(params)}")

                    dup_thumb = dup_v["thumbnail_url"]
                    base_thumb = base_v["thumbnail_url"]
                    if dup_thumb and (not base_thumb or (not base_thumb.startswith("http") and dup_thumb.startswith("http"))):
                        params.append(dup_thumb)
                        updates.append(f"thumbnail_url = ${len(params)}")

                    dup_views = dup_v["views"] or 0
                    base_views = base_v["views"] or 0
                    if dup_views > 0:
                        params.append(max(base_views, dup_views))
                        updates.append(f"views = ${len(params)}")

                    if not base_v["duration_seconds"] and dup_v["duration_seconds"]:
                        params.append(dup_v["duration_seconds"])
                        updates.append(f"duration_seconds = ${len(params)}")

                    if not base_v["qualities"] and dup_v["qualities"]:
                        params.append(dup_v["qualities"])
                        updates.append(f"qualities = ${len(params)}")

                    if updates:
                        await conn.execute(
                            f"UPDATE videos SET {', '.join(updates)} WHERE id = $1",
                            *params,
                        )

                # 1. Merge video_sites
                await conn.execute(
                    """
                    INSERT INTO video_sites (video_id, site)
                    SELECT $1, site FROM video_sites WHERE video_id = $2
                    ON CONFLICT (video_id, site) DO NOTHING
                    """,
                    base_id,
                    dup_id,
                )

                # 2. Merge favourites (re-point non-colliding, delete colliding)
                await conn.execute(
                    """
                    UPDATE favourites
                       SET video_id = $1
                     WHERE video_id = $2
                       AND NOT EXISTS (
                           SELECT 1 FROM favourites f2 WHERE f2.video_id = $1 AND f2.user_id = favourites.user_id
                       )
                    """,
                    base_id,
                    dup_id,
                )
                await conn.execute("DELETE FROM favourites WHERE video_id = $1", dup_id)

                # 3. Merge video_plays
                await conn.execute(
                    "UPDATE video_plays SET video_id = $1 WHERE video_id = $2",
                    base_id,
                    dup_id,
                )

                # 4. Merge video_reactions
                await conn.execute(
                    """
                    UPDATE video_reactions
                       SET video_id = $1
                     WHERE video_id = $2
                       AND NOT EXISTS (
                           SELECT 1 FROM video_reactions r2 WHERE r2.video_id = $1 AND r2.user_id = video_reactions.user_id
                       )
                    """,
                    base_id,
                    dup_id,
                )
                await conn.execute("DELETE FROM video_reactions WHERE video_id = $1", dup_id)

                # 5. Merge short_links
                await conn.execute(
                    "UPDATE short_links SET video_id = $1 WHERE video_id = $2",
                    base_id,
                    dup_id,
                )

                # 6. Merge tpdb_scenes
                await conn.execute(
                    "UPDATE tpdb_scenes SET video_id = $1 WHERE video_id = $2",
                    base_id,
                    dup_id,
                )

                # 7. Delete child taxonomy relations
                await conn.execute("DELETE FROM video_pornstars WHERE video_id = $1", dup_id)
                await conn.execute("DELETE FROM video_studios WHERE video_id = $1", dup_id)
                await conn.execute("DELETE FROM video_categories WHERE video_id = $1", dup_id)
                await conn.execute("DELETE FROM video_sites WHERE video_id = $1", dup_id)
                await conn.execute("DELETE FROM onlyfans_media WHERE video_id = $1", dup_id)

                # 8. Delete the duplicate video row
                await conn.execute("DELETE FROM videos WHERE id = $1", dup_id)

            merged_count += 1
            if merged_count % 100 == 0 or merged_count == len(to_merge):
                print(f"Merged {merged_count} / {len(to_merge)} duplicate videos.", flush=True)

        print(f"Starting slug rename operations for {len(to_rename)} singletons...", flush=True)
        for dup, clean_slug in to_rename:
            dup_id = dup["id"]
            try:
                async with conn.transaction():
                    await conn.execute(
                        "UPDATE videos SET slug = $1 WHERE id = $2",
                        clean_slug,
                        dup_id,
                    )
                renamed_count += 1
            except Exception as e:
                print(f"Could not rename video {dup_id} to {clean_slug}: {e}", flush=True)

        print(
            f"Deduplication finished successfully! Merged {merged_count} duplicates, renamed {renamed_count} singletons.",
            flush=True,
        )


def main():
    parser = argparse.ArgumentParser(description="Prom-King duplicate video cleanup")
    parser.add_argument("--execute", action="store_true", help="Apply changes to the database")
    args = parser.parse_args()

    asyncio.run(run_deduplication(execute=args.execute))


if __name__ == "__main__":
    main()

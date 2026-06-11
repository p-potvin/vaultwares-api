import os
import re
import base64
import secrets
import string
import logging
import asyncio
from app.services.zipper.fileboom import FileboomClient
from app.routers.promking.db import get_pool

logger = logging.getLogger(__name__)

def generate_id(length=24):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def generate_slug(filename: str) -> str:
    # Remove extension
    base_name, _ = os.path.splitext(filename)
    # Lowercase
    slug = base_name.lower()
    # Replace spaces, underscores, and special characters with hyphens
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    # Strip leading/trailing hyphens
    slug = slug.strip('-')
    # If slug is empty, use a fallback random name
    if not slug:
        slug = f"download-{generate_id(6).lower()}"
    return slug

def make_linkvertise_url(target_url: str) -> str:
    user_id = os.environ.get("LINKVERTISE_USER_ID", "331075")
    random_id = os.environ.get("LINKVERTISE_RANDOM_ID", "dynamic")
    target_b64 = base64.b64encode(target_url.encode('utf-8')).decode('utf-8')
    return f"https://link-to.net/{user_id}/{random_id}/dynamic?r={target_b64}"

async def get_unique_slug(conn, base_slug: str) -> str:
    slug = base_slug
    attempts = 0
    while attempts < 100:
        row = await conn.fetchrow("SELECT 1 FROM link_sharing WHERE slug = $1", slug)
        if not row:
            return slug
        # Append random 4-character hex string if collision occurs
        slug = f"{base_slug}-{secrets.token_hex(2)}"
        attempts += 1
    return f"{base_slug}-{secrets.token_hex(4)}"

async def save_to_database(record: dict):
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Check collision and get unique slug
        unique_slug = await get_unique_slug(conn, record["slug"])
        record["slug"] = unique_slug
        
        await conn.execute("""
            INSERT INTO link_sharing (id, title, slug, file_path, fileboom_url, linkvertise_url_fxv, linkvertise_url_pkt)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """, record["id"], record["title"], record["slug"], record["file_path"], record["fileboom_url"], record["linkvertise_url_fxv"], record["linkvertise_url_pkt"])
        logger.info(f"Database: Saved link_sharing record {record['id']} for {record['slug']}")

def trigger_post_download_pipeline(file_path: str, page_url: str):
    """
    Executes the FileBoom upload, linkvertise generation, and database logging.
    Runs asynchronously/background-safe.
    """
    try:
        if not os.path.exists(file_path):
            logger.error(f"[Post-Download] File not found at path: {file_path}")
            return

        filename = os.path.basename(file_path)
        logger.info(f"[Post-Download] Starting pipeline for file: {filename}")

        # 1. Upload to FileBoom
        try:
            client = FileboomClient()
            fileboom_url = client.upload_file(file_path)
        except Exception as e:
            logger.error(f"[Post-Download] FileBoom upload failed: {e}")
            # We still proceed with DB logging so the user knows upload failed (url is None)
            fileboom_url = None

        # 2. SEO Slug Generation
        base_slug = generate_slug(filename)
        
        # 3. Determine File Type path mapping
        ext = os.path.splitext(filename)[1].lower().strip(".")
        if ext == "zip":
            file_type = "zip"
        elif ext in ["mp4", "mkv", "avi", "mov"]:
            file_type = "video"
        else:
            file_type = "file"

        # 4. Generate Target redirection pages
        # Format: https://links.fullxxx.video/{file_type}/{slug}
        # and     https://links.prom-king.xyz/{file_type}/{slug}
        fxv_target = f"https://links.fullxxx.video/{file_type}/{base_slug}"
        pkt_target = f"https://links.prom-king.xyz/{file_type}/{base_slug}"

        # 5. Generate Linkvertise monetized URLs
        linkvertise_url_fxv = make_linkvertise_url(fxv_target)
        linkvertise_url_pkt = make_linkvertise_url(pkt_target)

        # 6. Database persistence
        record_id = generate_id(24)
        title = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ")
        record = {
            "id": record_id,
            "title": title,
            "slug": base_slug,
            "file_path": file_path,
            "fileboom_url": fileboom_url,
            "linkvertise_url_fxv": linkvertise_url_fxv,
            "linkvertise_url_pkt": linkvertise_url_pkt
        }

        # Use asyncio run_coroutine_threadsafe or create new event loop if necessary
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            asyncio.run_coroutine_threadsafe(save_to_database(record), loop)
        else:
            loop.run_until_complete(save_to_database(record))

        logger.info(f"[Post-Download] Complete for {filename}!")
        logger.info(f" -> FileBoom: {fileboom_url}")
        logger.info(f" -> Linkvertise FXV: {linkvertise_url_fxv}")
        logger.info(f" -> Linkvertise PKT: {linkvertise_url_pkt}")

    except Exception as e:
        logger.exception(f"[Post-Download] Error processing pipeline for {file_path}: {e}")

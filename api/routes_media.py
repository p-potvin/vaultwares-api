import os
import time
import socket
import logging
import asyncio
import httpx
import requests
import threading
import zipfile
import random
import re
import hashlib
import subprocess
from urllib.parse import urlparse, urljoin
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from api.models import ScrapePayload, DownloadPayload, OpenPayload
from api.auth import require_auth, _get_client_ip, _is_trusted_client_ip, _effective_scheme
from api.database import db_available, Tortoise
from tortoise import connections

router = APIRouter()
logger = logging.getLogger("vaultwares.api")

ZIPPER_DEST_DIR = "C:/Users/Administrator/Desktop/Github Repos/python-zipper/.downloaded"
RD_TOKEN_PATH = "C:/Users/Administrator/Desktop/Github Repos/.access/realdebrid_api.txt"

try:
    from app.services.zipper import scraper
except ImportError:
    scraper = None
    logger.warning("Media Pipeline: Failed to import scraper module from app.services.zipper.")

zipper_cancel_event = threading.Event()
THROTTLE_SPEED_BPS = 5 * 1024 * 1024
DEFAULT_RCLONE_REMOTES = "gdrive:python-zipper,proton_pc:python-zipper,proton:python-zipper"
active_zipper_jobs = {}
zipper_jobs_lock = threading.Lock()
active_download_jobs = 0
download_task_lock = threading.Lock()

def update_job_progress(corr_id: str, status=None, increment_processed=False, increment_images=False, increment_other=False, total_links=None):
    parent_id = corr_id.split("-")[0] if "-" in corr_id else corr_id
    with zipper_jobs_lock:
        if parent_id not in active_zipper_jobs: return
        job = active_zipper_jobs[parent_id]
        if status: job["status"] = status
        if increment_processed: job["processed_links"] += 1
        if increment_images: job["images_count"] += 1
        if increment_other: job["other_files_count"] += 1
        if total_links is not None: job["total_links"] = total_links
        job["updated_at"] = time.time()
        
        if job["processed_links"] >= job["total_links"] and job["status"] == "running":
            job["status"] = "completed"
        if len(active_zipper_jobs) > 50:
            sorted_jobs = sorted(active_zipper_jobs.items(), key=lambda x: x[1]["created_at"])
            for old_id, _ in sorted_jobs[:len(active_zipper_jobs) - 50]:
                active_zipper_jobs.pop(old_id, None)

def throttle_chunk(chunk_size, start_time):
    if THROTTLE_SPEED_BPS:
        min_time = chunk_size / THROTTLE_SPEED_BPS
        elapsed = time.time() - start_time
        if elapsed < min_time: time.sleep(min_time - elapsed)

def _configured_rclone_remotes():
    raw = os.environ.get("VAULTWARES_RCLONE_REMOTES") or os.environ.get("PYTHON_ZIPPER_RCLONE_REMOTES") or DEFAULT_RCLONE_REMOTES
    return [remote.strip().rstrip("/") for remote in raw.split(",") if remote.strip()]

def handoff_to_rclone(file_path):
    if not file_path or not os.path.exists(file_path):
        return {"status": "missing", "path": file_path}
    for remote in _configured_rclone_remotes():
        target = f"{remote}/"
        try:
            logger.info("[Media Pipeline] Moving completed download to rclone remote: %s", remote)
            subprocess.run(
                ["rclone", "move", file_path, target, "--create-empty-src-dirs"],
                check=True,
                capture_output=True,
                text=True,
                timeout=3600,
            )
            return {"status": "moved", "remote": remote}
        except Exception as exc:
            logger.error("[Media Pipeline] rclone handoff failed for %s: %s", remote, exc)
    return {"status": "local", "path": file_path}

def get_rd_token():
    try:
        if os.path.exists(RD_TOKEN_PATH):
            with open(RD_TOKEN_PATH, 'r') as f: return f.read().strip()
    except Exception as e:
        logger.error(f"[Media Pipeline] Failed to read Real-Debrid token: {e}")
    return None

def unrestrict_link_rd(url, rd_token, corr_id):
    if not rd_token: return url
    try:
        headers = {'Authorization': f'Bearer {rd_token}', 'User-Agent': 'Mozilla/5.0'}
        resp = requests.post("https://api.real-debrid.com/rest/1.0/unrestrict/link", headers=headers, data={'link': url}, timeout=12)
        if resp.status_code == 200:
            dl_url = resp.json().get('download')
            if dl_url: return dl_url
    except Exception as e:
        logger.error(f"[correlationId: {corr_id}] Real-Debrid error: {e}")
    return url

def bypass_linkvertise(url, corr_id):
    for service in ["https://trw.lat/api/bypass", "https://api.bypass.vip/bypass", "https://free.bypass-api.com/bypass"]:
        try:
            resp = requests.get(service, params={'url': url}, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                res = data.get('result') or data.get('destination')
                if res and res.lower().startswith("http"): return res
        except: pass
    return url

def download_image_throttled(url, headers, corr_id):
    try:
        resp = requests.get(url, headers=headers, stream=True, timeout=10)
        if resp.status_code != 200: return None
        content = bytearray()
        for chunk in resp.iter_content(chunk_size=8192):
            if zipper_cancel_event.is_set(): return None
            if chunk:
                start = time.time()
                content.extend(chunk)
                throttle_chunk(len(chunk), start)
        return bytes(content)
    except Exception as e:
        logger.error(f"[correlationId: {corr_id}] Failed to download: {e}")
        return None

def _run_scraper_thread(url, selector, playwright, batch_size, corr_id):
    if not scraper:
        update_job_progress(corr_id, status="failed")
        return
    try:
        urls = scraper.scrape_with_playwright(url, selector) if playwright else scraper.scrape_with_requests(url, selector)
    except Exception as e:
        logger.error(f"[correlationId: {corr_id}] Scraper error: {e}")
        update_job_progress(corr_id, status="failed")
        return
    if not urls:
        update_job_progress(corr_id, status="completed")
        return
    update_job_progress(corr_id, total_links=len(urls))
    _download_and_process_links(url, urls, batch_size, corr_id)

def _run_downloader_thread(url, links, batch_size, corr_id, upscale_enabled=False, upscale_model='4xNomos8k_atd'):
    _download_and_process_links(url, links, batch_size, corr_id, upscale_enabled, upscale_model)

def _download_and_process_links(page_url, raw_links, batch_size, corr_id, upscale_enabled=False, upscale_model='4xNomos8k_atd'):
    global active_download_jobs
    if not scraper:
        update_job_progress(corr_id, status="failed")
        return
    headers = {"User-Agent": "Mozilla/5.0"}
    url_slug = scraper.get_url_slug(page_url)
    rd_token = get_rd_token()
    unique_urls = []
    seen = set()
    for u in raw_links:
        full_url = urljoin(page_url, u)
        if full_url.startswith("http") and full_url not in seen:
            seen.add(full_url)
            unique_urls.append(full_url)

    update_job_progress(corr_id, total_links=len(unique_urls))
    image_urls = []
    for idx, url in enumerate(unique_urls):
        if zipper_cancel_event.is_set():
            update_job_progress(corr_id, status="aborted")
            return
        file_corr = f"{corr_id}-{idx:03d}"
        resolved = url
        if any(d in url.lower() for d in ["linkvertise.com", "direct-link.net", "link-center.net"]):
            resolved = bypass_linkvertise(url, file_corr)
        final = resolved
        is_premium = any(d in resolved.lower() for d in ["mega.nz", "keep2share.cc", "rapidgator.net", "katfile.com", "pixeldrain.com"])
        if is_premium:
            final = unrestrict_link_rd(resolved, rd_token, file_corr)
        ext = os.path.splitext(urlparse(final).path)[1].lower().strip(".")
        if ext in ["jpg", "jpeg", "png", "gif", "webp"]:
            image_urls.append((final, file_corr))
        else:
            threading.Thread(target=_download_direct_file_worker, args=(final, headers, file_corr), daemon=True).start()
    if image_urls:
        _download_and_zip_images_worker(url_slug, page_url, image_urls, batch_size, headers, corr_id, upscale_enabled, upscale_model)

def _download_direct_file_worker(url, headers, file_corr_id):
    try:
        resp = requests.get(url, headers=headers, stream=True, timeout=120)
        if resp.status_code != 200:
            update_job_progress(file_corr_id, increment_processed=True)
            return
        content_disp = resp.headers.get('content-disposition', '')
        filename = ""
        if 'filename=' in content_disp: filename = content_disp.split('filename=')[1].strip('"\'')
        if not filename: filename = os.path.basename(urlparse(url).path)
        if not filename: filename = f"download_{hashlib.md5(url.encode()).hexdigest()[:8]}.bin"
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        file_path = os.path.join(ZIPPER_DEST_DIR, filename)
        with open(file_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if zipper_cancel_event.is_set():
                    f.close()
                    try: os.remove(file_path)
                    except: pass
                    update_job_progress(file_corr_id, status="aborted", increment_processed=True)
                    return
                if chunk:
                    start = time.time()
                    f.write(chunk)
                    throttle_chunk(len(chunk), start)
        parent_id = file_corr_id.split("-")[0]
        handoff_result = handoff_to_rclone(file_path)
        with zipper_jobs_lock:
            if parent_id in active_zipper_jobs:
                active_zipper_jobs[parent_id].setdefault("archives", []).append(filename)
                active_zipper_jobs[parent_id]["rclone"] = handoff_result
        update_job_progress(file_corr_id, increment_processed=True, increment_other=True)
    except Exception as e:
        logger.error(f"Download error: {e}")
        update_job_progress(file_corr_id, increment_processed=True)

def _download_and_zip_images_worker(url_slug, page_url, img_info_list, batch_size, headers, corr_id, upscale_enabled=False, upscale_model='4xNomos8k_atd'):
    zip_writer = None
    zip_path = None
    count = 0
    upscaler = None
    if upscale_enabled:
        try:
            from app.services.upscaler import get_upscaler
            upscaler = get_upscaler()
            if not upscaler.is_available(): upscale_enabled = False
        except: upscale_enabled = False

    for img_url, file_corr in img_info_list:
        if zipper_cancel_event.is_set():
            if zip_writer: zip_writer.close()
            update_job_progress(corr_id, status="aborted")
            return
        ext = os.path.splitext(urlparse(img_url).path)[1].lower().strip(".") or "jpg"
        content = download_image_throttled(img_url, headers, file_corr)
        if not content or len(content) < 40 * 1024:
            update_job_progress(file_corr, increment_processed=True)
            continue

        if not zip_writer:
            zip_filename = f"{url_slug}_{random.randint(0, 9000)}.zip"
            zip_path = os.path.join(ZIPPER_DEST_DIR, zip_filename)
            zip_writer = zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED)
            with zipper_jobs_lock:
                if corr_id in active_zipper_jobs:
                    active_zipper_jobs[corr_id].setdefault("archives", []).append(zip_filename)

        write_content = content
        out_ext = ext
        if upscale_enabled and upscaler and ext in ['jpg', 'jpeg', 'png', 'webp']:
            try:
                write_content = upscaler.upscale_image(content, model_name=upscale_model)
                out_ext = 'png'
            except: pass

        filename_in_zip = f"{url_slug}_{str(count + 1).zfill(3)}.{out_ext}"
        try:
            zip_writer.writestr(filename_in_zip, write_content)
            count += 1
            update_job_progress(file_corr, increment_processed=True, increment_images=True)
        except:
            update_job_progress(file_corr, increment_processed=True)

        if count > 0 and count % batch_size == 0:
            zip_writer.close()
            handoff_result = handoff_to_rclone(zip_path)
            with zipper_jobs_lock:
                if corr_id in active_zipper_jobs:
                    active_zipper_jobs[corr_id]["rclone"] = handoff_result
            zip_writer = None
            count = 0

    if zip_writer:
        zip_writer.close()
        handoff_result = handoff_to_rclone(zip_path)
        with zipper_jobs_lock:
            if corr_id in active_zipper_jobs:
                active_zipper_jobs[corr_id]["rclone"] = handoff_result

@router.get("/health")
def api_health():
    return {"status": "online"}

@router.get("/healthz")
async def api_healthz():
    if not db_available():
        return JSONResponse(status_code=503, content={"status": "degraded", "db": "uninitialized"})
    try:
        conn = connections.get("default")
        await asyncio.wait_for(conn.execute_query("SELECT 1"), timeout=2.0)
    except Exception as exc:
        return JSONResponse(status_code=503, content={"status": "degraded", "db": "error", "error": str(exc)[:200]})
    return {"status": "ok", "db": "up"}

@router.get("/api/jobs")
def api_get_jobs():
    with zipper_jobs_lock: return {"jobs": active_zipper_jobs, "source": "vaultwares-api"}

@router.get("/api/upscaler/status")
def api_upscaler_status():
    try:
        from app.services.upscaler import get_upscaler
        upscaler = get_upscaler()
        return {"available": upscaler.is_available(), "device": upscaler.device, "models": upscaler.get_available_models(), "stats": upscaler.get_stats()}
    except Exception as e:
        return {"available": False, "error": str(e)}

@router.post("/api/open-downloaded")
def api_open_downloaded(payload: OpenPayload):
    try:
        import subprocess
        target_dir = os.path.normpath(ZIPPER_DEST_DIR)
        os.makedirs(target_dir, exist_ok=True)
        
        target_file = payload.path or payload.filename
        if payload.folder or not target_file:
            subprocess.Popen(f'explorer.exe "{target_dir}"', shell=True)
            return {"status": "success", "message": "Opened downloaded folder"}
            
        file_path = os.path.normpath(target_file if os.path.isabs(target_file) else os.path.join(target_dir, target_file))
        if os.path.exists(file_path):
            subprocess.Popen(f'explorer.exe /select,"{file_path}"', shell=True)
            return {"status": "success", "message": f"Opened file {os.path.basename(file_path)}"}
            
        subprocess.Popen(f'explorer.exe "{target_dir}"', shell=True)
        return {"status": "success", "message": "Target file not found; opened downloaded folder"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/scrape")
def api_scrape(payload: ScrapePayload, request: Request):
    corr_id = request.state.correlation_id
    with zipper_jobs_lock:
        active_zipper_jobs[corr_id] = {"status": "running", "url": payload.url, "total_links": 0, "processed_links": 0, "images_count": 0, "other_files_count": 0, "created_at": time.time(), "updated_at": time.time()}
    zipper_cancel_event.clear()
    threading.Thread(target=_run_scraper_thread, args=(payload.url, payload.selector, payload.playwright, payload.batch_size, corr_id), daemon=True).start()
    return {"status": "Scraping task started", "correlationId": corr_id}

@router.post("/download")
def api_download(payload: DownloadPayload, request: Request):
    corr_id = request.state.correlation_id
    with zipper_jobs_lock:
        active_zipper_jobs[corr_id] = {"status": "running", "url": payload.url, "total_links": len(payload.links), "processed_links": 0, "images_count": 0, "other_files_count": 0, "created_at": time.time(), "updated_at": time.time()}
    zipper_cancel_event.clear()
    threading.Thread(target=_run_downloader_thread, args=(payload.url, payload.links, payload.batch_size, corr_id, payload.upscale_enabled, payload.upscale_model), daemon=True).start()
    return {"status": "Download task started", "count": len(payload.links), "correlationId": corr_id}

@router.post("/abort")
@router.post("/api/abort")
def api_abort():
    zipper_cancel_event.set()
    with zipper_jobs_lock:
        for job in active_zipper_jobs.values():
            if job["status"] == "running":
                job["status"] = "aborted"
                job["updated_at"] = time.time()
    return {"status": "Aborted"}

#!/usr/bin/env python
"""Apply all patches to api_server.py for upscaling support"""

import re

file_path = 'C:\\Users\\Administrator\\Desktop\\Github Repos\\vaultwares-api\\api_server.py'

with open(file_path, 'r') as f:
    content = f.read()

print("Original file loaded...")

# Patch 1: Update DownloadPayload model
print("Applying Patch 1: DownloadPayload model...")
old = """class DownloadPayload(BaseModel):
    url: str
    links: List[str]
    batch_size: Optional[int] = 100"""
new = """class DownloadPayload(BaseModel):
    url: str
    links: List[str]
    batch_size: Optional[int] = 5
    upscale_enabled: Optional[bool] = False
    upscale_model: Optional[str] = "4xNomos8k_atd""""
if old in content:
    content = content.replace(old, new)
    print("  ✓ DownloadPayload model updated")
else:
    print("  ✗ DownloadPayload model pattern not found")

# Patch 2: Add rate limiting globals and metrics function
print("Applying Patch 2: Rate limiting globals...")
old2 = """active_zipper_jobs = {}
zipper_jobs_lock = threading.Lock()

def update_job_progress"""
new2 = """active_zipper_jobs = {}
zipper_jobs_lock = threading.Lock()

# Rate limiting for download jobs - only 1 concurrent job at a time
download_task_lock = threading.Lock()
active_download_jobs = 0
MAX_CONCURRENT_DOWNLOAD_JOBS = 1

# Upscale metrics log
UPSCALE_METRICS_LOG = os.path.join(BASE_DIR, "data", "upscale_metrics.log")

def log_upscale_metrics(job_id: str, model: str, image_count: int, success_count: int, 
                        fail_count: int, total_time: float, avg_time_per_image: float):
    \"\"\"Log upscaling metrics for analysis\"\"\"
    metrics_entry = {
        "timestamp": time.time(),
        "job_id": job_id,
        "model": model,
        "image_count": image_count,
        "success_count": success_count,
        "fail_count": fail_count,
        "total_time_seconds": total_time,
        "avg_time_per_image_seconds": avg_time_per_image
    }
    try:
        with open(UPSCALE_METRICS_LOG, 'a') as f:
            f.write(json.dumps(metrics_entry) + '\\n')
    except Exception as e:
        logger.error(f"Failed to write upscale metrics: {e}")

def update_job_progress"""
if old2 in content:
    content = content.replace(old2, new2)
    print("  ✓ Rate limiting globals added")
else:
    print("  ✗ Rate limiting globals pattern not found")

# Patch 3: Update api_download endpoint
print("Applying Patch 3: api_download endpoint...")
old3 = """@app.post("/download")
def api_download(payload: DownloadPayload, request: Request):
    corr_id = request.state.correlation_id
    with zipper_jobs_lock:
        active_zipper_jobs[corr_id] = {
            "status": "running",
            "url": payload.url,
            "total_links": len(payload.links),
            "processed_links": 0,
            "images_count": 0,
            "other_files_count": 0,
            "created_at": time.time(),
            "updated_at": time.time()
        }
    zipper_cancel_event.clear()
    threading.Thread(
        target=_run_downloader_thread,
        args=(payload.url, payload.links, payload.batch_size, corr_id),
        daemon=True
    ).start()
    return {"status": "Download task started", "count": len(payload.links), "correlationId": corr_id}"""

new3 = """@app.post("/download")
def api_download(payload: DownloadPayload, request: Request):
    global active_download_jobs
    
    # Validate batch_size
    if payload.batch_size < 1 or payload.batch_size > 100:
        return {"status": "error", "message": "batch_size must be between 1 and 100"}
    
    # Validate upscale_model if upscaling is enabled
    if payload.upscale_enabled:
        allowed_models = ["4xNomos8k_atd"]
        if payload.upscale_model not in allowed_models:
            return {"status": "error", "message": f"upscale_model must be one of {allowed_models}"}
    
    # Rate limiting - only one job at a time
    with download_task_lock:
        if active_download_jobs >= MAX_CONCURRENT_DOWNLOAD_JOBS:
            return {"status": "error", "message": "Another download job is already running. Please wait."}
        active_download_jobs += 1
    
    corr_id = request.state.correlation_id
    with zipper_jobs_lock:
        active_zipper_jobs[corr_id] = {
            "status": "running",
            "url": payload.url,
            "total_links": len(payload.links),
            "processed_links": 0,
            "images_count": 0,
            "other_files_count": 0,
            "upscale_enabled": payload.upscale_enabled,
            "upscale_model": payload.upscale_model,
            "created_at": time.time(),
            "updated_at": time.time()
        }
    zipper_cancel_event.clear()
    threading.Thread(
        target=_run_downloader_thread,
        args=(payload.url, payload.links, payload.batch_size, corr_id,
              payload.upscale_enabled, payload.upscale_model),
        daemon=True
    ).start()
    return {"status": "Download task started", "count": len(payload.links), "correlationId": corr_id}"""
if old3 in content:
    content = content.replace(old3, new3)
    print("  ✓ api_download endpoint updated")
else:
    print("  ✗ api_download endpoint pattern not found")

# Patch 4: Update _run_downloader_thread
print("Applying Patch 4: _run_downloader_thread...")
old4 = """def _run_downloader_thread(url, links, batch_size, corr_id):
    logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Background downloader task started for URL: {url} ({len(links)} links)")
    os.makedirs(ZIPPER_DEST_DIR, exist_ok=True)
    _download_and_process_links(url, links, batch_size, corr_id)"""
new4 = """def _run_downloader_thread(url, links, batch_size, corr_id, upscale_enabled=False, upscale_model='4xNomos8k_atd'):
    logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Background downloader task started for URL: {url} ({len(links)} links)")
    os.makedirs(ZIPPER_DEST_DIR, exist_ok=True)
    _download_and_process_links(url, links, batch_size, corr_id, upscale_enabled, upscale_model)"""
if old4 in content:
    content = content.replace(old4, new4)
    print("  ✓ _run_downloader_thread updated")
else:
    print("  ✗ _run_downloader_thread pattern not found")

# Patch 5: Update _download_and_process_links signature and body
print("Applying Patch 5: _download_and_process_links...")

# First, update the function signature
old5a = "def _download_and_process_links(page_url, raw_links, batch_size, corr_id):"
new5a = "def _download_and_process_links(page_url, raw_links, batch_size, corr_id, upscale_enabled=False, upscale_model='4xNomos8k_atd'):"
if old5a in content:
    content = content.replace(old5a, new5a)
    print("  ✓ _download_and_process_links signature updated")
else:
    print("  ✗ _download_and_process_links signature not found")

# Add global active_download_jobs after the function signature
old5b = """def _download_and_process_links(page_url, raw_links, batch_size, corr_id, upscale_enabled=False, upscale_model='4xNomos8k_atd'):
    if not scraper:"""
new5b = """def _download_and_process_links(page_url, raw_links, batch_size, corr_id, upscale_enabled=False, upscale_model='4xNomos8k_atd'):
    global active_download_jobs
    
    if not scraper:"""
if old5b in content:
    content = content.replace(old5b, new5b)
    print("  ✓ global active_download_jobs added")

# Update the scraper error handling
old5c = """    if not scraper:
        logger.error(f"[correlationId: {corr_id}] [Media Pipeline] Scraper module not loaded. Aborting process.")
        update_job_progress(corr_id, status="failed")
        return"""
new5c = """    if not scraper:
        logger.error(f"[correlationId: {corr_id}] [Media Pipeline] Scraper module not loaded. Aborting process.")
        update_job_progress(corr_id, status="failed")
        with download_task_lock:
            active_download_jobs -= 1
        return"""
if old5c in content:
    content = content.replace(old5c, new5c)
    print("  ✓ scraper error handling updated")

# Add upscaling info to job tracking
old5d = """    update_job_progress(corr_id, total_links=len(unique_urls))
    logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Processing {len(unique_urls)} link(s)...")"""
new5d = """    update_job_progress(corr_id, total_links=len(unique_urls))
    
    # Update job with upscaling info
    with zipper_jobs_lock:
        if corr_id in active_zipper_jobs:
            active_zipper_jobs[corr_id]["upscale_enabled"] = upscale_enabled
            active_zipper_jobs[corr_id]["upscale_model"] = upscale_model
    
    logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Processing {len(unique_urls)} link(s)...")"""
if old5d in content:
    content = content.replace(old5d, new5d)
    print("  ✓ upscaling info added to job tracking")

# Update the worker call
old5e = """    if image_urls:
        _download_and_zip_images_worker(url_slug, page_url, image_urls, batch_size, headers, corr_id)"""
new5e = """    if image_urls:
        _download_and_zip_images_worker(url_slug, page_url, image_urls, batch_size, headers, corr_id, upscale_enabled, upscale_model)
    else:
        with download_task_lock:
            active_download_jobs -= 1"""
if old5e in content:
    content = content.replace(old5e, new5e)
    print("  ✓ worker call updated")

# Patch 6: Update _download_and_zip_images_worker
print("Applying Patch 6: _download_and_zip_images_worker...")
old6 = """def _download_and_zip_images_worker(url_slug, page_url, img_info_list, batch_size, headers, corr_id):
    import zipfile
    import random
    
    zip_writer = None
    zip_path = None
    count = 0
    zip_file_count = 0"""

new6 = """def _download_and_zip_images_worker(url_slug, page_url, img_info_list, batch_size, headers, corr_id, upscale_enabled=False, upscale_model='4xNomos8k_atd'):
    import zipfile
    import random
    
    global active_download_jobs
    
    zip_writer = None
    zip_path = None
    count = 0
    zip_file_count = 0
    upscaler = None
    upscale_success_count = 0
    upscale_fail_count = 0
    start_time = time.time()
    
    # Initialize upscaler if enabled
    if upscale_enabled:
        try:
            from app.services.upscaler import ImageUpscaler
            upscaler = ImageUpscaler()
            logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Upscaling enabled with model: {upscale_model}")
        except Exception as e:
            logger.error(f"[correlationId: {corr_id}] [Media Pipeline] Failed to initialize upscaler: {e}")
            upscale_enabled = False"""
if old6 in content:
    content = content.replace(old6, new6)
    print("  ✓ _download_and_zip_images_worker signature and initialization updated")
else:
    print("  ✗ _download_and_zip_images_worker pattern not found")

# Add upscaling logic in the worker loop
old6b = """        logger.info(f"[correlationId: {file_corr_id}] [Media Pipeline] Downloading image: {img_url}")
        content = download_image_throttled(img_url, headers, file_corr_id)
        if not content:
            update_job_progress(file_corr_id, increment_processed=True)
            continue"""

new6b = """        logger.info(f"[correlationId: {file_corr_id}] [Media Pipeline] Downloading image: {img_url}")
        content = download_image_throttled(img_url, headers, file_corr_id)
        if not content:
            update_job_progress(file_corr_id, increment_processed=True)
            continue
        
        # Upscale if enabled
        if upscale_enabled and upscaler and content:
            try:
                original_size = len(content)
                content = upscaler.upscale_image(content, model_name=upscale_model)
                upscale_success_count += 1
                logger.info(f"[correlationId: {file_corr_id}] [Media Pipeline] Upscaled image {img_url} ({original_size} -> {len(content)} bytes)")
            except Exception as e:
                upscale_fail_count += 1
                logger.error(f"[correlationId: {file_corr_id}] [Media Pipeline] Upscaling failed for {img_url}: {e}")
                # Continue with original image"""
if old6b in content:
    content = content.replace(old6b, new6b)
    print("  ✓ upscaling logic added to worker loop")

# Update the end of _download_and_zip_images_worker
old6c = """    logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Finished downloading and zipping task for: {page_url}")"""

new6c = """    # Log upscaling metrics
    if upscale_enabled:
        total_time = time.time() - start_time
        avg_time = total_time / max(1, len(img_info_list))
        log_upscale_metrics(
            corr_id,
            upscale_model,
            len(img_info_list),
            upscale_success_count,
            upscale_fail_count,
            total_time,
            avg_time
        )
    
    logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Finished downloading and zipping task for: {page_url}")
    
    with download_task_lock:
        active_download_jobs -= 1"""
if old6c in content:
    content = content.replace(old6c, new6c)
    print("  ✓ metrics logging and cleanup added to worker")

# Write the patched content back
print("\nWriting patched file...")
with open(file_path, 'w') as f:
    f.write(content)

print("✓ All patches applied successfully!")

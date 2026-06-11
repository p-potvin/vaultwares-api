#!/usr/bin/env python
"""Script to patch api_server.py with upscaling support"""

import re

# Read the file
with open('api_server.py', 'r') as f:
    content = f.read()

# 1. Update DownloadPayload model
old_model = """class DownloadPayload(BaseModel):
    url: str
    links: List[str]
    batch_size: Optional[int] = 100"""

new_model = """class DownloadPayload(BaseModel):
    url: str
    links: List[str]
    batch_size: Optional[int] = 5
    upscale_enabled: Optional[bool] = False
    upscale_model: Optional[str] = "4xNomos8k_atd""""

content = content.replace(old_model, new_model)

# 2. Update _run_downloader_thread function signature and call
old_run_downloader = """def _run_downloader_thread(url, links, batch_size, corr_id):
    logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Background downloader task started for URL: {url} ({len(links)} links)")
    os.makedirs(ZIPPER_DEST_DIR, exist_ok=True)
    _download_and_process_links(url, links, batch_size, corr_id)"""

new_run_downloader = """def _run_downloader_thread(url, links, batch_size, corr_id, upscale_enabled=False, upscale_model='4xNomos8k_atd'):
    logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Background downloader task started for URL: {url} ({len(links)} links)")
    os.makedirs(ZIPPER_DEST_DIR, exist_ok=True)
    _download_and_process_links(url, links, batch_size, corr_id, upscale_enabled, upscale_model)"""

content = content.replace(old_run_downloader, new_run_downloader)

# 3. Update _download_and_process_links function signature
old_download_process = """def _download_and_process_links(page_url, raw_links, batch_size, corr_id):
    if not scraper:
        logger.error(f"[correlationId: {corr_id}] [Media Pipeline] Scraper module not loaded. Aborting process.")
        update_job_progress(corr_id, status="failed")
        return
        
    headers = {"""

new_download_process = """def _download_and_process_links(page_url, raw_links, batch_size, corr_id, upscale_enabled=False, upscale_model='4xNomos8k_atd'):
    global active_download_jobs
    
    if not scraper:
        logger.error(f"[correlationId: {corr_id}] [Media Pipeline] Scraper module not loaded. Aborting process.")
        update_job_progress(corr_id, status="failed")
        with download_task_lock:
            active_download_jobs -= 1
        return
        
    headers = {"""

# Check if this exact pattern exists first
if old_download_process in content:
    content = content.replace(old_download_process, new_download_process)
else:
    # Try to find and replace just the signature
    content = re.sub(
        r'def _download_and_process_links\(page_url, raw_links, batch_size, corr_id\):ciendo',
        r'def _download_and_process_links(page_url, raw_links, batch_size, corr_id, upscale_enabled=False, upscale_model=\'4xNomos8k_atd\'):\n    global active_download_jobs\n    \n    ',
        content
    )

# 4. Add upscaling info to job tracking
old_job_create = """    with zipper_jobs_lock:
        active_zipper_jobs[corr_id] = {
            "status": "running",
            "url": payload.url,
            "total_links": len(payload.links),
            "processed_links": 0,
            "images_count": 0,
            "other_files_count": 0,
            "created_at": time.time(),
            "updated_at": time.time()
        }"""

new_job_create = """    with zipper_jobs_lock:
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
        }"""

content = content.replace(old_job_create, new_job_create)

# 5. Update the call to _download_and_zip_images_worker
old_worker_call = """    if image_urls:
        _download_and_zip_images_worker(url_slug, page_url, image_urls, batch_size, headers, corr_id)"""

new_worker_call = """    if image_urls:
        _download_and_zip_images_worker(url_slug, page_url, image_urls, batch_size, headers, corr_id, upscale_enabled, upscale_model)
    else:
        with download_task_lock:
            active_download_jobs -= 1"""

content = content.replace(old_worker_call, new_worker_call)

# 6. Add upscaling info to job tracking in _download_and_process_links
old_progress_update = """    update_job_progress(corr_id, total_links=len(unique_urls))
    logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Processing {len(unique_urls)} link(s)...")"""

new_progress_update = """    update_job_progress(corr_id, total_links=len(unique_urls))
    
    # Update job with upscaling info
    with zipper_jobs_lock:
        if corr_id in active_zipper_jobs:
            active_zipper_jobs[corr_id]["upscale_enabled"] = upscale_enabled
            active_zipper_jobs[corr_id]["upscale_model"] = upscale_model
    
    logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Processing {len(unique_urls)} link(s)...")"""

content = content.replace(old_progress_update, new_progress_update)

# Write the file back
with open('api_server.py', 'w') as f:
    f.write(content)

print("Patched api_server.py successfully")

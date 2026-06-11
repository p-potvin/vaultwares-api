#!/usr/bin/env python
"""Patch remaining changes to api_server.py"""

file_path = 'C:\\Users\\Administrator\\Desktop\\Github Repos\\vaultwares-api\\api_server.py'

with open(file_path, 'r') as f:
    content = f.read()

print("Loaded file...")

# Update the worker call in _download_and_process_links
print("Patching worker call...")
old_call = """    if image_urls:
        _download_and_zip_images_worker(url_slug, page_url, image_urls, batch_size, headers, corr_id)


def _download_direct_file_worker"""

new_call = """    if image_urls:
        _download_and_zip_images_worker(url_slug, page_url, image_urls, batch_size, headers, corr_id, upscale_enabled, upscale_model)
    else:
        with download_task_lock:
            active_download_jobs -= 1


def _download_direct_file_worker"""

if old_call in content:
    content = content.replace(old_call, new_call)
    print("  OK: Worker call updated")
else:
    print("  FAIL: Worker call pattern not found")
    print("Looking for similar...")
    if 'if image_urls:' in content and '_download_and_zip_images_worker' in content:
        # Find the exact occurrence in _download_and_process_links
        idx = content.find('    if image_urls:\n        _download_and_zip_images_worker')
        if idx != -1:
            print(f"  Found at position {idx}")
            print(f"  Context: {repr(content[idx:idx+150])}")

# Update _download_and_zip_images_worker signature and body
print("Patching _download_and_zip_images_worker...")
old_worker = """def _download_and_zip_images_worker(url_slug, page_url, img_info_list, batch_size, headers, corr_id):
    import zipfile
    import random
    
    zip_writer = None
    zip_path = None
    count = 0
    zip_file_count = 0"""

new_worker = """def _download_and_zip_images_worker(url_slug, page_url, img_info_list, batch_size, headers, corr_id, upscale_enabled=False, upscale_model='4xNomos8k_atd'):
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

if old_worker in content:
    content = content.replace(old_worker, new_worker)
    print("  OK: Worker function signature and initialization updated")
else:
    print("  FAIL: Worker function pattern not found")

# Add upscaling logic in the worker loop
print("Patching upscaling logic...")
old_loop = """        logger.info(f"[correlationId: {file_corr_id}] [Media Pipeline] Downloading image: {img_url}")
        content = download_image_throttled(img_url, headers, file_corr_id)
        if not content:
            update_job_progress(file_corr_id, increment_processed=True)
            continue"""

new_loop = """        logger.info(f"[correlationId: {file_corr_id}] [Media Pipeline] Downloading image: {img_url}")
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

if old_loop in content:
    content = content.replace(old_loop, new_loop)
    print("  OK: Upscaling logic added")
else:
    print("  FAIL: Upscaling logic pattern not found")

# Update the end of _download_and_zip_images_worker
print("Patching worker end...")
old_end = """    logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Finished downloading and zipping task for: {page_url}")"""

new_end = """    # Log upscaling metrics
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

if old_end in content:
    content = content.replace(old_end, new_end)
    print("  OK: Worker end updated with metrics and cleanup")
else:
    print("  FAIL: Worker end pattern not found")

# Write back
print("\nWriting patched file...")
with open(file_path, 'w') as f:
    f.write(content)

print("Done!")

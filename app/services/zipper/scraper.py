import os
import sys
import re
import random
import zipfile
import argparse
import subprocess
from urllib.parse import urlparse, urljoin

def install_dependencies():
    dependencies = ["beautifulsoup4", "requests", "pillow"]
    missing = []
    for dep in dependencies:
        try:
            if dep == "beautifulsoup4":
                __import__("bs4")
            elif dep == "pillow":
                __import__("PIL")
            else:
                __import__(dep)
        except ImportError:
            missing.append(dep)
            
    if missing:
        print(f"Missing dependencies for scraper: {missing}. Installing them now...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
            print("Dependencies installed successfully.")
        except Exception as e:
            print(f"Failed to install dependencies: {e}")
            sys.exit(1)

# Ensure packages are installed
install_dependencies()

import requests
from bs4 import BeautifulSoup

def get_url_slug(url):
    try:
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        if not path:
            path = parsed.netloc
        slug = re.sub(r'[^a-zA-Z0-9_\-]', '_', path)
        slug = re.sub(r'_+', '_', slug).strip("_")
        return slug or "download"
    except Exception:
        return "download"

def download_image(url, headers):
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.content
    except Exception as e:
        print(f"Failed to download image from {url}: {e}")
    return None

def scrape_with_requests(url, selector_str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching page {url}: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    
    if selector_str:
        container = soup.select_one(selector_str)
        if not container:
            print(f"Warning: Selector '{selector_str}' not found. Falling back to whole document.")
            container = soup
    else:
        container = soup

    img_tags = container.find_all("img")
    raw_urls = []
    for img in img_tags:
        # Extract src, data-src, or href attributes
        src = img.get("src") or img.get("data-src") or img.get("href")
        if src:
            raw_urls.append(src)
            
    # Resolve relative URLs
    resolved_urls = []
    for r_url in raw_urls:
        full_url = urljoin(url, r_url)
        if full_url.startswith("http://") or full_url.startswith("https://"):
            resolved_urls.append(full_url)
            
    # De-duplicate while preserving order
    unique_urls = []
    seen = set()
    for u in resolved_urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)
            
    return unique_urls

def scrape_with_playwright(url, selector_str):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed. Installing it now...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
            subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
            from playwright.sync_api import sync_playwright
        except Exception as e:
            print(f"Failed to load/install playwright: {e}")
            sys.exit(1)

    unique_urls = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        print(f"Loading page with browser: {url}...")
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception as e:
            print(f"Playwright navigation warning: {e}. Trying to parse whatever loaded.")

        # If selector is provided, check if it exists
        if selector_str:
            try:
                page.wait_for_selector(selector_str, timeout=5000)
                eval_target = f"document.querySelector('{selector_str}')"
            except Exception:
                print(f"Warning: Selector '{selector_str}' not found in time. Falling back to document.")
                eval_target = "document"
        else:
            eval_target = "document"

        # Evaluate JS to extract all image URLs
        js_code = f"""
        () => {{
            const container = {eval_target};
            if (!container) return [];
            const nodes = container.querySelectorAll('img');
            return Array.from(nodes).map(el => el.href || el.src);
        }}
        """
        raw_urls = page.evaluate(js_code)
        browser.close()

    resolved_urls = []
    for r_url in raw_urls:
        full_url = urljoin(url, r_url)
        if full_url.startswith("http://") or full_url.startswith("https://"):
            resolved_urls.append(full_url)

    seen = set()
    for u in resolved_urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    return unique_urls

def main():
    parser = argparse.ArgumentParser(description="Scrape images from a website and download them as ZIP archives.")
    parser.add_argument("--url", required=True, help="URL of the website to scrape.")
    parser.add_argument("--selector", default="", help="Optional CSS selector of the container element.")
    parser.add_argument("--dest", default="", help="Optional destination directory for the downloaded ZIPs (default: project_root/.downloaded/).")
    parser.add_argument("--batch-size", type=int, default=100, help="Number of images per ZIP file (default: 100).")
    parser.add_argument("--playwright", action="store_true", help="Use browser execution (Playwright) to scrape dynamic websites.")
    args = parser.parse_args()

    # Determine default destination
    if not args.dest:
        # Resolve script path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        args.dest = os.path.join(project_root, ".downloaded")
    
    os.makedirs(args.dest, exist_ok=True)
    print(f"Target destination directory: {args.dest}")

    # Step 1: Scrape image URLs
    if args.playwright:
        urls = scrape_with_playwright(args.url, args.selector)
    else:
        urls = scrape_with_requests(args.url, args.selector)

    print(f"Scraped {len(urls)} unique image URLs.")
    if not urls:
        print("No valid image URLs found. Exiting.")
        sys.exit(0)

    # Step 2: Download and package in ZIP files
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    url_slug = get_url_slug(args.url)
    zip_writer = None
    zip_path = None
    count = 0
    zip_file_count = 0

    for i, img_url in enumerate(urls):
        # Determine extension
        parsed_img = urlparse(img_url)
        ext = os.path.splitext(parsed_img.path)[1].lower().strip(".")
        if ext not in ["jpg", "jpeg", "png", "gif", "webp", "svg"]:
            ext = "jpg"

        print(f"Downloading ({i+1}/{len(urls)}): {img_url}")
        content = download_image(img_url, headers)
        if not content:
            continue

        # Initialize zip writer if needed
        if zip_writer is None:
            random_suffix = random.randint(0, 9000)
            zip_filename = f"{url_slug}_{random_suffix}.zip"
            zip_path = os.path.join(args.dest, zip_filename)
            zip_writer = zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED)
            zip_file_count += 1
            print(f"Creating new ZIP archive: {zip_path}")

        # Add file to ZIP
        filename_in_zip = f"{url_slug}_{str(count + 1).padStart(3, '0')}.{ext}" if hasattr(str, 'padStart') else f"{url_slug}_{str(count + 1).zfill(3)}.{ext}"
        try:
            zip_writer.writestr(filename_in_zip, content)
            count += 1
        except Exception as e:
            print(f"Failed to add image to zip: {e}")

        # Batch check
        if count > 0 and count % args.batch_size == 0:
            zip_writer.close()
            zip_writer = None
            print(f"Closed ZIP archive {zip_path} with {args.batch_size} files.")
            count = 0

    # Close the final zip if any files were written
    if zip_writer is not None:
        zip_writer.close()
        print(f"Closed final ZIP archive {zip_path} with {count} files.")

    print(f"Completed downloading and zipping {zip_file_count} archives into {args.dest}.")

if __name__ == "__main__":
    main()

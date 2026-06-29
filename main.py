"""
run this locally once to scrape fitgirl-repacks and build a local catalog of repacks with metadata.
after that, use update.py to refresh the catalog with new releases. feel free to tweak the script as needed,
but please keep the original author credits.
"""

# author: v7upsln
# github: https://github.com/v7upSln
# repo: https://github.com/v7upSln/CrackEasy-Cache

import os
import json
import time
import re
import sys
import hashlib
from bs4 import BeautifulSoup
import undetected_chromedriver as uc

ITEMS_PER_DISCOVER_PAGE = 30
PROGRESS_FILE = "Cache/scraping_progress.json"

def init_driver():
    print("[*] Configuring Chrome with headless anti-detection profiles...")
    options = uc.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36')
    
    print("[*] Launching browser engine instance...")
    driver = uc.Chrome(options=options, version_main=149)
    print("[+] Browser engine online and operational.")
    return driver

def clean_title(title_text):
    if not title_text:
        return ""
    title_text = title_text.replace('&#8211;', '-').replace('&amp;', '&')
    return re.sub(r'\s+', ' ', title_text).strip()

def get_md5_hash(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def ensure_directories():
    for folder in ['Cache', 'metadata', 'discover_pages']:
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
            print(f"[SYSTEM] Created missing directory: {folder}")

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"[+] Resuming session: Found {len(data.get('links_pool', {}))} cataloged links and {len(data.get('scraped_details', {}))} scraped profiles.")
                return data
        except Exception as e:
            print(f"[!] Warning: Progress checkpoint file corrupted ({e}). Initializing clean slate.")
            pass
    print("[*] No progress checkpoint discovered. Commencing fresh extraction pass.")
    return {"stage": "index", "last_page": 0, "links_pool": {}, "scraped_details": {}}

def save_progress(progress_data):
    ensure_directories()
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress_data, f, ensure_ascii=False, indent=2)

def update_live_database(final_items_list):
    catalog = list(final_items_list)
    total_items = len(catalog)
    
    with open("metadata/catalog_all.json", "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    with open("metadata/catalog_fitgirl.json", "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    cache_index = []
    for item in catalog:
        cache_index.append({
            "id": item["id"],
            "title": item["title"],
            "url": item["url"],
            "provider": item["provider"],
            "cover_url": item["cover_url"],
            "repack_size": item["repack_size"]
        })

    with open("Cache/fitgirl.json", "w", encoding="utf-8") as f:
        json.dump({"last_updated": int(time.time()), "items": cache_index}, f, ensure_ascii=False, indent=2)

    total_pages = (total_items + ITEMS_PER_DISCOVER_PAGE - 1) // ITEMS_PER_DISCOVER_PAGE
    for idx in range(0, len(cache_index), ITEMS_PER_DISCOVER_PAGE):
        page_num = (idx // ITEMS_PER_DISCOVER_PAGE) + 1
        chunk = cache_index[idx:idx + ITEMS_PER_DISCOVER_PAGE]
        
        discover_page_content = {
            "page": page_num,
            "total_pages": total_pages,
            "items": chunk
        }
        with open(f"discover_pages/page_{page_num}.json", "w", encoding="utf-8") as f:
            json.dump(discover_page_content, f, ensure_ascii=False, indent=2)

def parse_game_page_details(html_source):
    metadata = {
        "cover_url": "",
        "original_size": "Unknown",
        "repack_size": "Unknown",
        "genres": []
    }
    
    soup = BeautifulSoup(html_source, 'html.parser')
    
    # find the main content block
    entry_content = soup.find('div', class_='entry-content')
    if not entry_content:
        entry_content = soup
    
    # find a cover image first
    img_tags = entry_content.find_all('img')
    for img in img_tags:
        src = img.get('src', '') or img.get('data-src', '')
        if not src:
            continue
        if any(bad in src for bad in ['avatar', 'hitcounter', 'donate', 'paypal', 'logo']):
            continue
            
        if 'riotpixels' in src or 'imageban' in src or 'fitgirl-repacks' in src:
            src = src.replace('.240p.jpg', '').replace('.480p.jpg', '')
            metadata["cover_url"] = src
            break
            
    if not metadata["cover_url"] and img_tags:
        metadata["cover_url"] = img_tags[0].get('src', '')

    full_text = entry_content.get_text()


    def extract_field(text, pattern):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).split('\n')[0].strip()
        return "Unknown"

    # Match patterns across the full inner text block layout
    metadata["original_size"] = extract_field(full_text, r'Original\s+Size\s*:\s*([^\r\n]+)')
    metadata["repack_size"] = extract_field(full_text, r'Repack\s+Size\s*:\s*([^\r\n]+)')
    
    genres_raw = extract_field(full_text, r'(?:Genres?\/Tags?|Genre\/Tags?|Genres?)\s*:\s*([^\r\n]+)')
    if genres_raw != "Unknown":
        metadata["genres"] = [g.strip() for g in genres_raw.split(',') if g.strip()]

    return metadata

def run_scraper_pipeline():
    ensure_directories()
    progress = load_progress()
    driver = init_driver()
    
    # === stage 1: gather index from a-z pages
    if progress["stage"] == "index":
        print("\n" + "="*60)
        print("[*] STAGE 1: HARVESTING GAME INDEX FROM A-Z MAP (PAGES 1 to 140)")
        print("="*60)
        base_az_url = "https://fitgirl-repacks.site/all-my-repacks-a-z/?lcp_page0={page}#lcp_instance_0"
        
        start_page = progress["last_page"] + 1
        for page in range(start_page, 141):
            target_url = base_az_url.format(page=page)
            print(f"[➔] Requesting A-Z Index Page [{page}/140] -> {target_url}")
            
            try:
                start_time = time.time()
                driver.get(target_url)
                load_duration = time.time() - start_time
                print(f"    [INFO] DOM fetched in {load_duration:.2f}s. Extracting listing elements...")
                
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                list_items = soup.select('ul.lcp_catlist li a') or soup.find_all('a', href=True)
                
                found_on_page = 0
                for anchor in list_items:
                    url = anchor.get('href', '')
                    title = clean_title(anchor.get_text())
                    
                    if not url or "all-my-repacks-a-z" in url or not title or len(title) < 3:
                        continue
                        
                    if url not in progress["links_pool"]:
                        progress["links_pool"][url] = title
                        found_on_page += 1
                    
                print(f"[+] Page {page} parsing complete: Added {found_on_page} target links. Total pool: {len(progress['links_pool'])}")
                progress["last_page"] = page
                save_progress(progress)
                
                time.sleep(2.0)
                
            except Exception as e:
                print(f"[!] Critical Error parsing index board page {page}: {e}")
                print("[*] Cooling engine down for 5 seconds before retry...")
                time.sleep(5)
                
        progress["stage"] = "details"
        save_progress(progress)
        print(f"\n[+] STAGE 1 COMPLETE: Extracted a total of {len(progress['links_pool'])} target links.")

    # === stage 2: process and scrape deep details ===
    if progress["stage"] == "details":
        print("\n" + "="*60)
        print("[*] STAGE 2: LIVE DEEP ELEMENT EXTRACTION & LIVE DATABASE UPDATES")
        print("="*60)
        total_links = len(progress["links_pool"])
        
        current_index = 0
        for url, title in list(progress["links_pool"].items()):
            current_index += 1
            game_id = get_md5_hash(url)
            
            if game_id in progress["scraped_details"]:
                print(f"[SKIP] [{current_index}/{total_links}] Already synced: {title} ({game_id})")
                continue
                
            print(f"\n[➔] PROCESSING ENTRY [{current_index}/{total_links}]: {title}")
            print(f"    [URL] {url}")
            print(f"    [ID]  {game_id}")
            
            try:
                start_time = time.time()
                driver.get(url)
                fetch_time = time.time() - start_time
                print(f"    [HTTP] Document loaded in {fetch_time:.2f}s. Inspecting DOM structural properties...")
                
                parsed_data = parse_game_page_details(driver.page_source)
                
                print(f"    [DATA] Cover URL : {parsed_data['cover_url']}")
                print(f"    [DATA] Orig Size : {parsed_data['original_size']}")
                print(f"    [DATA] Rpck Size : {parsed_data['repack_size']}")
                print(f"    [DATA] Genres    : {', '.join(parsed_data['genres']) if parsed_data['genres'] else 'None Listed'}")
                
                game_entry = {
                    "id": game_id,
                    "title": title,
                    "url": url,
                    "provider": "fitgirl",
                    "cover_url": parsed_data["cover_url"],
                    "original_size": parsed_data["original_size"],
                    "repack_size": parsed_data["repack_size"],
                    "genres": parsed_data["genres"]
                }
                
                # write the item file right away
                meta_filename = f"metadata/{game_id}.json"
                with open(meta_filename, "w", encoding="utf-8") as f:
                    json.dump(game_entry, f, ensure_ascii=False, indent=2)
                print(f"    [DB] Successfully wrote standalone file: {meta_filename}")
                
                # keep the state map updated
                progress["scraped_details"][game_id] = game_entry
                
                # refresh the shared index files immediately
                update_live_database(progress["scraped_details"].values())
                
                if current_index % 5 == 0:
                    save_progress(progress)
                    print(f"    [PROGRESS] Progress tracking session file flushed cleanly to disk layout.")
                
                time.sleep(1.8)
                    
            except Exception as e:
                print(f"    [!] Error pulling details for target element '{title}': {str(e)}")
                print("    [!] Proceeding to subsequent record...")
                continue
                
        print("\n[+] Complete catalog deep harvesting operation finalized.")
        save_progress(progress)
        
    driver.quit()
    print("[+] Scraping process concluded. Browser engine decommissioned successfully.")

if __name__ == "__main__":
    run_scraper_pipeline()
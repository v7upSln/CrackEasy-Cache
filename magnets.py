import os
import json
import time
import re
from bs4 import BeautifulSoup
import undetected_chromedriver as uc

METADATA_DIR = "metadata"
PROGRESS_FILE = "Cache/scraping_progress.json"
ITEMS_PER_DISCOVER_PAGE = 30

# Set to True to start from the top and overwrite ALL files from scratch.
# Set to False to only process files that are missing magnets.
REWRITE_ALL_FROM_SCRATCH = True 

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

def run_magnet_patcher():
    if not os.path.exists(METADATA_DIR):
        print(f"[!] Target directory '{METADATA_DIR}' not found.")
        return

    all_files = os.listdir(METADATA_DIR)
    json_targets = [f for f in all_files if re.match(r'^[a-f0-9]{32}\.json$', f)]
    total_files = len(json_targets)
    
    print(f"[+] Found {total_files} standalone metadata elements to check.")
    
    to_process = []
    all_game_entries = {}
    
    for filename in json_targets:
        file_path = os.path.join(METADATA_DIR, filename)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                item_data = json.load(f)
                
            # Keep a working copy for re-sync logs later
            all_game_entries[item_data["id"]] = item_data
            
            # If Rewrite mode is on, queue everything. Otherwise, skip ..
            if REWRITE_ALL_FROM_SCRATCH:
                to_process.append((file_path, item_data))
            else:
                if "magnets" not in item_data or not item_data["magnets"]:
                    to_process.append((file_path, item_data))
        except Exception as e:
            print(f"[!] Failed to parse file template {filename}: {e}")

    items_needed = len(to_process)
    
    if REWRITE_ALL_FROM_SCRATCH:
        print(f"[➔] REWRITE MODE ACTIVE: Queueing ALL {items_needed} items to overwrite from the top.")
    else:
        print(f"[*] Analysis complete: {items_needed} items are missing magnet data layout strings.")
    
    if items_needed == 0:
        print("[+] Everything is completely up to date! Exiting.")
        return

# start driver
    driver = init_driver()
    processed_count = 0
    
    try:
        for file_path, item in to_process:
            processed_count += 1
            print(f"\n[➔] PATCHING ENTRY [{processed_count}/{items_needed}]: {item['title']}")
            print(f"    [URL] {item['url']}")
            
            try:
                start_time = time.time()
                driver.get(item['url'])
                fetch_time = time.time() - start_time
                print(f"    [HTTP] Loaded page source properties in {fetch_time:.2f}s.")
                
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                entry_content = soup.find('div', class_='entry-content') or soup
                
                magnets = []
                for anchor in entry_content.find_all('a', href=True):
                    href = anchor['href'].strip()
                    if href.startswith('magnet:'):
                        if href not in magnets:
                            magnets.append(href)
                            marker_label = anchor.get_text(strip=True) or "Magnet Link"
                            print(f"        [+] Marked & Added -> {marker_label}")
                
                item["magnets"] = magnets
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(item, f, ensure_ascii=False, indent=2)
                print(f"    [DB] Successfully updated metadata file. Found {len(magnets)} magnets.")
                
                all_game_entries[item["id"]] = item
                
                if os.path.exists(PROGRESS_FILE):
                    try:
                        with open(PROGRESS_FILE, 'r', encoding='utf-8') as pf:
                            progress_data = json.load(pf)
                        if item["id"] in progress_data.get("scraped_details", {}):
                            progress_data["scraped_details"][item["id"]]["magnets"] = magnets
                            with open(PROGRESS_FILE, 'w', encoding='utf-8') as pf:
                                json.dump(progress_data, pf, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
                
                time.sleep(1.8)
                
            except Exception as e:
                print(f"    [!] Error pulling down details for entry '{item['title']}': {e}")
                continue
                
    finally:
        driver.quit()
        print("\n[*] Refreshing tracking indices and full database collections...")
        update_live_database(all_game_entries.values())
        print("[+] Retroactive patch pipeline operation complete.")

if __name__ == "__main__":
    run_magnet_patcher()
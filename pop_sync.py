import os
import re
import json
import time
import hashlib
import sys
from bs4 import BeautifulSoup
import undetected_chromedriver as uc

META_DIR = "metadata"
OUTPUT_FILE = "pop_repacks.json"

def get_md5(text):
    return hashlib.md5(text.strip().encode('utf-8')).hexdigest()

def get_chrome_options(headless=True):
    options = uc.ChromeOptions()
    if headless:
        options.add_argument('--headless')
    options.add_argument('--log-level=3')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--ignore-certificate-errors')
    options.add_argument('--ignore-ssl-errors')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36')
    return options

def make_driver(headless=True):
    try:
        return uc.Chrome(options=get_chrome_options(headless), version_main=149)
    except Exception as e:
        match = re.search(r"Current browser version is (\d+)", str(e))
        if match:
            detected_version = int(match.group(1))
            return uc.Chrome(options=get_chrome_options(headless), version_main=detected_version)
        raise e

def load_page_safely(driver, url, headless_tracker):
    try:
        driver.set_page_load_timeout(30)
        driver.get(url)
    except Exception as e:
        print(f"    [!] Timeout or load warning: {e}")
    
    time.sleep(3)
    title = driver.title.lower()
    
    if any(x in title for x in ["just a moment", "cloudflare", "ddos-guard"]) or "enable javascript" in driver.page_source.lower():
        print("    [!] Hit Cloudflare firewall verification window. Booting visible engine layout...")
        try: driver.quit()
        except: pass
        
        driver = make_driver(headless=False)
        driver.get(url)
        
        while any(x in driver.title.lower() for x in ["just a moment", "cloudflare", "ddos-guard"]) or "enable javascript" in driver.page_source.lower():
            print("    [...] Waiting for verification clear...")
            time.sleep(3)
        print("    [✓] Security clearance token verified successfully!")
        headless_tracker[0] = False
    return driver, driver.page_source

def load_local_metadata_cache():
    title_map = {}
    if not os.path.exists(META_DIR):
        return title_map
        
    for filename in os.listdir(META_DIR):
        if filename.endswith(".json"):
            filepath = os.path.join(META_DIR, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    meta_data = json.load(f)
                    if "title" in meta_data:
                        norm_title = meta_data["title"].lower().strip()
                        title_map[norm_title] = {
                            "filepath": filepath,
                            "data": meta_data
                        }
            except Exception:
                pass
    return title_map

def extract_chart_games(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    content_div = soup.find('div', class_='entry-content') or soup
    results = []
    seen_urls = set()
    
    for a in content_div.find_all('a'):
        href = a.get('href', '').strip()
        if not href:
            continue
            
        if 'fitgirl-repacks.site' in href and not any(x in href for x in ['/category/', '/tags/', '/comment', '?share=', '/wp-content', '/page/']):
            if not href.endswith('/'):
                href += '/'
            
            if href in seen_urls:
                continue
            
            img_el = a.find('img')
            title = img_el.get('alt', '').strip() if img_el else a.get_text(strip=True)
            title = title.replace('&#8211;', '-').strip()
            title = re.sub(r'^\d+\.\s*', '', title)
            
            if title and len(title) > 2:
                seen_urls.add(href)
                results.append({"title": title, "url": href})
    return results

def main():
    print("[*] Pre-loading local metadata library for database mapping...")
    local_title_cache = load_local_metadata_cache()

    print("[*] Initializing Chrome Engine for Charts Tracking...")
    headless_tracker = [True]
    driver = make_driver(headless=headless_tracker[0])

    chart_collections = {"monthly": [], "yearly": []}
    
    # Track which absolute file paths are actively seen on the charts
    active_monthly_paths = set()
    active_yearly_paths = set()

    targets = [
        ("monthly", "https://fitgirl-repacks.site/pop-repacks/", active_monthly_paths),
        ("yearly", "https://fitgirl-repacks.site/popular-repacks-of-the-year/", active_yearly_paths)
    ]

    # ═══════════════════════════════════════════════════════════
    # PHASE 1: SCRAPE AND RESOLVE TARGET PATHS
    # ═══════════════════════════════════════════════════════════
    for chart_type, url, active_paths_set in targets:
        print(f"\n[*] Requesting {chart_type.upper()} charts page lookup -> {url}")
        driver, html_src = load_page_safely(driver, url, headless_tracker)
        games = extract_chart_games(html_src)
        print(f"[+] Discovered {len(games)} structured game associations on chart page layout.")

        for g in games:
            game_url = g["url"]
            game_title = g["title"]
            game_id = get_md5(game_url)
            
            target_filepath = None
            status = "Unknown"
            
            # Resolve via Hash
            meta_filepath = os.path.join(META_DIR, f"{game_id}.json")
            if os.path.exists(meta_filepath):
                target_filepath = meta_filepath
                status = "Matched via Hash"
                
            # Resolve via Exact Title
            if not target_filepath:
                norm_title = game_title.lower().strip()
                if norm_title in local_title_cache:
                    target_filepath = local_title_cache[norm_title]["filepath"]
                    status = "Matched via Title"
                else:
                    # Resolve via Fuzzy Match
                    for local_title, cache_item in local_title_cache.items():
                        if norm_title in local_title or local_title in norm_title:
                            target_filepath = cache_item["filepath"]
                            status = "Matched via Fuzzy Title"
                            break

            if target_filepath:
                active_paths_set.add(os.path.abspath(target_filepath))
                # Grab a snapshot of the current state for compilation log usage
                try:
                    with open(target_filepath, "r", encoding="utf-8") as f:
                        current_data = json.load(f)
                    chart_collections[chart_type].append(current_data)
                except:
                    pass
                print(f"    [✓] Flagged active tracking vector for: {os.path.basename(target_filepath)} [{status}]")
            else:
                # If a popular game doesn't exist in local DB files yet
                compiled_item = {
                    "id": game_id,
                    "title": game_title,
                    "url": game_url,
                    "provider": "fitgirl",
                    f"pop_repack_{chart_type}": True,
                    "status": "Missing Local DB File"
                }
                chart_collections[chart_type].append(compiled_item)
                print(f"    [!] Skipped Active Vector Assignment (Not Found in DB): '{game_title}'")

    driver.quit()

    # ═══════════════════════════════════════════════════════════
    # PHASE 2: GLOBAL SWEEP & PURGE OPERATION
    # ═══════════════════════════════════════════════════════════
    print("\n[*] Running global database consistency sweep to purge stale popularity flags...")
    
    if os.path.exists(META_DIR):
        for filename in os.listdir(META_DIR):
            if not filename.endswith(".json"):
                continue
                
            file_path = os.path.abspath(os.path.join(META_DIR, filename))
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Check actual chart verification presence
                should_be_monthly = file_path in active_monthly_paths
                should_be_yearly = file_path in active_yearly_paths
                
                # Check state changes to eliminate unnecessary filesystem disk I/O writes
                modified = False
                if data.get("pop_repack_monthly", False) != should_be_monthly:
                    data["pop_repack_monthly"] = should_be_monthly
                    modified = True
                if data.get("pop_repack_yearly", False) != should_be_yearly:
                    data["pop_repack_yearly"] = should_be_yearly
                    modified = True
                
                if modified:
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    print(f"    [⇄] Syncing Flags -> {filename} [Monthly={should_be_monthly}, Yearly={should_be_yearly}]")
            except Exception as e:
                print(f"    [-] Error verification sweep context for file {filename}: {e}")

    # Write data index summary matrix log catalog
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(chart_collections, f, ensure_ascii=False, indent=2)
    
    print(f"\n[+] Script sequence complete. Database state purged and written to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()

import os
import re
import json
import time
import random
import hashlib
import sys
import html
from bs4 import BeautifulSoup
import undetected_chromedriver as uc

META_DIR = "metadata"

os.makedirs(META_DIR, exist_ok=True)

def get_md5(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()

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
        print(f"[*] Initializing Chrome Engine (Headless={headless})...")
        return uc.Chrome(options=get_chrome_options(headless))
    except Exception as e:
        match = re.search(r"Current browser version is (\d+)", str(e))
        if match:
            detected_version = int(match.group(1))
            print(f"[!] Mismatch found. Forcing driver execution stream to version: {detected_version}")
            fresh_options = get_chrome_options(headless)
            return uc.Chrome(options=fresh_options, version_main=detected_version)
        raise e

def check_site_availability(driver, url):
    try:
        print(f"[*] Pinging server health checkout -> {url}")
        driver.set_page_load_timeout(15)
        driver.get(url)
        src = driver.page_source.lower()
        
        indicators = [
            "503 service unavailable", 
            "502 bad gateway", 
            "504 gateway timeout",
            "host error",
            "connection timed out"
        ]
        if any(ind in src for ind in indicators):
            print(f"    [!] Critical: Found service drop indicator in page body.")
            return False
        return True
    except Exception as e:
        print(f"    [!] Error performing availability handshake: {e}")
        return False

def load_page_safely(driver, url):
    try:
        print(f"[*] Requesting targeted DOM layout -> {url}")
        driver.set_page_load_timeout(30)
        driver.get(url)
    except Exception as e:
        print(f"    [!] Timeout or load error occurred: {e}")
        return driver, driver.page_source

    title = driver.title.lower()
    print(f"    [INFO] Document loaded. Current Page Title: '{driver.title}'")
    
    if any(x in title for x in ["just a moment", "cloudflare", "ddos-guard"]):
        print("    [!] Hit firewall protective challenge. Switching to headful layout for visual bypass...")
        try:
            driver.quit()
        except:
            pass
        driver = make_driver(headless=False)
        driver.get(url)
        while any(x in driver.title.lower() for x in ["just a moment", "cloudflare", "ddos-guard"]):
            print("    [...] Waiting for manual challenge resolution inside browser session...")
            time.sleep(2)
        print("    [+] Challenge bypassed successfully.")
    
    return driver, driver.page_source

def parse_details(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    content = soup.find('div', class_='entry-content') or soup
    text = content.get_text()

    def find_field(pattern):
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).split('\n')[0].strip() if m else "Unknown"

    orig_size = find_field(r'Original\s+Size\s*:\s*([^\r\n]+)')
    rep_size = find_field(r'Repack\s+Size\s*:\s*([^\r\n]+)')
    genres_raw = find_field(r'(?:Genres?\/Tags?|Genre\/Tags?|Genres?)\s*:\s*([^\r\n]+)')
    genres = [g.strip() for g in genres_raw.split(',') if g.strip() and g.strip() != "Unknown"]

    cover_url = ""
    for img in content.find_all('img'):
        src = img.get('src') or img.get('data-src') or ""
        if src and not any(x in src for x in ['avatar', 'donate', 'logo', 'paypal']):
            if any(h in src for h in ['riotpixels', 'imageban', 'fitgirl-repacks']):
                cover_url = re.sub(r'([?&])resize=\d+%2C\d+(&)?', '', src).replace('?&', '?')
                break
    if not cover_url and content.find_all('img'):
        cover_url = content.find_all('img')[0].get('src', '')

    magnets = []
    for anchor in content.find_all('a', href=True):
        href = anchor['href'].strip()
        if href.startswith('magnet:'):
            if href not in magnets:
                magnets.append(href)
                marker_label = anchor.get_text(strip=True) or "Magnet Link"
                print(f"        [+] Marked & Added -> {marker_label}")

    return cover_url, orig_size, rep_size, genres, magnets

def main():
    base_url = "https://fitgirl-repacks.site/"
    feed_url = "https://fitgirl-repacks.site/feed/"
    driver = make_driver(headless=True)
    
    print("[*] Running pre-flight availability check...")
    if not check_site_availability(driver, base_url):
        print("[!] Target backend server is down right now. Exiting routine execution safely.")
        driver.quit()
        sys.exit(0)
        
    print("[*] Target server verified up. Loading RSS stream payload...")
    driver, rss_html = load_page_safely(driver, feed_url)
    
    print(f"[DEBUG] Raw payload extracted. Document size: {len(rss_html)} characters.")
    
    if "&lt;item&gt;" in rss_html or "&lt;channel&gt;" in rss_html:
        print("[!] Detected Chrome XML Viewer escaping tree. normalising document elements...")
        rss_html = html.unescape(rss_html)
        print(f"[DEBUG] Post-normalization payload size: {len(rss_html)} characters.")
        
    # Print a tiny tracking block snapshot if it looks like things are missing
    if "<item>" not in rss_html:
        print("[!] Warning: '<item>' flag tag not present in stream string layout.")
        print(f"[DEBUG] Sample dump of head window segment:\n{rss_html[:600]}\n--- End Dump ---")

    items = re.findall(r'<item>(.*?)</item>', rss_html, re.DOTALL)
    print(f"[*] Discovered {len(items)} raw feed segments.")
    
    new_games_count = 0

    for idx, raw_item in enumerate(items, start=1):
        title_match = re.search(r'<title>(.*?)</title>', raw_item, re.DOTALL)
        link_match = re.search(r'<link>(.*?)</link>', raw_item, re.DOTALL)
        
        if not title_match or not link_match:
            print(f"    [DEBUG] Segment index [{idx}] skipped: Missing explicit inner structural maps.")
            continue
            
        title = title_match.group(1)
        link = link_match.group(1)
        
        title = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', title).replace('&#8211;', '-').strip()
        link = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', link).strip()

        if "upcoming-repacks" in link or title.lower() == "upcoming repacks":
            continue
            
        game_id = get_md5(link)
        meta_filepath = os.path.join(META_DIR, f"{game_id}.json")
        
        if os.path.exists(meta_filepath):
            print(f"    [SKIP] Found matching hash file map on disk layout for: {title}")
            continue
            
        print(f" -> Found new game release: {title}")
        new_games_count += 1
        
        print(f"    [➔] Deep extracting elements for: {title}")
        driver, detail_html = load_page_safely(driver, link)
        
        try:
            cover_src, size_orig, size_rep, genres, magnets = parse_details(detail_html)
            
            entry = {
                "id": game_id,
                "title": title,
                "url": link,
                "provider": "fitgirl",
                "cover_url": cover_src,
                "original_size": size_orig,
                "repack_size": size_rep,
                "genres": genres,
                "magnets": magnets
            }
            
            with open(meta_filepath, "w", encoding="utf-8") as f:
                json.dump(entry, f, ensure_ascii=False, indent=2)
            print(f"    [+] Generated micro-node entry mapping: {meta_filepath}")
            
        except Exception as exc:
            print(f"    [!] Skipping item execution runner phase: {exc}")
            
        time.sleep(random.uniform(4.0, 10.0))
        
    print(f"[+] Execution round complete. Ingested {new_games_count} fresh repack profiles.")
    driver.quit()

if __name__ == "__main__":
    main()
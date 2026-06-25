"""
Europe Travel Content Scraper (v2 - verified against live site structure)
===========================================================================
Crawls:
  1. Lonely Planet's article hub for Europe-related travel stories
  2. Thrillophilia's "Places to Visit in Europe" page (includes an explicit
     "Best Time to Visit" field per place, used here to filter for July/Aug)

KEY FINDINGS FROM TESTING (June 2026):
  - lonelyplanet.com/search is BLOCKED by their robots.txt. Don't crawl it.
  - lonelyplanet.com/articles and /articles/<slug> pages ARE crawlable.
  - thrillophilia.com/places-to-visit-in-europe IS crawlable and lists ~75
    places, each with Country / Best Time to Visit / Suggested Duration.

Requirements:
    pip install requests beautifulsoup4 lxml
"""

import csv
import random
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
REQUEST_TIMEOUT = 15

# Months we care about for filtering "Best Time to Visit" fields
TARGET_MONTHS = ["june", "july", "august"]


def polite_sleep(min_s=2.0, max_s=4.0):
    time.sleep(random.uniform(min_s, max_s))


def get_soup(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except requests.RequestException as e:
        print(f"[!] Failed to fetch {url}: {e}")
        return None


def mentions_target_months(text):
    """True if a 'best time to visit' string overlaps June/July/August."""
    text_lower = text.lower()
    return any(month in text_lower for month in TARGET_MONTHS)


# ---------------------------------------------------------------------------
# 1. LONELY PLANET
# ---------------------------------------------------------------------------

# Known-good entry points (verified reachable, not blocked by robots.txt).
LONELY_PLANET_HUBS = [
    "https://www.lonelyplanet.com/europe/articles",
    "https://www.lonelyplanet.com/articles",
]


def scrape_lonely_planet():
    """
    Crawls Lonely Planet article hub pages, collects links to individual
    /articles/<slug> pages whose link text mentions Europe or summer-related
    keywords, then visits each article to pull title + intro paragraphs.
    """
    results = []
    seen_urls = set()
    base_url = "https://www.lonelyplanet.com"

    keyword_filter = [
        "europe", "summer", "july", "august", "mediterranean", "greece",
        "italy", "spain", "france", "croatia", "portugal", "balkan",
    ]

    for hub_url in LONELY_PLANET_HUBS:
        print(f"[LonelyPlanet] Fetching hub: {hub_url}")
        soup = get_soup(hub_url)
        if soup is None:
            continue

        # Article links all follow the pattern /articles/<slug>
        for a_tag in soup.select("a[href*='/articles/']"):
            href = a_tag.get("href", "")
            link_text = a_tag.get_text(strip=True)
            if not href or not link_text:
                continue

            full_url = urljoin(base_url, href)
            if full_url in seen_urls:
                continue

            combined = (link_text + " " + href).lower()
            if not any(k in combined for k in keyword_filter):
                continue

            seen_urls.add(full_url)
            results.append({
                "source": "Lonely Planet",
                "title": link_text,
                "url": full_url,
                "summary": "",  # filled in below
            })

        polite_sleep()

    # Visit each matched article to grab a real summary (first paragraph)
    for item in results:
        print(f"[LonelyPlanet] Fetching article: {item['url']}")
        article_soup = get_soup(item["url"])
        if article_soup is None:
            continue

        meta_desc = article_soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            item["summary"] = meta_desc["content"].strip()
        else:
            first_p = article_soup.find("p")
            if first_p:
                item["summary"] = first_p.get_text(strip=True)

        polite_sleep()

    return results


# ---------------------------------------------------------------------------
# 2. THRILLOPHILIA
# ---------------------------------------------------------------------------

THRILLOPHILIA_EUROPE_URL = "https://www.thrillophilia.com/places-to-visit-in-europe"


def scrape_thrillophilia():
    """
    Scrapes Thrillophilia's "75 Places to Visit in Europe" page. Each place
    is listed under a heading (h2/h3) with a description paragraph and a
    line containing 'Country:', 'Best Time to Visit:', and
    'Suggested Duration:'. We extract those fields with regex on each
    place's text block, since exact div/class names can change without
    notice on this kind of content page.
    """
    print(f"[Thrillophilia] Fetching: {THRILLOPHILIA_EUROPE_URL}")
    soup = get_soup(THRILLOPHILIA_EUROPE_URL)
    if soup is None:
        return []

    results = []

    # Each place appears to be introduced by an <h2> or <h3> with just the
    # place name (e.g. "Switzerland", "Paris", "Rome"). We walk the page's
    # headings and grab the text following each one, up to the next heading.
    headings = soup.find_all(["h2", "h3"])

    for i, heading in enumerate(headings):
        place_name = heading.get_text(strip=True)
        if not place_name or len(place_name) > 60:
            # Skip section headers like "Best Places To See In Europe"
            continue

        # Collect text from siblings until the next heading
        block_text_parts = []
        for sib in heading.find_next_siblings():
            if sib.name in ("h2", "h3"):
                break
            block_text_parts.append(sib.get_text(" ", strip=True))
        block_text = " ".join(block_text_parts)

        if not block_text:
            continue

        country_match = re.search(r"Country:\s*([A-Za-z ,]+?)(?:\s{2,}|$|Best Time)", block_text)
        best_time_match = re.search(r"Best Time to Visit:?\s*([A-Za-z ,\-]+?)(?:Suggested Duration|$)", block_text)
        duration_match = re.search(r"Suggested Duration:?\s*([0-9A-Za-z \-]+?)(?:$)", block_text)

        # Only keep entries that actually look like place entries (have at
        # least a "Best Time to Visit" field — filters out unrelated headings)
        if not best_time_match:
            continue

        best_time = best_time_match.group(1).strip()

        results.append({
            "source": "Thrillophilia",
            "place": place_name,
            "country": country_match.group(1).strip() if country_match else "",
            "best_time_to_visit": best_time,
            "suggested_duration": duration_match.group(1).strip() if duration_match else "",
            "summer_match": mentions_target_months(best_time),
            "url": THRILLOPHILIA_EUROPE_URL,
        })

    return results


# ---------------------------------------------------------------------------
# 3. SAVE RESULTS
# ---------------------------------------------------------------------------

def save_lonely_planet_csv(rows, filename="lonely_planet_europe.csv"):
    if not rows:
        print("[LonelyPlanet] No data scraped — nothing to save.")
        return
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["source", "title", "url", "summary"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"[OK] Saved {len(rows)} Lonely Planet rows to {filename}")


def save_thrillophilia_csv(rows, filename="thrillophilia_europe_places.csv"):
    if not rows:
        print("[Thrillophilia] No data scraped — nothing to save.")
        return
    fieldnames = ["source", "place", "country", "best_time_to_visit",
                  "suggested_duration", "summer_match", "url"]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"[OK] Saved {len(rows)} Thrillophilia rows to {filename}")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Scraping Lonely Planet (article hub) ===")
    lp_results = scrape_lonely_planet()
    save_lonely_planet_csv(lp_results)

    print("\n=== Scraping Thrillophilia (places to visit in Europe) ===")
    th_results = scrape_thrillophilia()
    save_thrillophilia_csv(th_results)

    summer_places = [r for r in th_results if r["summer_match"]]
    print(f"\n{len(summer_places)} Thrillophilia places list June/July/August "
          f"as part of their best time to visit:")
    for p in summer_places:
        print(f"  - {p['place']} ({p['country']}): {p['best_time_to_visit']}")
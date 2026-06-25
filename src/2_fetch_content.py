"""
Content Fetcher (step 2)
========================
Reads all URLs from the CSVs produced by 1_crawl.py, fetches the full body
text of each page, and writes one JSON document per URL to

    data/raw_docs.jsonl

Each line is a self-contained document:
    {
        "id":      "<url>",
        "source":  "Lonely Planet" | "Thrillophilia",
        "title":   "...",
        "url":     "...",
        "text":    "<full cleaned body text>",
        "meta":    { ...any extra fields from the CSV row... }
    }

This file is the input to step 3 (chunk + embed + index).

Requirements:
    pip install requests beautifulsoup4 lxml
"""

import csv
import json
import os
import random
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
REQUEST_TIMEOUT = 20

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

OUTPUT_FILE = DATA_DIR / "raw_docs.jsonl"

# CSVs to pull URLs from (relative to repo root)
CSV_SOURCES = [
    ROOT / "lonely_planet_europe.csv",
    ROOT / "europe_travel_places.csv",
    ROOT / "thrillophilia_europe_places.csv",
]

# Skip URLs that are clearly not article/place pages
SKIP_URL_PATTERNS = [
    r"/tours/",          # Thrillophilia booking pages — thin content
    r"request_callback",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def polite_sleep(min_s: float = 1.5, max_s: float = 3.5) -> None:
    time.sleep(random.uniform(min_s, max_s))


def should_skip(url: str) -> bool:
    return any(re.search(p, url) for p in SKIP_URL_PATTERNS)


def fetch_html(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        print(f"  [!] {url}: {e}")
        return None


# ---------------------------------------------------------------------------
# Per-source content extractors
# ---------------------------------------------------------------------------

def _clean_and_extract(container: Tag) -> str:
    """Strip boilerplate tags then collect text from content tags."""
    for tag in container.find_all(["nav", "header", "footer", "aside", "script", "style"]):
        tag.decompose()
    paragraphs = container.find_all(["p", "h1", "h2", "h3", "h4", "li"])
    lines = [t.get_text(" ", strip=True) for t in paragraphs if t.get_text(strip=True)]
    return "\n\n".join(lines)


def extract_lonely_planet(soup: BeautifulSoup) -> str:
    """Pull the main article body from a Lonely Planet article page.

    LP renders article body in <div class="content-block ...">. Fall back to
    <main> if that class is absent (layout may change over time).
    """
    result = soup.find("div", class_="content-block")
    if not isinstance(result, Tag):
        result = soup.find("main")
    container: Tag = result if isinstance(result, Tag) else soup
    return _clean_and_extract(container)


def extract_thrillophilia(soup: BeautifulSoup) -> str:
    """Pull place/article content from a Thrillophilia page."""
    container: Tag | None = None
    for sel in ["div.content-section", "div.place-content", "div#main-content", "main", "article"]:
        found = soup.select_one(sel)
        if found is not None:
            container = found
            break
    if container is None:
        result = soup.find("body")
        container = result if isinstance(result, Tag) else soup
    return _clean_and_extract(container)


def extract_generic(soup: BeautifulSoup) -> str:
    """Generic extractor: grab all <p> and heading tags from <body>."""
    result = soup.find("body")
    container: Tag = result if isinstance(result, Tag) else soup
    for tag in container.find_all(["nav", "header", "footer", "aside", "script", "style"]):
        tag.decompose()
    paragraphs = container.find_all(["p", "h1", "h2", "h3", "h4"])
    lines = [t.get_text(" ", strip=True) for t in paragraphs if t.get_text(strip=True)]
    return "\n\n".join(lines)


EXTRACTORS = {
    "lonely planet": extract_lonely_planet,
    "thrillophilia": extract_thrillophilia,
}


def extract_text(source: str, html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    extractor = EXTRACTORS.get(source.lower().strip(), extract_generic)
    text = extractor(soup)
    # Collapse excessive whitespace / blank lines
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def get_page_title(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        return og_title["content"].strip()
    title_tag = soup.find("title")
    if title_tag:
        return title_tag.get_text(strip=True)
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return ""


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

def load_urls_from_csvs() -> list[dict]:
    """Return a deduplicated list of {url, source, title, meta} dicts."""
    seen: set[str] = set()
    docs: list[dict] = []

    for csv_path in CSV_SOURCES:
        if not csv_path.exists():
            print(f"[skip] {csv_path.name} not found")
            continue

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = (row.get("url") or "").strip()
                if not url or url in seen:
                    continue
                if should_skip(url):
                    continue
                seen.add(url)

                source = (row.get("source") or "").strip()
                title = (row.get("title") or row.get("place") or "").strip()
                meta = {k: v for k, v in row.items() if k not in ("url", "source", "title", "summary")}

                docs.append({"url": url, "source": source, "title": title, "meta": meta})

    print(f"[load] {len(docs)} unique URLs queued for fetching")
    return docs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def fetch_all(docs: list[dict]) -> None:
    # Load already-fetched URLs so we can resume without re-fetching
    already_done: set[str] = set()
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        already_done.add(json.loads(line)["id"])
                    except (json.JSONDecodeError, KeyError):
                        pass
        print(f"[resume] {len(already_done)} already fetched, skipping them")

    todo = [d for d in docs if d["url"] not in already_done]
    print(f"[fetch] {len(todo)} pages to fetch → {OUTPUT_FILE}")

    with open(OUTPUT_FILE, "a", encoding="utf-8") as out:
        for i, doc in enumerate(todo, 1):
            url = doc["url"]
            print(f"[{i}/{len(todo)}] {doc['source']} | {url}")

            html = fetch_html(url)
            if html is None:
                polite_sleep()
                continue

            text = extract_text(doc["source"], html)
            if not text:
                print("  [!] empty text extracted, skipping")
                polite_sleep()
                continue

            # Use page title if the CSV title was empty or a product listing
            title = doc["title"]
            if not title or len(title) > 200:
                title = get_page_title(html)

            record = {
                "id": url,
                "source": doc["source"],
                "title": title,
                "url": url,
                "text": text,
                "meta": doc["meta"],
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()

            polite_sleep()

    # Summary
    total = 0
    with open(OUTPUT_FILE, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                total += 1
    print(f"\n[done] {OUTPUT_FILE} contains {total} documents")


if __name__ == "__main__":
    all_docs = load_urls_from_csvs()
    fetch_all(all_docs)

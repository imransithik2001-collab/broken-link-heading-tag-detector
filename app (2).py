import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="Broken Link & Heading Tag Checker", layout="wide")

st.title("🔗 Broken Link & Heading Tag Checker")
st.write(
    "Enter one or more URLs (one per line). The tool will scan each page, "
    "count H1/H2/H3 heading tags separately, and check every link on the "
    "page for broken status."
)

# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------
urls_input = st.text_area(
    "Enter URL(s) — one per line",
    placeholder="https://example.com\nhttps://another-site.com/page",
    height=120,
)

col1, col2 = st.columns(2)
with col1:
    timeout = st.slider("Request timeout (seconds)", 3, 30, 10)
with col2:
    max_workers = st.slider("Parallel link checks", 1, 20, 8)

check_button = st.button("🚀 Run Check", type="primary")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LinkHeadingChecker/1.0)"
}


def fetch_page(url, timeout):
    """Fetch a page and return response object or raise."""
    return requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)


def count_headings(soup):
    return {
        "H1": len(soup.find_all("h1")),
        "H2": len(soup.find_all("h2")),
        "H3": len(soup.find_all("h3")),
    }


def extract_links(soup, base_url):
    links = set()
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith("#") or href.lower().startswith("javascript:") or href.lower().startswith("mailto:") or href.lower().startswith("tel:"):
            continue
        full_url = urljoin(base_url, href)
        links.add(full_url)
    return list(links)


def check_link_status(link, timeout):
    """Check a single link. Try HEAD first, fall back to GET (some servers block HEAD)."""
    try:
        r = requests.head(link, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code >= 400:

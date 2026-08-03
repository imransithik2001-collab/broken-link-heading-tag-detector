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
            # Some servers don't support HEAD properly — retry with GET
            r = requests.get(link, headers=HEADERS, timeout=timeout, allow_redirects=True, stream=True)
        return link, r.status_code, r.status_code >= 400
    except requests.exceptions.RequestException as e:
        return link, "ERROR", True


def process_url(source_url, timeout, max_workers):
    result = {
        "source_url": source_url,
        "error": None,
        "headings": {"H1": 0, "H2": 0, "H3": 0},
        "links_checked": 0,
        "broken_links": [],
        "all_links_status": [],
    }
    try:
        resp = fetch_page(source_url, timeout)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        result["error"] = str(e)
        return result

    soup = BeautifulSoup(resp.text, "html.parser")
    result["headings"] = count_headings(soup)

    links = extract_links(soup, source_url)
    result["links_checked"] = len(links)

    if links:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(check_link_status, link, timeout) for link in links]
            for future in as_completed(futures):
                link, status, is_broken = future.result()
                result["all_links_status"].append((link, status, is_broken))
                if is_broken:
                    result["broken_links"].append((link, status))

    return result


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if check_button:
    raw_urls = [u.strip() for u in urls_input.splitlines() if u.strip()]

    if not raw_urls:
        st.warning("Please enter at least one URL.")
    else:
        overall_summary = []

        for source_url in raw_urls:
            with st.spinner(f"Scanning {source_url} ..."):
                result = process_url(source_url, timeout, max_workers)

            st.markdown("---")
            st.subheader(f"📄 {source_url}")

            if result["error"]:
                st.error(f"Could not fetch this page: {result['error']}")
                overall_summary.append({
                    "URL": source_url,
                    "H1": "-", "H2": "-", "H3": "-",
                    "Links Checked": "-", "Broken Links": "-",
                    "Status": "Fetch Failed",
                })
                continue

            h = result["headings"]

            # Heading counts
            hc1, hc2, hc3 = st.columns(3)
            hc1.metric("H1 tags", h["H1"])
            hc2.metric("H2 tags", h["H2"])
            hc3.metric("H3 tags", h["H3"])

            # Broken link summary
            broken_count = len(result["broken_links"])
            st.write(
                f"**Links found:** {result['links_checked']}  |  "
                f"**Broken links:** {broken_count}"
            )

            if broken_count > 0:
                st.error(f"⚠️ {broken_count} broken link(s) found")
                broken_df = pd.DataFrame(result["broken_links"], columns=["Broken Link", "Status Code"])
                st.dataframe(broken_df, use_container_width=True)
            else:
                st.success("✅ No broken links found")

            with st.expander("View all checked links & status"):
                all_df = pd.DataFrame(result["all_links_status"], columns=["Link", "Status Code", "Broken"])
                st.dataframe(all_df, use_container_width=True)

            overall_summary.append({
                "URL": source_url,
                "H1": h["H1"], "H2": h["H2"], "H3": h["H3"],
                "Links Checked": result["links_checked"],
                "Broken Links": broken_count,
                "Status": "OK",
            })

        st.markdown("---")
        st.subheader("📊 Summary — All URLs")
        summary_df = pd.DataFrame(overall_summary)
        st.dataframe(summary_df, use_container_width=True)

        csv = summary_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download Summary as CSV",
            data=csv,
            file_name="link_heading_summary.csv",
            mime="text/csv",
        )

else:
    st.info("Enter URL(s) above and click **Run Check** to start.")

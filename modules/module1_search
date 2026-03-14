"""
MODULE 1 — Serper Search + Provider Discovery
"""
import requests
import streamlit as st
from urllib.parse import urlparse
import time


EXCLUDE_DOMAINS = {
    "reddit.com", "quora.com", "linkedin.com", "youtube.com",
    "facebook.com", "twitter.com", "instagram.com", "glassdoor.com",
    "indeed.com", "naukri.com", "timesjobs.com", "wikipedia.org",
    "pmi.org", "amazon.com", "flipkart.com", "trustpilot.com",
}

MARKETPLACE_DOMAINS = {
    "udemy.com", "coursera.org", "edx.org", "pluralsight.com",
    "skillshare.com", "alison.com",
}


def build_search_queries(location: str) -> list:
    return [
        f"PMP certification training {location}",
        f"PMP course {location} 2025",
        f"project management professional training {location}",
        f"PMI authorized training provider {location}",
        f"PMP exam preparation course {location}",
        f"PMP training online {location}",
    ]


def get_root_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        parts = parsed.netloc.replace("www.", "").split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else parsed.netloc
    except Exception:
        return ""


def classify_provider(url: str) -> str:
    domain = get_root_domain(url)
    if domain in EXCLUDE_DOMAINS:
        return "exclude"
    if domain in MARKETPLACE_DOMAINS:
        return "marketplace"
    return "direct_provider"


def search_serper(query: str, api_key: str, num_results: int = 10) -> dict:
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    payload = {"q": query, "num": num_results, "hl": "en"}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.warning(f"Serper error for '{query}': {e}")
        return {}


def parse_serper_results(raw: dict) -> list:
    providers = []
    for item in raw.get("organic", []):
        providers.append({
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": item.get("snippet", ""),
            "source_type": "organic",
            "position": item.get("position", 99),
        })
    for item in raw.get("ads", []):
        providers.append({
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": item.get("snippet", ""),
            "source_type": "ad",
            "position": 0,
        })
    for item in raw.get("places", []):
        providers.append({
            "title": item.get("title", ""),
            "url": item.get("website", ""),
            "snippet": item.get("address", ""),
            "source_type": "local",
            "position": item.get("position", 99),
            "rating": item.get("rating"),
            "reviews": item.get("ratingCount"),
        })
    return providers


def deduplicate_providers(all_providers: list) -> list:
    seen_domains = {}
    priority_map = {"ad": 0, "local": 1, "organic": 2}
    for p in all_providers:
        if not p.get("url"):
            continue
        domain = get_root_domain(p["url"])
        if not domain:
            continue
        p["domain"] = domain
        p["provider_type"] = classify_provider(p["url"])
        if p["provider_type"] == "exclude":
            continue
        if domain not in seen_domains:
            seen_domains[domain] = p
        else:
            existing_pri = priority_map.get(seen_domains[domain].get("source_type", "organic"), 2)
            new_pri = priority_map.get(p.get("source_type", "organic"), 2)
            if new_pri < existing_pri:
                seen_domains[domain] = p
    return list(seen_domains.values())


def discover_providers(location: str, api_key: str, max_queries: int = 4) -> list:
    queries = build_search_queries(location)[:max_queries]
    all_providers = []
    progress = st.progress(0, text=f"Searching for PMP providers in {location}...")
    for i, query in enumerate(queries):
        progress.progress((i + 1) / len(queries), text=f"Query {i+1}/{len(queries)}: {query}")
        raw = search_serper(query, api_key)
        providers = parse_serper_results(raw)
        all_providers.extend(providers)
        time.sleep(0.3)
    progress.empty()
    deduped = deduplicate_providers(all_providers)
    priority_map = {"ad": 0, "local": 1, "organic": 2}
    deduped.sort(key=lambda x: priority_map.get(x.get("source_type", "organic"), 2))
    return deduped


def render_module1():
    st.title("Module 1 — Provider Discovery")
    st.caption("Discovers PMP training providers in any location via Google Search")

    api_key = st.secrets.get("search", {}).get("SERPER_API_KEY", "")
    if not api_key:
        st.error("SERPER_API_KEY missing from secrets.toml")
        return

    col1, col2 = st.columns([3, 1])
    with col1:
        location = st.text_input("Location", placeholder="e.g. Dubai, UAE · Singapore · London · Mumbai", label_visibility="collapsed")
    with col2:
        clicked = st.button("Search", type="primary", use_container_width=True)

    if clicked and location:
        providers = discover_providers(location, api_key)
        if not providers:
            st.warning("No providers found. Try a broader location.")
            return

        st.session_state["discovered_providers"] = providers
        st.session_state["search_location"] = location

        direct = [p for p in providers if p["provider_type"] == "direct_provider"]
        marketplaces = [p for p in providers if p["provider_type"] == "marketplace"]

        m1, m2, m3 = st.columns(3)
        m1.metric("Total found", len(providers))
        m2.metric("Direct providers", len(direct))
        m3.metric("Marketplaces", len(marketplaces))

        st.divider()
        for p in providers:
            badge = {"ad": "Ad", "local": "Local", "organic": "Organic"}.get(p.get("source_type"), "")
            with st.expander(f"{p['title']} — {p.get('domain', '')}  [{badge}]"):
                st.markdown(f"**URL:** [{p['url']}]({p['url']})")
                st.markdown(f"**Snippet:** {p.get('snippet', 'N/A')}")
                if p.get("rating"):
                    st.markdown(f"**Rating:** {p['rating']} ⭐ ({p.get('reviews', '?')} reviews)")

        st.success(f"Found {len(providers)} providers. Proceed to Module 2.")
    elif clicked:
        st.warning("Please enter a location.")


if __name__ == "__main__":
    render_module1()

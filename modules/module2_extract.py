"""
MODULE 2 — Scraping (Firecrawl → Apify → BeautifulSoup) + DeepSeek Price Extraction
"""
import streamlit as st
import requests
import json
import re
import time
from dataclasses import dataclass, asdict, field
from typing import Optional
from html.parser import HTMLParser


@dataclass
class CourseData:
    provider_name: str
    url: str
    domain: str
    price: Optional[float] = None
    currency: Optional[str] = None
    price_usd: Optional[float] = None
    price_display: Optional[float] = None
    display_currency: Optional[str] = None
    raw_price_text: Optional[str] = None
    delivery_mode: Optional[str] = None
    duration_days: Optional[int] = None
    pdu_hours: Optional[int] = None
    exam_voucher_included: Optional[bool] = None
    next_date: Optional[str] = None
    rating: Optional[float] = None
    reviews: Optional[int] = None
    is_atp: bool = False
    extraction_status: str = "pending"


EXTRACTION_PROMPT = """You are a data extractor for a PMP training price comparison tool.

Given the page content below, extract PMP certification course details.
Return ONLY a valid JSON object. Use null for fields you cannot find with confidence.

{
  "provider_name": "company or brand name",
  "price": numeric price only (no symbols) or null,
  "currency": "3-letter ISO code e.g. USD AED INR GBP SGD AUD" or null,
  "raw_price_text": "exact price text shown e.g. $1499 or AED 3500" or null,
  "delivery_mode": "online_live OR self_paced OR classroom OR blended" or null,
  "duration_days": number or null,
  "pdu_hours": number or null,
  "exam_voucher_included": true or false or null,
  "next_date": "YYYY-MM-DD" or null,
  "is_atp": true or false
}

Rules:
- If multiple prices exist, return the LOWEST for the standard PMP course
- Return ONLY the JSON — no explanation, no markdown fences

PAGE CONTENT:
{page_content}
"""


def firecrawl_scrape(url: str, api_key: str) -> Optional[str]:
    if not api_key:
        return None
    endpoint = "https://api.firecrawl.dev/v1/scrape"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"url": url, "formats": ["markdown"], "onlyMainContent": True, "waitFor": 2000}
    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        if data.get("success") and data.get("data", {}).get("markdown"):
            return data["data"]["markdown"][:8000]
        return None
    except requests.exceptions.RequestException:
        return None


def apify_scrape(url: str, api_key: str) -> Optional[str]:
    if not api_key:
        return None
    endpoint = "https://api.apify.com/v2/acts/apify~website-content-crawler/run-sync-get-dataset-items"
    params = {"token": api_key}
    payload = {
        "startUrls": [{"url": url}],
        "maxCrawlPages": 1,
        "crawlerType": "cheerio",
    }
    try:
        response = requests.post(endpoint, params=params, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        if data and len(data) > 0:
            text = data[0].get("text") or data[0].get("markdown") or ""
            return text[:8000] if text else None
        return None
    except requests.exceptions.RequestException:
        return None


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        self._skip = tag in ("script", "style", "noscript")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            text = data.strip()
            if text:
                self._parts.append(text)

    def get_text(self):
        return "\n".join(self._parts)


def free_scrape(url: str) -> Optional[str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    }
    try:
        response = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
        response.raise_for_status()
        parser = _TextExtractor()
        parser.feed(response.text)
        text = parser.get_text()
        return text[:8000] if text else None
    except requests.exceptions.RequestException:
        return None


def scrape_url(url: str, firecrawl_key: str, apify_key: str) -> Optional[str]:
    """Try Firecrawl first, then Apify, then free scraping."""
    markdown = firecrawl_scrape(url, firecrawl_key)
    if markdown:
        return markdown

    markdown = apify_scrape(url, apify_key)
    if markdown:
        return markdown

    return free_scrape(url)


def extract_with_llm(markdown: str, url: str, api_key: str) -> Optional[dict]:
    prompt = EXTRACTION_PROMPT.replace("{page_content}", markdown)
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek/deepseek-chat-v3-0324",
                "max_tokens": 512,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        raw = data["choices"][0]["message"]["content"].strip()
        # Strip markdown code fences
        if "```" in raw:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
            if match:
                raw = match.group(1)
        # Find the JSON object even if surrounded by extra text
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if not json_match:
            st.warning(f"No JSON found in LLM response for {url}")
            return None
        raw = json_match.group(0)
        # Fix common issues: single quotes, trailing commas, comments
        raw = re.sub(r"//.*?$", "", raw, flags=re.MULTILINE)  # remove line comments
        raw = re.sub(r",\s*([}\]])", r"\1", raw)  # remove trailing commas
        return json.loads(raw)
    except json.JSONDecodeError as e:
        st.warning(f"JSON parse error for {url}: {e}")
        return None
    except Exception as e:
        st.warning(f"LLM error for {url}: {e}")
        return None


def build_course_data(provider: dict, extracted: Optional[dict]) -> CourseData:
    if not extracted:
        return CourseData(
            provider_name=provider.get("title", provider.get("domain", "Unknown")),
            url=provider.get("url", ""),
            domain=provider.get("domain", ""),
            rating=provider.get("rating"),
            reviews=provider.get("reviews"),
            extraction_status="failed",
        )
    has_price = extracted.get("price") is not None
    has_mode = extracted.get("delivery_mode") is not None
    status = "success" if (has_price and has_mode) else ("partial" if has_price else "failed")
    return CourseData(
        provider_name=extracted.get("provider_name") or provider.get("title", "Unknown"),
        url=provider.get("url", ""),
        domain=provider.get("domain", ""),
        price=extracted.get("price"),
        currency=extracted.get("currency"),
        raw_price_text=extracted.get("raw_price_text"),
        delivery_mode=extracted.get("delivery_mode"),
        duration_days=extracted.get("duration_days"),
        pdu_hours=extracted.get("pdu_hours"),
        exam_voucher_included=extracted.get("exam_voucher_included"),
        next_date=extracted.get("next_date"),
        is_atp=extracted.get("is_atp", False),
        rating=provider.get("rating"),
        reviews=provider.get("reviews"),
        extraction_status=status,
    )


def extract_all_providers(providers: list, firecrawl_key: str, llm_key: str, max_providers: int = 15, apify_key: str = "") -> list:
    results = []
    to_process = providers[:max_providers]
    progress = st.progress(0, text="Starting extraction...")
    status_box = st.empty()

    for i, provider in enumerate(to_process):
        url = provider.get("url", "")
        name = provider.get("title", provider.get("domain", "Unknown"))
        progress.progress((i + 1) / len(to_process), text=f"Extracting {i+1}/{len(to_process)}: {name}")
        status_box.caption(f"Scraping → {url[:70]}...")

        markdown = scrape_url(url, firecrawl_key, apify_key)
        if not markdown:
            results.append(build_course_data(provider, None))
            time.sleep(0.3)
            continue

        extracted = extract_with_llm(markdown, url, llm_key)
        results.append(build_course_data(provider, extracted))
        time.sleep(0.4)

    progress.empty()
    status_box.empty()
    results.sort(key=lambda x: (
        0 if x.extraction_status == "success" else
        1 if x.extraction_status == "partial" else 2,
        x.price or 999999
    ))
    return results


def render_module2():
    st.title("Module 2 — Price Extraction")
    st.caption("Crawls each provider page and extracts structured price data via DeepSeek")

    firecrawl_key = st.secrets.get("scraping", {}).get("FIRECRAWL_API_KEY", "")
    apify_key = st.secrets.get("scraping", {}).get("APIFY_API_KEY", "")
    llm_key = st.secrets.get("llm", {}).get("OPENROUTER_API_KEY", "")

    if not llm_key:
        st.error("OPENROUTER_API_KEY missing from secrets.toml")
        return

    providers = st.session_state.get("discovered_providers", [])
    location = st.session_state.get("search_location", "")

    if not providers:
        st.info("Run Module 1 first to discover providers.")
        return

    st.info(f"{len(providers)} providers found in **{location}**")
    max_p = st.slider("Max providers to extract (conserves Firecrawl credits)", 5, min(20, len(providers)), 10)

    if st.button("Extract Prices", type="primary"):
        courses = extract_all_providers(providers, firecrawl_key, llm_key, max_providers=max_p, apify_key=apify_key)
        st.session_state["extracted_courses"] = [asdict(c) for c in courses]

        successful = sum(1 for c in courses if c.extraction_status == "success")
        partial = sum(1 for c in courses if c.extraction_status == "partial")
        failed = sum(1 for c in courses if c.extraction_status == "failed")
        with_price = sum(1 for c in courses if c.price is not None)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Success", successful)
        m2.metric("Partial", partial)
        m3.metric("Failed", failed)
        m4.metric("With price", with_price)

        st.divider()
        for c in courses:
            if c.extraction_status == "failed":
                continue
            icon = "✅" if c.extraction_status == "success" else "⚠️"
            label = c.raw_price_text or "Price not found"
            with st.expander(f"{icon} {c.provider_name} — {label}"):
                col1, col2, col3 = st.columns(3)
                col1.markdown(f"**Price:** {c.raw_price_text or 'N/A'}")
                col1.markdown(f"**Currency:** {c.currency or 'N/A'}")
                col2.markdown(f"**Delivery:** {c.delivery_mode or 'N/A'}")
                col2.markdown(f"**Duration:** {str(c.duration_days) + 'd' if c.duration_days else 'N/A'}")
                col3.markdown(f"**PDU hrs:** {c.pdu_hours or 'N/A'}")
                col3.markdown(f"**Voucher:** {'Yes ✅' if c.exam_voucher_included else ('No' if c.exam_voucher_included is False else '?')}")
                if c.is_atp:
                    st.success("PMI Authorized Training Partner")
                st.caption(f"[{c.url}]({c.url})")

        st.success(f"Done. {with_price} providers with prices ready for Module 3.")


if __name__ == "__main__":
    render_module2()

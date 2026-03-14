"""
MODULE 4 — Supabase Caching Layer
Cache search results for 24h. On repeat searches serve from DB, skip the scrape pipeline.
"""
import streamlit as st
from datetime import datetime, timedelta, timezone

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False


SCHEMA_SQL = """
-- Run this ONCE in your Supabase Dashboard → SQL Editor

CREATE TABLE IF NOT EXISTS pmp_search_cache (
    id              BIGSERIAL PRIMARY KEY,
    location_slug   TEXT NOT NULL,
    location_raw    TEXT NOT NULL,
    searched_at     TIMESTAMPTZ DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,
    provider_count  INT,
    results_json    JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pmp_cache_slug    ON pmp_search_cache (location_slug);
CREATE INDEX IF NOT EXISTS idx_pmp_cache_expires ON pmp_search_cache (expires_at);

CREATE TABLE IF NOT EXISTS pmp_price_history (
    id              BIGSERIAL PRIMARY KEY,
    domain          TEXT NOT NULL,
    provider_name   TEXT,
    location_slug   TEXT NOT NULL,
    price_usd       NUMERIC,
    currency        TEXT,
    price_raw       NUMERIC,
    raw_price_text  TEXT,
    delivery_mode   TEXT,
    is_atp          BOOLEAN DEFAULT FALSE,
    exam_voucher    BOOLEAN,
    recorded_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_history_domain ON pmp_price_history (domain, location_slug);
"""


@st.cache_resource
def get_supabase_client():
    if not SUPABASE_AVAILABLE:
        return None
    try:
        url = st.secrets["database"]["SUPABASE_URL"]
        key = st.secrets["database"]["SUPABASE_SERVICE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.warning(f"Supabase connection failed: {e}")
        return None


def normalise_location(location: str) -> str:
    return location.lower().strip().replace(",", "").replace("  ", " ").replace(" ", "-")


def get_cached_results(location: str):
    supabase = get_supabase_client()
    if not supabase:
        return None
    try:
        slug = normalise_location(location)
        now_iso = datetime.now(timezone.utc).isoformat()
        response = (
            supabase.table("pmp_search_cache")
            .select("results_json, searched_at, provider_count")
            .eq("location_slug", slug)
            .gt("expires_at", now_iso)
            .order("searched_at", desc=True)
            .limit(1)
            .execute()
        )
        if response.data:
            row = response.data[0]
            st.info(f"Cache hit — {row['provider_count']} providers from {row['searched_at'][:10]}")
            return row["results_json"]
        return None
    except Exception as e:
        st.warning(f"Cache read error: {e}")
        return None


def save_to_cache(location: str, courses: list) -> bool:
    supabase = get_supabase_client()
    if not supabase:
        return False
    try:
        slug = normalise_location(location)
        now = datetime.now(timezone.utc)
        expires = (now + timedelta(hours=24)).isoformat()

        supabase.table("pmp_search_cache").insert({
            "location_slug": slug,
            "location_raw": location,
            "searched_at": now.isoformat(),
            "expires_at": expires,
            "provider_count": len(courses),
            "results_json": courses,
        }).execute()

        history_rows = []
        for c in courses:
            if not c.get("price_usd") and not c.get("price"):
                continue
            history_rows.append({
                "domain": c.get("domain", ""),
                "provider_name": c.get("provider_name", ""),
                "location_slug": slug,
                "price_usd": c.get("price_usd"),
                "currency": c.get("currency"),
                "price_raw": c.get("price"),
                "raw_price_text": c.get("raw_price_text"),
                "delivery_mode": c.get("delivery_mode"),
                "is_atp": c.get("is_atp", False),
                "exam_voucher": c.get("exam_voucher_included"),
                "recorded_at": now.isoformat(),
            })
        if history_rows:
            supabase.table("pmp_price_history").insert(history_rows).execute()

        return True
    except Exception as e:
        st.warning(f"Cache write error: {e}")
        return False


def get_recent_searches(limit: int = 10) -> list:
    supabase = get_supabase_client()
    if not supabase:
        return []
    try:
        response = (
            supabase.table("pmp_search_cache")
            .select("location_raw, searched_at, provider_count")
            .order("searched_at", desc=True)
            .limit(limit * 3)
            .execute()
        )
        seen = set()
        unique = []
        for row in (response.data or []):
            loc = row["location_raw"]
            if loc not in seen:
                seen.add(loc)
                unique.append(row)
                if len(unique) >= limit:
                    break
        return unique
    except Exception:
        return []


def render_module4():
    st.title("Module 4 — Supabase Cache")
    st.caption("Saves search results for 24h — skips re-scraping on repeat searches")

    if not SUPABASE_AVAILABLE:
        st.error("supabase package not installed. Run: pip install supabase")
        return

    try:
        _ = st.secrets["database"]["SUPABASE_URL"]
        _ = st.secrets["database"]["SUPABASE_SERVICE_KEY"]
    except KeyError:
        st.error("Supabase keys missing from secrets.toml")
        st.code('[database]\nSUPABASE_URL = "https://xxxx.supabase.co"\nSUPABASE_SERVICE_KEY = "eyJ..."', language="toml")
        return

    with st.expander("First-time setup — run this SQL in Supabase Dashboard → SQL Editor"):
        st.code(SCHEMA_SQL, language="sql")

    st.divider()

    enriched = st.session_state.get("enriched_courses", [])
    location = st.session_state.get("search_location", "")

    if enriched and location:
        st.subheader("Save current results")
        st.write(f"**{len(enriched)}** providers for **{location}**")
        if st.button("Save to Supabase", type="primary"):
            with st.spinner("Saving..."):
                ok = save_to_cache(location, enriched)
            if ok:
                st.success(f"Saved {len(enriched)} providers. Cache valid 24h.")
            else:
                st.error("Save failed. Check connection and table schema.")
    else:
        st.info("Run Modules 1–3 first, then save results here.")

    st.divider()
    st.subheader("Test cache lookup")
    test_loc = st.text_input("Location to check", placeholder="e.g. Dubai, UAE")
    if st.button("Check cache") and test_loc:
        cached = get_cached_results(test_loc)
        if cached:
            st.success(f"Found {len(cached)} cached providers for '{test_loc}'")
            if st.button("Load into session"):
                st.session_state["extracted_courses"] = cached
                st.session_state["search_location"] = test_loc
                st.success("Loaded. Go to Module 3 to view.")
        else:
            st.warning(f"No valid cache for '{test_loc}'.")

    st.divider()
    st.subheader("Recent searches")
    recent = get_recent_searches()
    if recent:
        for row in recent:
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.write(row["location_raw"])
            c2.caption(row["searched_at"][:10])
            c3.caption(f"{row['provider_count']} providers")
    else:
        st.caption("No searches saved yet.")


if __name__ == "__main__":
    render_module4()

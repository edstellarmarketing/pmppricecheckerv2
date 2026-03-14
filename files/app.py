"""
PMP Training Price Comparison App
Run: streamlit run app.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from dataclasses import asdict

from modules.module1_search import render_module1, discover_providers
from modules.module2_extract import render_module2, extract_all_providers
from modules.module3_forex import (
    render_module3, fetch_exchange_rates,
    build_comparison_df, convert_price, format_price,
    enrich_with_forex, CURRENCY_OPTIONS
)
from modules.module4_cache import render_module4, get_cached_results, save_to_cache, get_recent_searches

st.set_page_config(
    page_title="PMP Training Price Finder",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar ──
with st.sidebar:
    st.markdown("### 📊 PMP Price Finder")
    st.caption("Real-time comparison across providers worldwide")
    st.divider()

    page = st.radio(
        "Navigate",
        ["🔍 Search & Compare", "⚙️ Module 1 — Discovery",
         "💰 Module 2 — Extraction", "💱 Module 3 — Currency",
         "🗄️ Module 4 — Cache"],
        label_visibility="collapsed",
    )

    st.divider()
    loc = st.session_state.get("search_location")
    providers = st.session_state.get("discovered_providers", [])
    courses = st.session_state.get("extracted_courses", [])
    priced = [c for c in courses if c.get("price")]

    if loc:
        st.caption(f"Location: **{loc}**")
    if providers:
        st.caption(f"Providers found: **{len(providers)}**")
    if priced:
        st.caption(f"With prices: **{len(priced)}**")

    st.divider()
    st.caption("Serper · Firecrawl · DeepSeek · Supabase")


# ── Check required keys ──
def check_keys():
    missing = []
    for section, key in [
        ("search", "SERPER_API_KEY"),
        ("llm", "OPENROUTER_API_KEY"),
        ("forex", "EXCHANGERATE_API_KEY"),
    ]:
        try:
            _ = st.secrets[section][key]
        except Exception:
            missing.append(f"{section}.{key}")
    return missing


# ════════════════════════════════════════════
# MAIN PAGE — Search & Compare
# ════════════════════════════════════════════
if page == "🔍 Search & Compare":
    st.title("PMP Training Price Comparison")
    st.markdown("Find and compare PMP certification training prices from providers anywhere in the world.")

    missing = check_keys()
    if missing:
        st.error(f"Missing API keys in secrets.toml: `{'`, `'.join(missing)}`")
        st.stop()

    # ── Recent searches quick-access ──
    recent = get_recent_searches(limit=6)
    if recent:
        st.caption("Recent:")
        cols = st.columns(min(len(recent), 6))
        for i, row in enumerate(recent[:6]):
            if cols[i].button(row["location_raw"], key=f"rec_{i}", use_container_width=True):
                st.session_state["_quick_loc"] = row["location_raw"]
                st.rerun()

    # ── Search inputs ──
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        default_loc = st.session_state.pop("_quick_loc", "")
        location = st.text_input(
            "Location",
            value=default_loc,
            placeholder="e.g. Dubai, UAE  ·  Singapore  ·  London  ·  Mumbai  ·  New York",
            label_visibility="collapsed",
        )
    with col2:
        currency_label = st.selectbox("Currency", list(CURRENCY_OPTIONS.keys()), label_visibility="collapsed")
        display_currency = CURRENCY_OPTIONS[currency_label]
    with col3:
        search_btn = st.button("Search providers", type="primary", use_container_width=True)

    # ── Run pipeline ──
    if search_btn and location:
        # Step 0: cache check
        with st.spinner("Checking cache..."):
            cached = get_cached_results(location)

        if cached:
            st.session_state["extracted_courses"] = cached
            st.session_state["search_location"] = location
        else:
            # Step 1: Discover
            st.markdown("**Step 1 / 3 — Discovering providers...**")
            providers = discover_providers(
                location,
                st.secrets["search"]["SERPER_API_KEY"],
                max_queries=4,
            )
            st.session_state["discovered_providers"] = providers
            st.session_state["search_location"] = location

            if not providers:
                st.warning("No providers found. Try a broader location.")
                st.stop()
            st.success(f"Found {len(providers)} providers.")

            # Step 2: Extract
            st.markdown("**Step 2 / 3 — Extracting prices...**")
            courses_obj = extract_all_providers(
                providers,
                st.secrets.get("scraping", {}).get("FIRECRAWL_API_KEY", ""),
                st.secrets["llm"]["OPENROUTER_API_KEY"],
                max_providers=12,
                apify_key=st.secrets.get("scraping", {}).get("APIFY_API_KEY", ""),
            )
            courses = [asdict(c) for c in courses_obj]
            st.session_state["extracted_courses"] = courses
            priced_count = sum(1 for c in courses if c.get("price"))
            st.success(f"Extracted prices from {priced_count} providers.")

            # Step 3: Save to cache (non-fatal)
            try:
                enriched = enrich_with_forex(courses, st.secrets["forex"]["EXCHANGERATE_API_KEY"], display_currency)
                save_to_cache(location, enriched)
            except Exception:
                pass

    elif search_btn and not location:
        st.warning("Please enter a city or country.")

    # ── Display results ──
    courses = st.session_state.get("extracted_courses", [])
    priced = [c for c in courses if c.get("price") is not None]

    if priced:
        forex_key = st.secrets["forex"]["EXCHANGERATE_API_KEY"]
        rates = fetch_exchange_rates(forex_key)

        if not rates:
            st.error("Could not load exchange rates.")
            st.stop()

        prices_usd = [convert_price(c["price"], c.get("currency", "USD"), "USD", rates) for c in priced]
        prices_usd = [p for p in prices_usd if p]

        if prices_usd:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Providers", len(priced))
            m2.metric("Lowest", format_price(min(prices_usd), "USD"))
            m3.metric("Highest", format_price(max(prices_usd), "USD"))
            m4.metric("Average", format_price(sum(prices_usd) / len(prices_usd), "USD"))

        st.divider()

        # Filters
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            mode_filter = st.multiselect("Delivery mode", ["Online live", "Self-paced", "Classroom", "Blended"])
        with fc2:
            atp_only = st.checkbox("ATP providers only")
        with fc3:
            voucher_only = st.checkbox("Exam voucher included only")

        df = build_comparison_df(priced, rates, display_currency)

        if mode_filter:
            df = df[df["Delivery"].isin(mode_filter)]
        if atp_only:
            df = df[df["ATP"] == "✅"]
        if voucher_only:
            df = df[df["Voucher"] == "Yes ✅"]

        if df.empty:
            st.warning("No results match your filters.")
        else:
            loc_display = st.session_state.get("search_location", "")
            st.subheader(f"PMP training in {loc_display}")

            display_cols = ["Provider", f"Price ({display_currency})", "Price (USD)",
                            "Delivery", "Duration", "PDU hrs", "Voucher", "ATP", "Rating", "Course Page"]
            # Remove duplicate when display currency is USD
            display_cols = list(dict.fromkeys(display_cols))
            display_cols = [c for c in display_cols if c in df.columns]

            st.dataframe(
                df[display_cols],
                use_container_width=True,
                column_config={
                    "Provider": st.column_config.TextColumn(width="large"),
                    "Course Page": st.column_config.LinkColumn(display_text="View"),
                },
            )

            csv = df[display_cols].to_csv(index=False)
            fname = f"pmp_prices_{loc_display.replace(',','').replace(' ','_').lower()}.csv"
            st.download_button("Download CSV", csv, file_name=fname, mime="text/csv")

# ── Module pages ──
elif page == "⚙️ Module 1 — Discovery":
    render_module1()
elif page == "💰 Module 2 — Extraction":
    render_module2()
elif page == "💱 Module 3 — Currency":
    render_module3()
elif page == "🗄️ Module 4 — Cache":
    render_module4()

"""
MODULE 3 — Currency Conversion + Comparison Table
"""
import requests
import streamlit as st
import pandas as pd
from typing import Optional
from datetime import datetime


CURRENCY_OPTIONS = {
    "USD — US Dollar": "USD",
    "AED — UAE Dirham": "AED",
    "INR — Indian Rupee": "INR",
    "GBP — British Pound": "GBP",
    "EUR — Euro": "EUR",
    "SGD — Singapore Dollar": "SGD",
    "AUD — Australian Dollar": "AUD",
    "CAD — Canadian Dollar": "CAD",
    "MYR — Malaysian Ringgit": "MYR",
    "SAR — Saudi Riyal": "SAR",
    "QAR — Qatari Riyal": "QAR",
    "ZAR — South African Rand": "ZAR",
    "JPY — Japanese Yen": "JPY",
}

CURRENCY_SYMBOLS = {
    "USD": "$", "AED": "AED ", "INR": "₹", "GBP": "£",
    "EUR": "€", "SGD": "S$", "AUD": "A$", "CAD": "C$",
    "MYR": "RM ", "SAR": "SAR ", "QAR": "QAR ", "ZAR": "R ",
    "JPY": "¥",
}

DELIVERY_LABELS = {
    "online_live": "Online live",
    "self_paced": "Self-paced",
    "classroom": "Classroom",
    "blended": "Blended",
}


@st.cache_data(ttl=3600)
def fetch_exchange_rates(api_key: str, base: str = "USD") -> dict:
    url = f"https://v6.exchangerate-api.com/v6/{api_key}/latest/{base}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("result") == "success":
            return data.get("conversion_rates", {})
        st.warning(f"ExchangeRate-API error: {data.get('error-type', 'unknown')}")
        return {}
    except Exception as e:
        st.warning(f"Forex fetch failed: {e}")
        return {}


def convert_price(price: float, from_currency: str, to_currency: str, rates: dict) -> Optional[float]:
    if not price or not from_currency or not rates:
        return None
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()
    if from_currency == to_currency:
        return round(price, 2)
    price_usd = price if from_currency == "USD" else (price / rates[from_currency] if from_currency in rates else None)
    if price_usd is None:
        return None
    if to_currency == "USD":
        return round(price_usd, 2)
    return round(price_usd * rates[to_currency], 2) if to_currency in rates else None


def format_price(amount: Optional[float], currency: str) -> str:
    if amount is None:
        return "N/A"
    symbol = CURRENCY_SYMBOLS.get(currency, f"{currency} ")
    if currency in ("JPY", "INR", "NGN"):
        return f"{symbol}{amount:,.0f}"
    return f"{symbol}{amount:,.2f}"


def build_comparison_df(courses: list, rates: dict, display_currency: str) -> pd.DataFrame:
    rows = []
    for c in courses:
        if c.get("price") is None:
            continue
        price_usd = convert_price(c["price"], c.get("currency", "USD"), "USD", rates)
        price_disp = convert_price(c["price"], c.get("currency", "USD"), display_currency, rates)
        rows.append({
            "Provider": c.get("provider_name", "Unknown"),
            f"Price ({display_currency})": format_price(price_disp, display_currency),
            "Price (USD)": format_price(price_usd, "USD"),
            "Original": c.get("raw_price_text", "N/A"),
            "Delivery": DELIVERY_LABELS.get(c.get("delivery_mode"), c.get("delivery_mode") or "N/A"),
            "Duration": f"{c['duration_days']}d" if c.get("duration_days") else "N/A",
            "PDU hrs": c.get("pdu_hours") or "N/A",
            "Voucher": "Yes ✅" if c.get("exam_voucher_included") else ("No" if c.get("exam_voucher_included") is False else "?"),
            "ATP": "✅" if c.get("is_atp") else "—",
            "Rating": f"{c['rating']} ⭐" if c.get("rating") else "N/A",
            "URL": c.get("url", ""),
            "_sort": price_usd or 999999,
        })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)
    df.index += 1
    return df


def enrich_with_forex(courses: list, api_key: str, display_currency: str = "USD") -> list:
    rates = fetch_exchange_rates(api_key)
    if not rates:
        return courses
    for c in courses:
        if c.get("price") and c.get("currency"):
            c["price_usd"] = convert_price(c["price"], c["currency"], "USD", rates)
            c["price_display"] = convert_price(c["price"], c["currency"], display_currency, rates)
            c["display_currency"] = display_currency
    return courses


def render_module3():
    st.title("Module 3 — Price Comparison")
    st.caption("Currency-normalised comparison table across all discovered providers")

    forex_key = st.secrets.get("forex", {}).get("EXCHANGERATE_API_KEY", "")
    if not forex_key:
        st.error("EXCHANGERATE_API_KEY missing from secrets.toml")
        return

    courses = st.session_state.get("extracted_courses", [])
    location = st.session_state.get("search_location", "your location")

    if not courses:
        st.info("Run Modules 1 and 2 first.")
        return

    priced = [c for c in courses if c.get("price") is not None]
    if not priced:
        st.warning("No prices extracted yet. Run Module 2.")
        return

    col1, col2, col3 = st.columns([2, 2, 2])
    with col1:
        currency_label = st.selectbox("Display currency", list(CURRENCY_OPTIONS.keys()))
        display_currency = CURRENCY_OPTIONS[currency_label]
    with col2:
        mode_filter = st.multiselect("Delivery mode", ["Online live", "Self-paced", "Classroom", "Blended"])
    with col3:
        atp_only = st.checkbox("ATP providers only")
        voucher_only = st.checkbox("Exam voucher included only")

    with st.spinner("Fetching exchange rates..."):
        rates = fetch_exchange_rates(forex_key)

    if not rates:
        st.error("Could not load exchange rates.")
        return

    st.caption(f"Rates cached · last updated {datetime.now().strftime('%d %b %Y %H:%M')}")

    df = build_comparison_df(priced, rates, display_currency)

    if df.empty:
        st.warning("No data to display.")
        return

    prices_usd = [convert_price(c["price"], c.get("currency", "USD"), "USD", rates) for c in priced if c.get("price")]
    prices_usd = [p for p in prices_usd if p]

    if prices_usd:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Providers", len(df))
        m2.metric("Lowest", format_price(min(prices_usd), "USD"))
        m3.metric("Highest", format_price(max(prices_usd), "USD"))
        m4.metric("Average", format_price(sum(prices_usd) / len(prices_usd), "USD"))

    if mode_filter:
        df = df[df["Delivery"].isin(mode_filter)]
    if atp_only:
        df = df[df["ATP"] == "✅"]
    if voucher_only:
        df = df[df["Voucher"] == "Yes ✅"]

    st.divider()
    st.subheader(f"PMP training prices — {location}")

    display_cols = ["Provider", f"Price ({display_currency})", "Price (USD)", "Delivery", "Duration", "PDU hrs", "Voucher", "ATP", "Rating"]
    # Remove duplicate when display currency is USD
    display_cols = list(dict.fromkeys(display_cols))
    display_cols = [c for c in display_cols if c in df.columns]

    st.dataframe(df[display_cols], use_container_width=True,
                 column_config={"Provider": st.column_config.TextColumn(width="large")})

    csv = df[display_cols].to_csv(index=False)
    st.download_button("Download CSV", csv,
                       file_name=f"pmp_prices_{location.replace(',','').replace(' ','_').lower()}.csv",
                       mime="text/csv")

    enriched = enrich_with_forex(courses, forex_key, display_currency)
    st.session_state["enriched_courses"] = enriched
    st.session_state["display_currency"] = display_currency


if __name__ == "__main__":
    render_module3()

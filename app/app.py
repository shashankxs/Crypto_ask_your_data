"""
"Ask Your Crypto Data" — a premium-feeling crypto analytics dashboard with
a natural-language query layer over a dbt-modeled MotherDuck warehouse.

Architecture:
    data.py       - all DuckDB/MotherDuck queries (cached)
    indicators.py - MA / Bollinger / RSI / MACD, hand-rolled in pandas
    charts.py     - Plotly figure builders (technical chart, gauge, comparison)
    sparkline.py  - inline SVG sparklines (KPI cards, table cells)
    components.py - HTML/CSS widgets (ticker tape, cards, trading-grid table)
    theme.py      - palette + CSS + Plotly template
    ai.py         - natural-language-to-SQL (Groq by default, Anthropic optional)
                    and the SQL safety guardrail

Run locally:
    streamlit run app/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# Not every launcher (Streamlit Cloud, AppTest) adds this script's own
# directory to sys.path the way `streamlit run app/app.py` does locally —
# add it explicitly so the sibling-module imports below always resolve.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ai  # noqa: E402
import charts  # noqa: E402
import components as comp  # noqa: E402
import data  # noqa: E402
import theme  # noqa: E402

load_dotenv()

RANGES = ["7D", "30D", "90D", "ALL"]


def render_hero() -> None:
    st.markdown('<div class="hero-title">⚡ Ask Your Crypto Data</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-sub">A dbt-modeled warehouse of live crypto market data, '
        "queried in plain English — press <span class=\"kbd-hint\">⌘K</span> or "
        "<span class=\"kbd-hint\">Ctrl+K</span> to ask anything.</div>",
        unsafe_allow_html=True,
    )


def render_kpis(df: pd.DataFrame) -> None:
    total_mcap = df["market_cap_usd"].sum()
    avg_24h = df["price_change_pct_24h"].mean()
    best = df.loc[df["price_change_pct_24h"].idxmax()]
    worst = df.loc[df["price_change_pct_24h"].idxmin()]
    freshness = pd.to_datetime(df["snapshot_loaded_at"].max())

    # Sparkline for the market-cap card: aggregate daily market cap across
    # the top coins over the last 30 days.
    mcap_spark = data.get_duckdb_connection().execute(
        """
        select price_date, sum(market_cap_usd) as total_mcap
        from marts.fct_coin_price_daily
        where price_date >= current_date - 30
        group by price_date order by price_date
        """
    ).fetchdf()

    cols = st.columns(4)
    with cols[0]:
        st.markdown(
            comp.stat_card_html(
                "Tracked Market Cap", comp.fmt_compact(total_mcap),
                spark_values=mcap_spark["total_mcap"].tolist() if not mcap_spark.empty else None,
                spark_color=theme.ACCENT,
            ),
            unsafe_allow_html=True,
        )
    with cols[1]:
        st.markdown(
            comp.stat_card_html("Avg 24h Change", comp.fmt_pct(avg_24h), delta_color=theme.pct_color(avg_24h)),
            unsafe_allow_html=True,
        )
    with cols[2]:
        st.markdown(
            comp.stat_card_html(
                "Top Gainer (24h)", f'{best["symbol"]} {comp.fmt_pct(best["price_change_pct_24h"])}',
                delta_color=theme.GOOD,
            ),
            unsafe_allow_html=True,
        )
    with cols[3]:
        st.markdown(
            comp.stat_card_html(
                "Top Loser (24h)", f'{worst["symbol"]} {comp.fmt_pct(worst["price_change_pct_24h"])}',
                delta_color=theme.CRITICAL,
            ),
            unsafe_allow_html=True,
        )

    st.markdown(
        f'<div class="pill">🕒 Data as of {freshness.strftime("%Y-%m-%d %H:%M UTC")}</div>'
        f'<div class="pill">🪙 {len(df)} coins tracked</div>'
        f'<div class="pill">🔁 Refreshed every 6h via GitHub Actions</div>',
        unsafe_allow_html=True,
    )


def render_market_table(df: pd.DataFrame) -> None:
    st.markdown('<div class="section-title">💹 Market Overview</div>', unsafe_allow_html=True)
    sparklines: dict[str, list[float]] = {}
    for coin_id in df["coin_id"].head(15):
        hist = data.load_price_daily(coin_id, days=14)
        if not hist.empty:
            sparklines[coin_id] = hist["price_usd"].tolist()
    comp.render_trading_grid(df, sparklines=sparklines)


def render_fear_greed(days: int | None) -> None:
    sentiment = data.load_sentiment_daily(days=days)
    if sentiment.empty:
        return
    latest = sentiment.iloc[-1]
    st.plotly_chart(
        charts.build_fear_greed_gauge(latest["fear_greed_value"], latest["fear_greed_label"]),
        width="stretch", config={"displayModeBar": False},
    )


def render_technical_chart(coin_choices: pd.DataFrame) -> None:
    st.markdown('<div class="section-title">📈 Technical Chart</div>', unsafe_allow_html=True)

    top_cols = st.columns([2, 2, 2, 3])
    with top_cols[0]:
        label_to_id = {f'{r["name"]} ({r["symbol"]})': r["coin_id"] for _, r in coin_choices.iterrows()}
        chosen_label = st.selectbox("Coin", list(label_to_id.keys()), index=0)
        coin_id = label_to_id[chosen_label]
    with top_cols[1]:
        time_range = st.radio("Range", RANGES, horizontal=True, index=2, label_visibility="collapsed")
    with top_cols[2]:
        days = data.RANGE_TO_DAYS[time_range]
        has_ohlc_res = time_range in ("90D", "ALL")
        chart_type_options = ["Candlestick", "Line", "Area"] if has_ohlc_res else ["Line", "Area"]
        chart_type = st.selectbox("Chart type", chart_type_options, index=0).lower()
    with top_cols[3]:
        with st.expander("Indicators", expanded=False):
            ma_cols = st.columns(3)
            show_mas = [w for w, c in zip((7, 25, 50), ma_cols) if c.checkbox(f"MA{w}", value=(w == 7))]
            ind_cols = st.columns(3)
            show_bollinger = ind_cols[0].checkbox("Bollinger Bands")
            show_rsi = ind_cols[1].checkbox("RSI")
            show_macd = ind_cols[2].checkbox("MACD")

    if not has_ohlc_res and chart_type == "candlestick":
        chart_type = "line"

    price_df = data.load_price_daily(coin_id, days=days)
    ohlc_df = data.load_ohlc(coin_id, days=days) if has_ohlc_res else pd.DataFrame()

    if price_df.empty:
        st.info("No price history available for this coin yet.")
        return

    if time_range in ("7D", "30D") and chart_type == "candlestick":
        st.caption(
            "ℹ️ Candlesticks need OHLC data; CoinGecko's free tier only gives ~4-day "
            "candle resolution at this ingestion window, so 7D/30D show the daily "
            "price line instead of fabricating finer candles."
        )

    fig = charts.build_technical_chart(
        price_df, ohlc_df, chart_type, show_mas, show_bollinger, show_rsi, show_macd,
    )
    st.plotly_chart(
        fig, width="stretch",
        config={"displayModeBar": True, "toImageButtonOptions": {"format": "png", "filename": f"{coin_id}_chart"}},
    )

    dl_cols = st.columns([1, 1, 6])
    with dl_cols[0]:
        st.download_button("⬇ CSV", price_df.to_csv(index=False), file_name=f"{coin_id}_daily.csv", width="stretch")
    with dl_cols[1]:
        st.caption("PNG export: camera icon in chart toolbar ⤴")


def render_comparison(coin_choices: pd.DataFrame) -> None:
    with st.expander("🔀 Comparison mode (overlay multiple coins, normalized)", expanded=False):
        label_to_id = {f'{r["name"]} ({r["symbol"]})': r["coin_id"] for _, r in coin_choices.iterrows()}
        labels = st.multiselect("Compare coins", list(label_to_id.keys()), default=list(label_to_id.keys())[:2])
        if len(labels) < 2:
            st.caption("Pick at least 2 coins to compare.")
            return
        range_choice = st.radio("Range", RANGES, horizontal=True, index=2, key="cmp_range")
        days = data.RANGE_TO_DAYS[range_choice]
        series = {}
        for label in labels:
            coin_id = label_to_id[label]
            df = data.load_price_daily(coin_id, days=days)
            symbol = coin_choices.loc[coin_choices["coin_id"] == coin_id, "symbol"].iloc[0]
            series[symbol] = df[["price_date", "price_usd"]]
        st.plotly_chart(charts.build_comparison_chart(series), width="stretch")


def render_ask_section() -> None:
    st.markdown('<div class="section-title">✨ Ask Anything</div>', unsafe_allow_html=True)

    if "question" not in st.session_state:
        st.session_state["question"] = ""

    chip_cols = st.columns(len(ai.SUGGESTED_QUESTIONS))
    for col, q in zip(chip_cols, ai.SUGGESTED_QUESTIONS):
        with col:
            if st.button(q, key=f"chip_{q}", width="stretch"):
                st.session_state["question"] = q

    input_label = "Ask a question about the crypto market"
    question = st.text_input(
        input_label, key="question", label_visibility="collapsed",
        placeholder="e.g. Which coins are furthest below their all-time high right now?  (⌘K)",
    )
    comp.inject_command_palette_shortcut(input_label)
    ask_clicked = st.button("Ask →", type="primary")

    if not (ask_clicked and question):
        return

    with st.spinner("Thinking in SQL..."):
        try:
            sql = ai.question_to_sql(question)
            ai.validate_sql(sql)
        except ValueError as exc:
            st.error(f"Could not safely execute that question: {exc}")
            return

    with st.expander("🔍 Generated SQL", expanded=False):
        st.code(sql, language="sql")

    con = data.get_duckdb_connection()
    try:
        df: pd.DataFrame = con.execute(sql).fetchdf()
    except Exception as exc:  # noqa: BLE001 - surface any DB error to the user
        st.error(f"Query failed: {exc}")
        return

    if df.empty:
        st.info("Query ran successfully but returned no rows.")
        return

    if df.shape == (1, 1):
        value = df.iloc[0, 0]
        st.markdown(
            comp.stat_card_html(question, f"{value:,.4g}" if isinstance(value, (int, float)) else str(value)),
            unsafe_allow_html=True,
        )
        return

    st.dataframe(df, width="stretch", hide_index=True)

    dl_cols = st.columns([1, 6])
    with dl_cols[0]:
        st.download_button("⬇ CSV", df.to_csv(index=False), file_name="query_result.csv", width="stretch")

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    date_cols = [c for c in df.columns if "date" in c.lower() or "time" in c.lower()]
    template = theme.plotly_dark_template()

    import plotly.graph_objects as go

    if numeric_cols and date_cols:
        fig = go.Figure()
        for i, col in enumerate(numeric_cols):
            fig.add_trace(
                go.Scatter(
                    x=df[date_cols[0]], y=df[col], mode="lines+markers", name=col,
                    line=dict(width=2, color=theme.CATEGORICAL[i % len(theme.CATEGORICAL)]),
                    marker=dict(size=8),
                )
            )
        fig.update_layout(template=template, height=420)
        st.plotly_chart(fig, width="stretch")
    elif numeric_cols and len(df.columns) - len(numeric_cols) >= 1:
        label_col = [c for c in df.columns if c not in numeric_cols][0]
        fig = go.Figure(go.Bar(x=df[label_col], y=df[numeric_cols[0]], marker=dict(color=theme.CATEGORICAL[0])))
        fig.update_layout(template=template, height=420)
        st.plotly_chart(fig, width="stretch")


def render_footer() -> None:
    st.markdown(
        '<div class="footer-note">Built with CoinGecko · alternative.me · dbt · MotherDuck · '
        f"{('Anthropic Claude' if ai.LLM_PROVIDER == 'anthropic' else 'Groq')} · Streamlit · "
        "orchestrated via GitHub Actions</div>",
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="Ask Your Crypto Data", page_icon="⚡", layout="wide")
    theme.inject_css()

    overview = data.load_overview()
    comp.render_ticker_tape(overview)
    render_hero()
    render_kpis(overview)

    main_col, side_col = st.columns([3, 1])
    with main_col:
        coin_choices = data.load_coin_choices()
        render_technical_chart(coin_choices)
        render_comparison(coin_choices)
    with side_col:
        st.markdown('<div class="section-title">😨 Fear &amp; Greed</div>', unsafe_allow_html=True)
        render_fear_greed(days=None)

    render_market_table(overview)
    render_ask_section()
    render_footer()


if __name__ == "__main__":
    main()

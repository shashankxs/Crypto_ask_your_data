"""
"Ask Your Data" — a natural-language front end over the crypto warehouse
built by ingestion/ingest_coingecko.py + the dbt_project/ models.

The user asks a plain-English question; an LLM translates it into a SQL
query against the dbt marts (schema injected into the prompt), the app
executes it read-only against MotherDuck, and renders a table + chart.

Supports two LLM providers (set LLM_PROVIDER in .env):
    groq      (default) — free API, no credit card required: https://console.groq.com
    anthropic — requires a billed Anthropic API key

Run locally:
    streamlit run app/app.py
"""
from __future__ import annotations

import os
import re

import duckdb
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq").lower()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

# ---------------------------------------------------------------------------
# Palette (validated: references/palette.md — dark-mode steps)
# ---------------------------------------------------------------------------
PAGE_PLANE = "#0d0d0d"
SURFACE = "#1a1a19"
SURFACE_RAISED = "#202020"
TEXT_PRIMARY = "#f0efec"
TEXT_SECONDARY = "#c3c2b7"
TEXT_MUTED = "#898781"
GRIDLINE = "#2c2c2a"
BASELINE = "#383835"
BORDER = "rgba(255,255,255,0.10)"
GOOD = "#0ca30c"
CRITICAL = "#e66767"
CATEGORICAL = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]

SCHEMA_DESCRIPTION = """
You can query these dbt-modeled tables in the `marts` schema:

marts.dim_coin(coin_id, symbol, name, image_url, market_cap_rank)
    -- one row per coin

marts.fct_coin_latest_snapshot(
    coin_id, symbol, name, image_url, market_cap_rank, price_usd, market_cap_usd,
    volume_usd, price_change_pct_24h, price_change_pct_7d,
    circulating_supply, all_time_high_usd, ath_change_pct, snapshot_loaded_at
)
    -- latest point-in-time snapshot per coin

marts.fct_coin_price_daily(
    coin_id, price_date, price_usd, volume_usd, market_cap_usd,
    price_7d_moving_avg, daily_return_pct
)
    -- one row per coin per day of history
"""

SYSTEM_PROMPT = f"""You are a SQL analyst for a DuckDB/MotherDuck warehouse of
cryptocurrency market data. {SCHEMA_DESCRIPTION}

Rules:
- Write exactly one read-only DuckDB SQL SELECT query that answers the user's question.
- Only reference the tables and columns listed above.
- Never write INSERT, UPDATE, DELETE, DROP, ALTER, or any DDL/DML statement.
- Return ONLY the SQL query, no explanation, no markdown code fences.
"""

FORBIDDEN_PATTERN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|attach|copy|pragma|call)\b",
    re.IGNORECASE,
)

SUGGESTED_QUESTIONS = [
    "Which 5 coins gained the most in the last 24 hours?",
    "Show bitcoin's daily price and 7-day moving average for the last 30 days",
    "Which coins are furthest below their all-time high right now?",
    "What's the average daily return for the top 10 coins by market cap?",
]


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------
@st.cache_resource(ttl=300)
def get_duckdb_connection() -> duckdb.DuckDBPyConnection:
    token = os.environ.get("MOTHERDUCK_TOKEN")
    database = os.environ.get("MD_DATABASE", "crypto_db")
    if not token:
        st.error("MOTHERDUCK_TOKEN is not set. Add it to .env or Streamlit secrets.")
        st.stop()
    return duckdb.connect(f"md:{database}?motherduck_token={token}", read_only=True)


@st.cache_data(ttl=300)
def load_overview() -> pd.DataFrame:
    con = get_duckdb_connection()
    return con.execute(
        """
        select coin_id, symbol, name, image_url, market_cap_rank, price_usd,
               market_cap_usd, volume_usd, price_change_pct_24h, price_change_pct_7d,
               ath_change_pct, snapshot_loaded_at
        from marts.fct_coin_latest_snapshot
        order by market_cap_rank
        """
    ).fetchdf()


@st.cache_data(ttl=300)
def load_sparkline(coin_id: str) -> pd.DataFrame:
    con = get_duckdb_connection()
    return con.execute(
        "select price_date, price_usd from marts.fct_coin_price_daily "
        "where coin_id = ? order by price_date",
        [coin_id],
    ).fetchdf()


# ---------------------------------------------------------------------------
# LLM text-to-SQL
# ---------------------------------------------------------------------------
def question_to_sql(question: str) -> str:
    raw = _call_anthropic(question) if LLM_PROVIDER == "anthropic" else _call_groq(question)
    return re.sub(r"^```sql\s*|```$", "", raw.strip(), flags=re.IGNORECASE | re.MULTILINE).strip()


def _call_groq(question: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        st.error("GROQ_API_KEY is not set. Get a free key at https://console.groq.com and add it to .env.")
        st.stop()
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            "max_tokens": 400,
            "temperature": 0,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_anthropic(question: str) -> str:
    from anthropic import Anthropic  # optional dependency, only needed for this provider

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        st.error("ANTHROPIC_API_KEY is not set. Add it to .env or Streamlit secrets.")
        st.stop()
    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=400,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": question}],
    )
    return response.content[0].text


def validate_sql(sql: str) -> None:
    if not sql.lower().startswith("select"):
        raise ValueError("Generated query must be a single SELECT statement.")
    if FORBIDDEN_PATTERN.search(sql):
        raise ValueError("Generated query contains a disallowed keyword.")
    if ";" in sql.strip().rstrip(";"):
        raise ValueError("Only a single statement is allowed.")


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def fmt_usd(value: float) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"${value:,.2f}" if value < 1000 else f"${value:,.0f}"


def fmt_compact(value: float) -> str:
    if value is None or pd.isna(value):
        return "—"
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= threshold:
            return f"${value / threshold:,.2f}{suffix}"
    return f"${value:,.0f}"


def fmt_pct(value: float) -> str:
    if value is None or pd.isna(value):
        return "—"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:,.2f}%"


def pct_color(value: float) -> str:
    if value is None or pd.isna(value):
        return TEXT_MUTED
    return GOOD if value >= 0 else CRITICAL


# ---------------------------------------------------------------------------
# UI chrome
# ---------------------------------------------------------------------------
def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Inter', system-ui, -apple-system, "Segoe UI", sans-serif !important;
        }}
        .stApp {{
            background: radial-gradient(circle at 15% 0%, #14213a 0%, {PAGE_PLANE} 45%);
        }}
        #MainMenu, footer, header {{ visibility: hidden; }}

        .hero-title {{
            font-size: 2.6rem;
            font-weight: 800;
            background: linear-gradient(90deg, #3987e5 0%, #9085e9 60%, #d55181 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.1rem;
            letter-spacing: -0.02em;
        }}
        .hero-sub {{
            color: {TEXT_SECONDARY};
            font-size: 1.02rem;
            margin-bottom: 1.6rem;
        }}

        .stat-card {{
            background: {SURFACE};
            border: 1px solid {BORDER};
            border-radius: 16px;
            padding: 1.1rem 1.3rem;
            box-shadow: 0 4px 24px rgba(0,0,0,0.25);
            transition: transform 0.15s ease, border-color 0.15s ease;
        }}
        .stat-card:hover {{
            transform: translateY(-2px);
            border-color: rgba(57,135,229,0.4);
        }}
        .stat-label {{
            color: {TEXT_MUTED};
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            font-weight: 600;
            margin-bottom: 0.3rem;
        }}
        .stat-value {{
            color: {TEXT_PRIMARY};
            font-size: 1.65rem;
            font-weight: 700;
            line-height: 1.1;
        }}
        .stat-delta {{
            font-size: 0.92rem;
            font-weight: 600;
            margin-top: 0.25rem;
        }}

        .section-title {{
            color: {TEXT_PRIMARY};
            font-size: 1.3rem;
            font-weight: 700;
            margin-top: 2.2rem;
            margin-bottom: 0.9rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .pill {{
            display: inline-block;
            background: {SURFACE_RAISED};
            border: 1px solid {BORDER};
            color: {TEXT_SECONDARY};
            border-radius: 999px;
            padding: 0.2rem 0.75rem;
            font-size: 0.78rem;
            margin-right: 0.4rem;
        }}

        div[data-testid="stTextInput"] input {{
            background: {SURFACE} !important;
            border: 1px solid {BORDER} !important;
            border-radius: 12px !important;
            color: {TEXT_PRIMARY} !important;
            font-size: 1.05rem !important;
            padding: 0.85rem 1rem !important;
        }}
        div[data-testid="stTextInput"] input:focus {{
            border-color: #3987e5 !important;
            box-shadow: 0 0 0 2px rgba(57,135,229,0.25) !important;
        }}

        div[data-testid="stButton"] button {{
            background: {SURFACE_RAISED};
            border: 1px solid {BORDER};
            color: {TEXT_SECONDARY};
            border-radius: 999px;
            font-size: 0.85rem;
            padding: 0.35rem 0.9rem;
            transition: all 0.15s ease;
        }}
        div[data-testid="stButton"] button:hover {{
            border-color: #3987e5;
            color: {TEXT_PRIMARY};
            background: rgba(57,135,229,0.12);
        }}
        div[data-testid="stButton"] button[kind="primary"] {{
            background: linear-gradient(90deg, #3987e5, #9085e9);
            border: none;
            color: white;
            font-weight: 600;
            padding: 0.6rem 1.6rem;
        }}

        .footer-note {{
            color: {TEXT_MUTED};
            font-size: 0.82rem;
            margin-top: 3rem;
            text-align: center;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def plotly_dark_template() -> go.layout.Template:
    return go.layout.Template(
        layout=go.Layout(
            paper_bgcolor=SURFACE,
            plot_bgcolor=SURFACE,
            font=dict(color=TEXT_PRIMARY, family="Inter, sans-serif"),
            colorway=CATEGORICAL,
            xaxis=dict(gridcolor=GRIDLINE, zerolinecolor=BASELINE, linecolor=BASELINE),
            yaxis=dict(gridcolor=GRIDLINE, zerolinecolor=BASELINE, linecolor=BASELINE),
            legend=dict(bgcolor="rgba(0,0,0,0)"),
            margin=dict(l=10, r=10, t=30, b=10),
            hoverlabel=dict(bgcolor=SURFACE_RAISED, font_color=TEXT_PRIMARY, bordercolor=BORDER),
        )
    )


def stat_card(label: str, value: str, delta: str | None = None, delta_color: str = TEXT_MUTED) -> str:
    delta_html = f'<div class="stat-delta" style="color:{delta_color}">{delta}</div>' if delta else ""
    return f"""
    <div class="stat-card">
        <div class="stat-label">{label}</div>
        <div class="stat-value">{value}</div>
        {delta_html}
    </div>
    """


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
def render_hero() -> None:
    st.markdown('<div class="hero-title">📊 Ask Your Crypto Data</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-sub">A dbt-modeled warehouse of live CoinGecko market data, '
        "queried in plain English — an LLM writes the SQL, DuckDB/MotherDuck runs it.</div>",
        unsafe_allow_html=True,
    )


def render_stats(df: pd.DataFrame) -> None:
    total_mcap = df["market_cap_usd"].sum()
    avg_24h = df["price_change_pct_24h"].mean()
    best = df.loc[df["price_change_pct_24h"].idxmax()]
    worst = df.loc[df["price_change_pct_24h"].idxmin()]
    freshness = pd.to_datetime(df["snapshot_loaded_at"].max())

    cols = st.columns(4)
    with cols[0]:
        st.markdown(stat_card("Tracked Market Cap", fmt_compact(total_mcap)), unsafe_allow_html=True)
    with cols[1]:
        st.markdown(
            stat_card("Avg 24h Change", fmt_pct(avg_24h), delta_color=pct_color(avg_24h)),
            unsafe_allow_html=True,
        )
    with cols[2]:
        st.markdown(
            stat_card(
                "Top Gainer (24h)",
                f'{best["symbol"]} {fmt_pct(best["price_change_pct_24h"])}',
                delta_color=GOOD,
            ),
            unsafe_allow_html=True,
        )
    with cols[3]:
        st.markdown(
            stat_card(
                "Top Loser (24h)",
                f'{worst["symbol"]} {fmt_pct(worst["price_change_pct_24h"])}',
                delta_color=CRITICAL,
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
    view = df[
        ["image_url", "name", "symbol", "price_usd", "price_change_pct_24h",
         "price_change_pct_7d", "market_cap_usd", "ath_change_pct"]
    ].copy()
    st.dataframe(
        view,
        hide_index=True,
        width="stretch",
        column_config={
            "image_url": st.column_config.ImageColumn(" ", width="small"),
            "name": st.column_config.TextColumn("Coin"),
            "symbol": st.column_config.TextColumn("Ticker"),
            "price_usd": st.column_config.NumberColumn("Price", format="$%.2f"),
            "price_change_pct_24h": st.column_config.NumberColumn("24h %", format="%.2f%%"),
            "price_change_pct_7d": st.column_config.NumberColumn("7d %", format="%.2f%%"),
            "market_cap_usd": st.column_config.NumberColumn("Market Cap", format="compact"),
            "ath_change_pct": st.column_config.NumberColumn("vs ATH", format="%.1f%%"),
        },
    )


def render_ask_section() -> None:
    st.markdown('<div class="section-title">✨ Ask Anything</div>', unsafe_allow_html=True)

    if "question" not in st.session_state:
        st.session_state["question"] = ""

    chip_cols = st.columns(len(SUGGESTED_QUESTIONS))
    for col, q in zip(chip_cols, SUGGESTED_QUESTIONS):
        with col:
            if st.button(q, key=f"chip_{q}", width="stretch"):
                st.session_state["question"] = q

    question = st.text_input(
        "Ask a question about the crypto market",
        key="question",
        label_visibility="collapsed",
        placeholder="e.g. Which coins are furthest below their all-time high right now?",
    )
    ask_clicked = st.button("Ask →", type="primary")

    if not (ask_clicked and question):
        return

    with st.spinner("Thinking in SQL..."):
        try:
            sql = question_to_sql(question)
            validate_sql(sql)
        except ValueError as exc:
            st.error(f"Could not safely execute that question: {exc}")
            return

    with st.expander("🔍 Generated SQL", expanded=False):
        st.code(sql, language="sql")

    con = get_duckdb_connection()
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
            stat_card(question, f"{value:,.4g}" if isinstance(value, (int, float)) else str(value)),
            unsafe_allow_html=True,
        )
        return

    st.dataframe(df, width="stretch", hide_index=True)

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    date_cols = [c for c in df.columns if "date" in c.lower() or "time" in c.lower()]
    template = plotly_dark_template()

    if numeric_cols and date_cols:
        fig = go.Figure()
        for i, col in enumerate(numeric_cols):
            fig.add_trace(
                go.Scatter(
                    x=df[date_cols[0]], y=df[col], mode="lines+markers", name=col,
                    line=dict(width=2, color=CATEGORICAL[i % len(CATEGORICAL)]),
                    marker=dict(size=8),
                )
            )
        fig.update_layout(template=template, height=420, hovermode="x unified")
        st.plotly_chart(fig, width="stretch")
    elif numeric_cols and len(df.columns) - len(numeric_cols) >= 1:
        label_col = [c for c in df.columns if c not in numeric_cols][0]
        fig = go.Figure(
            go.Bar(
                x=df[label_col], y=df[numeric_cols[0]],
                marker=dict(color=CATEGORICAL[0]),
            )
        )
        fig.update_layout(template=template, height=420)
        st.plotly_chart(fig, width="stretch")


def render_footer() -> None:
    st.markdown(
        '<div class="footer-note">Built with CoinGecko · dbt · MotherDuck · '
        f"{('Anthropic Claude' if LLM_PROVIDER == 'anthropic' else 'Groq')} · Streamlit · "
        "orchestrated via GitHub Actions</div>",
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="Ask Your Crypto Data", page_icon="📊", layout="wide")
    inject_css()
    render_hero()

    df = load_overview()
    render_stats(df)
    render_market_table(df)
    render_ask_section()
    render_footer()


if __name__ == "__main__":
    main()

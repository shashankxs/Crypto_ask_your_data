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
import plotly.express as px
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq").lower()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

SCHEMA_DESCRIPTION = """
You can query these dbt-modeled tables in the `marts` schema:

marts.dim_coin(coin_id, symbol, name, market_cap_rank)
    -- one row per coin

marts.fct_coin_latest_snapshot(
    coin_id, symbol, name, market_cap_rank, price_usd, market_cap_usd,
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


def get_duckdb_connection() -> duckdb.DuckDBPyConnection:
    token = os.environ.get("MOTHERDUCK_TOKEN")
    database = os.environ.get("MD_DATABASE", "crypto_db")
    if not token:
        st.error("MOTHERDUCK_TOKEN is not set. Add it to .env or Streamlit secrets.")
        st.stop()
    return duckdb.connect(f"md:{database}?motherduck_token={token}", read_only=True)


def question_to_sql(question: str) -> str:
    if LLM_PROVIDER == "anthropic":
        raw = _call_anthropic(question)
    else:
        raw = _call_groq(question)
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


def main() -> None:
    st.set_page_config(page_title="Ask Your Crypto Data", page_icon="📊", layout="wide")
    st.title("📊 Ask Your Crypto Data")
    st.caption(
        "A dbt-modeled warehouse of live CoinGecko market data, queried in plain English. "
        "Ask a question below — an LLM writes the SQL, DuckDB/MotherDuck runs it."
    )

    with st.sidebar:
        st.header("How it works")
        st.markdown(
            "1. A scheduled job ingests CoinGecko market data into MotherDuck\n"
            "2. dbt builds staging + mart tables with tests\n"
            "3. Your question is converted to SQL by Claude\n"
            "4. The query runs read-only against the marts\n\n"
            "Try:\n"
            "- *Which 5 coins gained the most in the last 24 hours?*\n"
            "- *Show bitcoin's daily price and 7-day moving average for the last 30 days*\n"
            "- *What's the average daily return for the top 10 coins by market cap?*"
        )

    question = st.text_input("Ask a question about the crypto market:", "")

    if st.button("Ask", type="primary") and question:
        with st.spinner("Generating SQL..."):
            try:
                sql = question_to_sql(question)
                validate_sql(sql)
            except ValueError as exc:
                st.error(f"Could not safely execute that question: {exc}")
                return

        with st.expander("Generated SQL", expanded=False):
            st.code(sql, language="sql")

        con = get_duckdb_connection()
        try:
            df: pd.DataFrame = con.execute(sql).fetchdf()
        except Exception as exc:  # noqa: BLE001 - surface any DB error to the user
            st.error(f"Query failed: {exc}")
            return
        finally:
            con.close()

        if df.empty:
            st.info("Query ran successfully but returned no rows.")
            return

        st.dataframe(df, use_container_width=True)

        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        date_cols = [c for c in df.columns if "date" in c.lower() or "time" in c.lower()]
        if numeric_cols and date_cols:
            fig = px.line(df, x=date_cols[0], y=numeric_cols, markers=True)
            st.plotly_chart(fig, use_container_width=True)
        elif numeric_cols and len(df.columns) - len(numeric_cols) >= 1:
            label_col = [c for c in df.columns if c not in numeric_cols][0]
            fig = px.bar(df, x=label_col, y=numeric_cols[0])
            st.plotly_chart(fig, use_container_width=True)


if __name__ == "__main__":
    main()

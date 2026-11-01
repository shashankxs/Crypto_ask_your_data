"""
The natural-language-to-SQL layer: schema-scoped prompt, provider calls
(Groq by default, Anthropic optional), and the SQL safety guardrail.

Kept separate from UI code so it can be unit-tested (see tests/) without
importing Streamlit or touching a live connection.
"""
from __future__ import annotations

import os
import re

import requests
import streamlit as st

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq").lower()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

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

marts.fct_market_sentiment_daily(
    date, market_avg_daily_return_pct, market_total_volume_usd,
    fear_greed_value, fear_greed_label
)
    -- one row per calendar day: aggregated market stats across all tracked
    -- coins joined with the Crypto Fear & Greed Index (an independent
    -- sentiment source, 0-100, labeled e.g. "Fear"/"Neutral"/"Greed")

marts.fct_coin_ohlc(coin_id, candle_time, open, high, low, close)
    -- candlestick data per coin; candle width is ~4 days at our ingestion window
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
    "Was market sentiment fearful on the days with the biggest price drops?",
]


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
            "max_completion_tokens": 1024,
            "temperature": 0,
            # gpt-oss is a reasoning model; keep its chain-of-thought out of
            # `content` so it doesn't eat the token budget or leak into the SQL.
            "reasoning_effort": "low",
        },
        timeout=30,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    if not content.strip():
        raise ValueError("The model returned an empty response — try rephrasing the question.")
    return content


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
    stripped = sql.strip()
    if not (stripped.lower().startswith("select") or stripped.lower().startswith("with")):
        raise ValueError("Generated query must be a single SELECT (optionally with CTEs) statement.")
    if FORBIDDEN_PATTERN.search(sql):
        raise ValueError("Generated query contains a disallowed keyword.")
    if ";" in stripped.rstrip(";"):
        raise ValueError("Only a single statement is allowed.")

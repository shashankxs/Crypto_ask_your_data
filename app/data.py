"""
All DuckDB/MotherDuck query functions, cached via Streamlit. Kept separate
from rendering code so the chart/UI modules don't need to know about
connection handling or SQL.
"""
from __future__ import annotations

import os

import duckdb
import pandas as pd
import streamlit as st

RANGE_TO_DAYS = {"7D": 7, "30D": 30, "90D": 90, "ALL": None}


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
def load_price_daily(coin_id: str, days: int | None = None) -> pd.DataFrame:
    con = get_duckdb_connection()
    if days is None:
        return con.execute(
            "select price_date, price_usd, volume_usd, price_7d_moving_avg, daily_return_pct "
            "from marts.fct_coin_price_daily where coin_id = ? order by price_date",
            [coin_id],
        ).fetchdf()
    return con.execute(
        "select price_date, price_usd, volume_usd, price_7d_moving_avg, daily_return_pct "
        "from marts.fct_coin_price_daily where coin_id = ? "
        "and price_date >= current_date - CAST(? AS INTEGER) order by price_date",
        [coin_id, days],
    ).fetchdf()


@st.cache_data(ttl=300)
def load_ohlc(coin_id: str, days: int | None = None) -> pd.DataFrame:
    """4-day-candle OHLC history (see ingestion/ingest_coingecko_ohlc.py for why)."""
    con = get_duckdb_connection()
    if days is None:
        return con.execute(
            "select candle_time, open, high, low, close from marts.fct_coin_ohlc "
            "where coin_id = ? order by candle_time",
            [coin_id],
        ).fetchdf()
    return con.execute(
        "select candle_time, open, high, low, close from marts.fct_coin_ohlc "
        "where coin_id = ? and candle_time >= current_date - CAST(? AS INTEGER) "
        "order by candle_time",
        [coin_id, days],
    ).fetchdf()


@st.cache_data(ttl=300)
def load_sentiment_daily(days: int | None = None) -> pd.DataFrame:
    con = get_duckdb_connection()
    if days is None:
        return con.execute(
            "select date, fear_greed_value, fear_greed_label from marts.fct_market_sentiment_daily "
            "order by date"
        ).fetchdf()
    return con.execute(
        "select date, fear_greed_value, fear_greed_label from marts.fct_market_sentiment_daily "
        "where date >= current_date - CAST(? AS INTEGER) order by date",
        [days],
    ).fetchdf()


@st.cache_data(ttl=300)
def load_coin_choices() -> pd.DataFrame:
    con = get_duckdb_connection()
    return con.execute(
        "select coin_id, symbol, name from marts.dim_coin where symbol is not null "
        "order by market_cap_rank nulls last"
    ).fetchdf()

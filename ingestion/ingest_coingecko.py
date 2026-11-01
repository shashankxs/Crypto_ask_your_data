"""
Pulls current market snapshots and historical daily prices for the top N
coins from CoinGecko's free public API and lands them as raw tables in
MotherDuck (cloud-hosted DuckDB), ready for dbt to model.

Usage:
    python ingestion/ingest_coingecko.py --top 25 --history-days 90

Env vars (see .env.example):
    MOTHERDUCK_TOKEN
    MD_DATABASE
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timezone

import duckdb
import requests
from dotenv import load_dotenv

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
REQUEST_PAUSE_SECONDS = 1.5  # stay under CoinGecko's free-tier rate limit


def get_connection() -> duckdb.DuckDBPyConnection:
    load_dotenv()
    token = os.environ.get("MOTHERDUCK_TOKEN")
    database = os.environ.get("MD_DATABASE", "crypto_db")
    if not token:
        raise RuntimeError(
            "MOTHERDUCK_TOKEN is not set. Copy .env.example to .env and fill it in, "
            "or `export MOTHERDUCK_TOKEN=...` (free token at https://motherduck.com)."
        )
    return duckdb.connect(f"md:{database}?motherduck_token={token}")


def fetch_market_snapshot(top: int) -> list[dict]:
    resp = requests.get(
        f"{COINGECKO_BASE}/coins/markets",
        params={
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": top,
            "page": 1,
            "price_change_percentage": "24h,7d",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_history(coin_id: str, days: int) -> list[tuple[str, float, float, float]]:
    resp = requests.get(
        f"{COINGECKO_BASE}/coins/{coin_id}/market_chart",
        params={"vs_currency": "usd", "days": days, "interval": "daily"},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    prices = payload.get("prices", [])
    volumes = dict(payload.get("total_volumes", []))
    market_caps = dict(payload.get("market_caps", []))
    rows = []
    for ts_ms, price in prices:
        rows.append((coin_id, ts_ms, price, volumes.get(ts_ms), market_caps.get(ts_ms)))
    return rows


def load_snapshot(con: duckdb.DuckDBPyConnection, snapshot: list[dict]) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS raw.coin_market_snapshot (
            loaded_at TIMESTAMP,
            coin_id VARCHAR,
            symbol VARCHAR,
            name VARCHAR,
            current_price DOUBLE,
            market_cap DOUBLE,
            market_cap_rank INTEGER,
            total_volume DOUBLE,
            price_change_pct_24h DOUBLE,
            price_change_pct_7d DOUBLE,
            circulating_supply DOUBLE,
            ath DOUBLE,
            ath_change_pct DOUBLE
        );
        """
    )
    loaded_at = datetime.now(timezone.utc)
    rows = [
        (
            loaded_at,
            c["id"],
            c["symbol"],
            c["name"],
            c.get("current_price"),
            c.get("market_cap"),
            c.get("market_cap_rank"),
            c.get("total_volume"),
            c.get("price_change_percentage_24h"),
            c.get("price_change_percentage_7d_in_currency"),
            c.get("circulating_supply"),
            c.get("ath"),
            c.get("ath_change_percentage"),
        )
        for c in snapshot
    ]
    con.executemany(
        """
        INSERT INTO raw.coin_market_snapshot VALUES
        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    print(f"Loaded {len(rows)} rows into raw.coin_market_snapshot")


def load_history(con: duckdb.DuckDBPyConnection, coin_ids: list[str], days: int) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS raw.coin_price_history (
            coin_id VARCHAR,
            price_timestamp_ms BIGINT,
            price_usd DOUBLE,
            total_volume_usd DOUBLE,
            market_cap_usd DOUBLE
        );
        """
    )
    all_rows = []
    for coin_id in coin_ids:
        try:
            rows = fetch_history(coin_id, days)
            all_rows.extend(rows)
            print(f"  fetched {len(rows)} history points for {coin_id}")
        except requests.HTTPError as exc:
            print(f"  WARNING: failed to fetch history for {coin_id}: {exc}")
        time.sleep(REQUEST_PAUSE_SECONDS)

    if not all_rows:
        return

    placeholders = ", ".join("?" for _ in coin_ids)
    con.execute(
        f"DELETE FROM raw.coin_price_history WHERE coin_id IN ({placeholders})",
        coin_ids,
    )
    con.executemany(
        "INSERT INTO raw.coin_price_history VALUES (?, ?, ?, ?, ?)",
        all_rows,
    )
    print(f"Loaded {len(all_rows)} rows into raw.coin_price_history")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=25, help="Number of top coins by market cap to track")
    parser.add_argument("--history-days", type=int, default=90, help="Days of daily history to backfill/refresh")
    args = parser.parse_args()

    con = get_connection()

    print(f"Fetching market snapshot for top {args.top} coins...")
    snapshot = fetch_market_snapshot(args.top)
    load_snapshot(con, snapshot)

    coin_ids = [c["id"] for c in snapshot]
    print(f"Fetching {args.history_days}d price history for {len(coin_ids)} coins...")
    load_history(con, coin_ids, args.history_days)

    con.close()
    print("Done.")


if __name__ == "__main__":
    main()

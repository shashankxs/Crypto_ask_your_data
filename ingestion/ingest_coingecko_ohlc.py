"""
Pulls OHLC (candlestick) data from CoinGecko's free /coins/{id}/ohlc endpoint
for the current top-N coins and lands it in MotherDuck.

CoinGecko's free tier auto-selects candle granularity by the `days` window
requested — it is NOT configurable independently:
    days <= 2    -> 30-minute candles
    3 <= days <= 30  -> 4-hour candles
    days > 30    -> 4-day candles
At days=90 (our window) this yields ~4-day candles, not daily ones. That's
a real API limitation, not a bug: the chart UI uses this data for 90D/ALL
range views (where 4-day resolution is reasonable) and falls back to the
existing daily price-line data for 7D/30D views rather than pretending to
have finer OHLC resolution than actually exists.

Usage:
    python ingestion/ingest_coingecko_ohlc.py --top 25 --days 90
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_coingecko import (  # noqa: E402 - reuse shared connection/fetch/retry logic
    COINGECKO_BASE,
    MAX_RETRIES,
    REQUEST_PAUSE_SECONDS,
    fetch_market_snapshot,
    get_connection,
)


def fetch_ohlc(coin_id: str, days: int) -> list[tuple[str, int, float, float, float, float]]:
    resp = None
    for attempt in range(MAX_RETRIES):
        resp = requests.get(
            f"{COINGECKO_BASE}/coins/{coin_id}/ohlc",
            params={"vs_currency": "usd", "days": days},
            timeout=30,
        )
        if resp.status_code != 429:
            break
        wait = int(resp.headers.get("Retry-After", REQUEST_PAUSE_SECONDS * (attempt + 2)))
        print(f"  rate limited on {coin_id}, waiting {wait}s (attempt {attempt + 1}/{MAX_RETRIES})")
        time.sleep(wait)
    resp.raise_for_status()
    return [(coin_id, ts_ms, o, h, l, c) for ts_ms, o, h, l, c in resp.json()]


def load_ohlc(con: duckdb.DuckDBPyConnection, coin_ids: list[str], days: int) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS raw.coin_ohlc (
            loaded_at TIMESTAMP,
            coin_id VARCHAR,
            candle_time_ms BIGINT,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE
        );
        """
    )
    loaded_at = datetime.now(timezone.utc)
    all_rows: list[tuple] = []
    for coin_id in coin_ids:
        try:
            rows = fetch_ohlc(coin_id, days)
            all_rows.extend((loaded_at, *r) for r in rows)
            print(f"  fetched {len(rows)} OHLC candles for {coin_id}")
        except requests.HTTPError as exc:
            print(f"  WARNING: failed to fetch OHLC for {coin_id}: {exc}")
        time.sleep(REQUEST_PAUSE_SECONDS)

    if not all_rows:
        return

    placeholders = ", ".join("?" for _ in coin_ids)
    con.execute(f"DELETE FROM raw.coin_ohlc WHERE coin_id IN ({placeholders})", coin_ids)
    con.executemany(
        "INSERT INTO raw.coin_ohlc VALUES (?, ?, ?, ?, ?, ?, ?)",
        all_rows,
    )
    print(f"Loaded {len(all_rows)} rows into raw.coin_ohlc")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=25, help="Number of top coins by market cap to track")
    parser.add_argument("--days", type=int, default=90, help="CoinGecko OHLC window (granularity is auto-selected by CoinGecko)")
    args = parser.parse_args()

    con = get_connection()
    print(f"Fetching top {args.top} coin ids...")
    snapshot = fetch_market_snapshot(args.top)
    coin_ids = [c["id"] for c in snapshot]

    print(f"Fetching OHLC ({args.days}d window) for {len(coin_ids)} coins...")
    load_ohlc(con, coin_ids, args.days)
    con.close()
    print("Done.")


if __name__ == "__main__":
    main()

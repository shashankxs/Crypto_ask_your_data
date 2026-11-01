"""
Pulls the free, no-API-key Crypto Fear & Greed Index
(https://alternative.me/crypto/fear-and-greed-index/) and lands it as a raw
table in MotherDuck. A second, independently-sourced signal joined against
the CoinGecko price data lets the AI layer answer cross-source questions
like "was sentiment fearful when bitcoin dropped?".

Usage:
    python ingestion/ingest_fear_greed.py --days 90
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_coingecko import get_connection  # noqa: E402 - reuse the shared MotherDuck connection logic

FNG_URL = "https://api.alternative.me/fng/"


def fetch_fear_greed(days: int) -> list[dict]:
    resp = requests.get(FNG_URL, params={"limit": days, "format": "json"}, timeout=30)
    resp.raise_for_status()
    return resp.json().get("data", [])


def load_fear_greed(con: duckdb.DuckDBPyConnection, records: list[dict]) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS raw.fear_greed_index (
            loaded_at TIMESTAMP,
            index_date DATE,
            value INTEGER,
            value_classification VARCHAR
        );
        """
    )
    loaded_at = datetime.now(timezone.utc)
    dates = [datetime.fromtimestamp(int(r["timestamp"]), tz=timezone.utc).date() for r in records]
    if dates:
        placeholders = ", ".join("?" for _ in dates)
        con.execute(f"DELETE FROM raw.fear_greed_index WHERE index_date IN ({placeholders})", dates)

    rows = [
        (loaded_at, d, int(r["value"]), r["value_classification"])
        for r, d in zip(records, dates)
    ]
    con.executemany("INSERT INTO raw.fear_greed_index VALUES (?, ?, ?, ?)", rows)
    print(f"Loaded {len(rows)} rows into raw.fear_greed_index")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90, help="Days of Fear & Greed history to backfill/refresh")
    args = parser.parse_args()

    con = get_connection()
    print(f"Fetching {args.days}d Fear & Greed Index history...")
    records = fetch_fear_greed(args.days)
    load_fear_greed(con, records)
    con.close()
    print("Done.")


if __name__ == "__main__":
    main()

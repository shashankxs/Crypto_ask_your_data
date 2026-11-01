"""
Unit tests for ingestion/ingest_coingecko_ohlc.py — mocked HTTP, in-memory
DuckDB. No network or MotherDuck credentials required.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingestion"))
import ingest_coingecko_ohlc as iohlc  # noqa: E402


def _mock_response(status_code=200, json_data=None, headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.json.return_value = json_data if json_data is not None else []
    if status_code >= 400:
        resp.raise_for_status.side_effect = __import__("requests").HTTPError(response=resp)
    else:
        resp.raise_for_status.side_effect = None
    return resp


def test_fetch_ohlc_parses_rows():
    payload = [[1000, 10.0, 12.0, 9.0, 11.0], [2000, 11.0, 13.0, 10.5, 12.5]]
    with patch("ingest_coingecko_ohlc.requests.get", return_value=_mock_response(json_data=payload)):
        rows = iohlc.fetch_ohlc("bitcoin", 90)
    assert rows == [
        ("bitcoin", 1000, 10.0, 12.0, 9.0, 11.0),
        ("bitcoin", 2000, 11.0, 13.0, 10.5, 12.5),
    ]


def test_fetch_ohlc_retries_on_429():
    payload = [[1000, 10.0, 12.0, 9.0, 11.0]]
    responses = [
        _mock_response(status_code=429, headers={"Retry-After": "0"}),
        _mock_response(json_data=payload),
    ]
    with patch("ingest_coingecko_ohlc.requests.get", side_effect=responses), \
         patch("ingest_coingecko_ohlc.time.sleep") as mock_sleep:
        rows = iohlc.fetch_ohlc("bitcoin", 90)
    assert rows == [("bitcoin", 1000, 10.0, 12.0, 9.0, 11.0)]
    mock_sleep.assert_called_once_with(0)


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    yield connection
    connection.close()


def test_load_ohlc_replaces_existing_rows_for_same_coin(con):
    con.execute("CREATE SCHEMA raw")
    con.execute(
        "CREATE TABLE raw.coin_ohlc (loaded_at TIMESTAMP, coin_id VARCHAR, "
        "candle_time_ms BIGINT, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE)"
    )
    con.execute(
        "INSERT INTO raw.coin_ohlc VALUES (now(), 'bitcoin', 999, 1.0, 1.0, 1.0, 1.0)"
    )
    payload = [[1000, 10.0, 12.0, 9.0, 11.0]]
    with patch("ingest_coingecko_ohlc.requests.get", return_value=_mock_response(json_data=payload)), \
         patch("ingest_coingecko_ohlc.time.sleep"):
        iohlc.load_ohlc(con, ["bitcoin"], 90)

    rows = con.execute("SELECT candle_time_ms FROM raw.coin_ohlc WHERE coin_id = 'bitcoin'").fetchall()
    assert rows == [(1000,)]  # old row (999) replaced, not duplicated


def test_load_ohlc_continues_past_a_failing_coin(con):
    ok_payload = [[1000, 10.0, 12.0, 9.0, 11.0]]

    def fake_get(url, **kwargs):
        if "broken-coin" in url:
            return _mock_response(status_code=500)
        return _mock_response(json_data=ok_payload)

    with patch("ingest_coingecko_ohlc.requests.get", side_effect=fake_get), \
         patch("ingest_coingecko_ohlc.time.sleep"):
        iohlc.load_ohlc(con, ["broken-coin", "bitcoin"], 90)

    rows = con.execute("SELECT coin_id FROM raw.coin_ohlc").fetchall()
    assert rows == [("bitcoin",)]

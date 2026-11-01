"""
Unit tests for ingestion/ingest_coingecko.py — mocked HTTP, in-memory DuckDB.
No network access or MotherDuck credentials required.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingestion"))
import ingest_coingecko as ic  # noqa: E402


def _mock_response(status_code=200, json_data=None, headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.json.return_value = json_data or {}
    if status_code >= 400:
        resp.raise_for_status.side_effect = __import__("requests").HTTPError(response=resp)
    else:
        resp.raise_for_status.side_effect = None
    return resp


# ---------------------------------------------------------------------------
# fetch_market_snapshot
# ---------------------------------------------------------------------------
def test_fetch_market_snapshot_returns_parsed_json():
    sample = [{"id": "bitcoin", "symbol": "btc", "name": "Bitcoin", "current_price": 70000}]
    with patch("ingest_coingecko.requests.get", return_value=_mock_response(json_data=sample)) as mock_get:
        result = ic.fetch_market_snapshot(5)
    assert result == sample
    _, kwargs = mock_get.call_args
    assert kwargs["params"]["per_page"] == 5
    assert kwargs["params"]["order"] == "market_cap_desc"


# ---------------------------------------------------------------------------
# fetch_history — retry/backoff behavior
# ---------------------------------------------------------------------------
def test_fetch_history_parses_prices_volumes_market_caps():
    payload = {
        "prices": [[1000, 100.0], [2000, 110.0]],
        "total_volumes": [[1000, 5.0], [2000, 6.0]],
        "market_caps": [[1000, 50.0], [2000, 55.0]],
    }
    with patch("ingest_coingecko.requests.get", return_value=_mock_response(json_data=payload)):
        rows = ic.fetch_history("bitcoin", 10)
    assert rows == [
        ("bitcoin", 1000, 100.0, 5.0, 50.0),
        ("bitcoin", 2000, 110.0, 6.0, 55.0),
    ]


def test_fetch_history_retries_on_429_then_succeeds():
    payload = {"prices": [[1000, 1.0]], "total_volumes": [[1000, 1.0]], "market_caps": [[1000, 1.0]]}
    responses = [
        _mock_response(status_code=429, headers={"Retry-After": "0"}),
        _mock_response(status_code=200, json_data=payload),
    ]
    with patch("ingest_coingecko.requests.get", side_effect=responses), \
         patch("ingest_coingecko.time.sleep") as mock_sleep:
        rows = ic.fetch_history("bitcoin", 10)
    assert rows == [("bitcoin", 1000, 1.0, 1.0, 1.0)]
    mock_sleep.assert_called_once_with(0)


def test_fetch_history_gives_up_after_max_retries():
    responses = [_mock_response(status_code=429, headers={"Retry-After": "0"})] * ic.MAX_RETRIES
    with patch("ingest_coingecko.requests.get", side_effect=responses), \
         patch("ingest_coingecko.time.sleep"):
        with pytest.raises(Exception):
            ic.fetch_history("bitcoin", 10)


# ---------------------------------------------------------------------------
# load_snapshot / load_history — in-memory DuckDB, real SQL execution
# ---------------------------------------------------------------------------
@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    yield connection
    connection.close()


def test_load_snapshot_inserts_expected_row_shape(con):
    snapshot = [
        {
            "id": "bitcoin", "symbol": "btc", "name": "Bitcoin", "image": "http://x/btc.png",
            "current_price": 70000, "market_cap": 1e12, "market_cap_rank": 1,
            "total_volume": 2e10, "price_change_percentage_24h": 1.2,
            "price_change_percentage_7d_in_currency": -3.4, "circulating_supply": 19e6,
            "ath": 120000, "ath_change_percentage": -40.0,
        }
    ]
    ic.load_snapshot(con, snapshot)
    row = con.execute("SELECT coin_id, symbol, name, image_url, current_price FROM raw.coin_market_snapshot").fetchone()
    assert row == ("bitcoin", "btc", "Bitcoin", "http://x/btc.png", 70000)


def test_load_snapshot_handles_missing_optional_fields(con):
    # Some coins (e.g. new listings) can be missing ath or 7d change fields.
    snapshot = [{"id": "newcoin", "symbol": "new", "name": "New Coin"}]
    ic.load_snapshot(con, snapshot)
    row = con.execute("SELECT coin_id, ath, price_change_pct_7d FROM raw.coin_market_snapshot").fetchone()
    assert row == ("newcoin", None, None)


def test_load_history_replaces_existing_rows_for_same_coins(con):
    con.execute("CREATE SCHEMA raw")
    con.execute(
        "CREATE TABLE raw.coin_price_history "
        "(coin_id VARCHAR, price_timestamp_ms BIGINT, price_usd DOUBLE, "
        "total_volume_usd DOUBLE, market_cap_usd DOUBLE)"
    )
    con.execute("INSERT INTO raw.coin_price_history VALUES ('bitcoin', 999, 1.0, 1.0, 1.0)")

    payload = {"prices": [[1000, 2.0]], "total_volumes": [[1000, 2.0]], "market_caps": [[1000, 2.0]]}
    with patch("ingest_coingecko.requests.get", return_value=_mock_response(json_data=payload)), \
         patch("ingest_coingecko.time.sleep"):
        ic.load_history(con, ["bitcoin"], 10)

    rows = con.execute("SELECT price_timestamp_ms FROM raw.coin_price_history WHERE coin_id = 'bitcoin'").fetchall()
    assert rows == [(1000,)]  # old row (999) replaced, not duplicated


def test_load_history_continues_past_a_failing_coin(con):
    ok_payload = {"prices": [[1000, 1.0]], "total_volumes": [[1000, 1.0]], "market_caps": [[1000, 1.0]]}

    def fake_get(url, **kwargs):
        if "broken-coin" in url:
            return _mock_response(status_code=500)
        return _mock_response(json_data=ok_payload)

    with patch("ingest_coingecko.requests.get", side_effect=fake_get), \
         patch("ingest_coingecko.time.sleep"):
        ic.load_history(con, ["broken-coin", "bitcoin"], 10)

    rows = con.execute("SELECT coin_id FROM raw.coin_price_history").fetchall()
    assert rows == [("bitcoin",)]

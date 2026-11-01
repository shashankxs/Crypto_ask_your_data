# Ask Your Crypto Data

A small, end-to-end analytics pipeline that lets you ask plain-English
questions about live cryptocurrency markets and get back a SQL-backed
answer with a chart.

Built to demonstrate the full modern data engineering lifecycle in one
project: **ingestion → cloud warehouse → modeled + tested transformations →
scheduled orchestration → an LLM query layer on top.**

## Architecture

```
CoinGecko API
     │
     ▼
ingestion/ingest_coingecko.py  ──► raw.coin_market_snapshot
  (Python, scheduled via            raw.coin_price_history
   GitHub Actions cron)                   │
                                           ▼
                                   dbt (dbt-duckdb adapter)
                                   ├─ staging: cleaned/typed views
                                   └─ marts:   dim_coin
                                               fct_coin_latest_snapshot
                                               fct_coin_price_daily
                                   (schema + relationship tests on every build)
                                           │
                                           ▼
                              MotherDuck (cloud-hosted DuckDB)
                                           │
                                           ▼
                        app/app.py — Streamlit "Ask Your Data" UI
                        Claude converts a plain-English question into a
                        read-only SELECT against the marts, runs it, and
                        renders a table + chart.
```

Ingestion and dbt both run on a 6-hour GitHub Actions schedule against the
same MotherDuck database the Streamlit app reads from, so the whole system
stays in sync without any manual steps.

## Why this project

- **Ingestion**: a real external API (CoinGecko), with retries/rate-limit handling.
- **Warehouse**: cloud-hosted DuckDB (MotherDuck) — same SQL engine dbt and the app both speak, swappable for Snowflake/BigQuery by changing `profiles.yml`.
- **Transformation**: dbt staging → marts with documented models and 10+ data tests (not-null, uniqueness, referential integrity) that run on every scheduled build.
- **Orchestration**: GitHub Actions cron runs ingestion + `dbt build` every 6 hours.
- **AI layer**: an LLM text-to-SQL interface constrained to a read-only, schema-scoped prompt with query validation before execution — a natural-language analytics experience, not just a dashboard.

## Setup

1. **MotherDuck**: sign up free at [motherduck.com](https://motherduck.com), grab a token.
2. **Anthropic**: get an API key at [console.anthropic.com](https://console.anthropic.com).
3. Copy `.env.example` to `.env` and fill in both.
4. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
5. Run the ingestion job once to seed data:
   ```
   python ingestion/ingest_coingecko.py --top 25 --history-days 90
   ```
6. Build and test the dbt models:
   ```
   cd dbt_project
   dbt deps --profiles-dir .
   dbt build --profiles-dir .
   ```
7. Launch the app:
   ```
   streamlit run app/app.py
   ```

### Scheduling in GitHub Actions

Add `MOTHERDUCK_TOKEN` as a repository secret. The workflow in
`.github/workflows/ingest.yml` then refreshes data and rebuilds/tests the
dbt models every 6 hours automatically.

### Deploying the app

Push to GitHub, then deploy `app/app.py` on [Streamlit Community Cloud](https://streamlit.io/cloud)
for a free public demo link — set `MOTHERDUCK_TOKEN` and `ANTHROPIC_API_KEY`
as Streamlit secrets.

## Sample questions

- "Which 5 coins gained the most in the last 24 hours?"
- "Show bitcoin's daily price and 7-day moving average for the last 30 days."
- "What's the average daily return for the top 10 coins by market cap?"
- "Which coins are furthest below their all-time high right now?"

## Project layout

```
ingestion/          Python ingestion script (CoinGecko → raw MotherDuck tables)
dbt_project/         dbt models: staging/ (cleaned views), marts/ (fact/dim tables + tests)
app/app.py           Streamlit "Ask Your Data" interface with Claude text-to-SQL
.github/workflows/   Scheduled ingestion + dbt build/test
```

# Ask Your Crypto Data

A small, end-to-end analytics pipeline that lets you ask plain-English
questions about live cryptocurrency markets and get back a SQL-backed
answer with a chart.

Built to demonstrate the full modern data engineering lifecycle in one
project: **two independently-sourced ingestions → cloud warehouse → modeled,
tested, documented transformations → CI + scheduled orchestration → a
hardened LLM query layer → a polished UI.**

<!-- TODO: add a screenshot or GIF of the running app here -->
<!-- ![screenshot](docs/screenshot.png) -->

**Live demo:** _add your Streamlit Community Cloud URL here once deployed_

## Architecture

```
CoinGecko API                          alternative.me Fear & Greed API
     │                                              │
     ▼                                              ▼
ingest_coingecko.py                        ingest_fear_greed.py
(retry/backoff on 429s)                    (free, no API key)
     │                                              │
     ▼                                              ▼
raw.coin_market_snapshot              raw.fear_greed_index
raw.coin_price_history                              │
     │                                              │
     └──────────────────┬───────────────────────────┘
                         ▼
                 dbt (dbt-duckdb adapter)
                 ├─ staging/  cleaned, deduped, typed views (sourced via
                 │             dbt `source()`, with freshness checks)
                 └─ marts/    dim_coin
                              fct_coin_latest_snapshot
                              fct_coin_price_daily
                              fct_market_sentiment_daily  (joins both sources)
                 38 data tests: not-null, uniqueness, referential integrity,
                 accepted ranges, a custom no-future-dates check
                         │
                         ▼
              MotherDuck (cloud-hosted DuckDB)
                         │
                         ▼
         app/app.py — Streamlit "Ask Your Data" UI
         An LLM (Groq by default) converts a plain-English question into a
         read-only SELECT against the marts, validated against an
         adversarial-tested guardrail, executed, and rendered as a
         formatted table + chart.
```

**Orchestration & CI** (`.github/workflows/`):
- `ingest.yml` — refreshes both data sources and rebuilds/tests dbt models every 6 hours, with failure alerting
- `ci.yml` — on every pull request: unit tests (pytest, no secrets/network needed), then a full `dbt build` against a **throwaway, auto-torn-down** MotherDuck database, so a model change is validated before merge without ever touching production data
- `dbt-docs.yml` — publishes the dbt lineage graph + catalog to GitHub Pages on every push to `main`

## Engineering decisions (the "why")

- **MotherDuck over Snowflake/BigQuery**: same DuckDB SQL dbt and the app both already speak, zero infra to provision, free tier is enough for a project this size. Swapping to Snowflake is a `profiles.yml` change, not a rewrite.
- **Groq over OpenAI/Anthropic for the AI layer**: free tier with no credit card, which matters for a side project — and it forced a harder requirement: the SQL-safety guardrail (`validate_sql`) has to hold up regardless of which model is behind it, including a local open-weight reasoning model that occasionally returns CTEs or burns its token budget on hidden reasoning. Anthropic Claude is supported as a drop-in alternative via `LLM_PROVIDER=anthropic`.
- **An accumulating `dim_coin`** (union of every coin_id ever seen in either extract) instead of "today's top 25": the market-cap ranking and the price-history extract refresh independently, so a coin can drop out of the top 25 between runs. A naive "latest snapshot only" dimension silently broke referential integrity with historical fact rows — caught by `dbt build` failing in practice, not by inspection.
- **Validating the SQL guardrail adversarially, not just functionally**: an LLM is an untrusted component. `tests/test_sql_validator.py` throws prompt-injection and SQL-injection-style payloads at `validate_sql` (stacked statements, disguised DROP/DELETE, comment-hidden keywords, LLM preamble text) rather than only testing the happy path.
- **A second, independently-sourced dataset** (Fear & Greed Index) joined on date, not just more CoinGecko fields — proves the pipeline can do real dimensional modeling across sources, and lets the AI layer answer cross-source questions a single-API project can't.

## Setup

1. **MotherDuck**: sign up free at [motherduck.com](https://motherduck.com). In the app, go to the gear icon → **Access Tokens** → **Create Token**.
2. **Groq** (free, no credit card): get a key at [console.groq.com/keys](https://console.groq.com/keys).
3. Copy `.env.example` to `.env` and fill in `MOTHERDUCK_TOKEN` and `GROQ_API_KEY`.
4. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
5. Seed both data sources:
   ```
   python ingestion/ingest_coingecko.py --top 25 --history-days 90
   python ingestion/ingest_fear_greed.py --days 90
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

### Running the test suite

```
pip install pytest requests-mock
python -m pytest tests/ -v
```
36 tests: ingestion logic against mocked HTTP (no live API/credentials needed), plus the adversarial SQL-validator suite.

### CI/CD in GitHub Actions

Add `MOTHERDUCK_TOKEN` as a repository secret (**Settings → Secrets and variables → Actions**). Optionally add a `SLACK_WEBHOOK_URL` repository **variable** for failure alerts. Then:
- Every PR triggers `ci.yml` — unit tests + a full pipeline run against an isolated, auto-deleted database (`crypto_db_ci_pr<N>`).
- Every push to `main` triggers `dbt-docs.yml`, publishing the lineage graph to GitHub Pages (enable **Settings → Pages → Source: GitHub Actions** once).
- Every 6 hours, `ingest.yml` refreshes production data.

### Deploying the app

Push to GitHub, then deploy `app/app.py` on [Streamlit Community Cloud](https://streamlit.io/cloud)
for a free public demo link — set `MOTHERDUCK_TOKEN` and `GROQ_API_KEY`
as Streamlit secrets.

## Sample questions

- "Which 5 coins gained the most in the last 24 hours?"
- "Show bitcoin's daily price and 7-day moving average for the last 30 days."
- "Which coins are furthest below their all-time high right now?"
- "Was market sentiment fearful on the days with the biggest price drops?"

## Project layout

```
ingestion/
  ingest_coingecko.py    CoinGecko → raw tables (retry/backoff on rate limits)
  ingest_fear_greed.py   alternative.me Fear & Greed Index → raw table
dbt_project/
  models/staging/        cleaned, deduped, typed views; dbt sources + freshness checks
  models/marts/          dim_coin, fct_coin_latest_snapshot, fct_coin_price_daily,
                          fct_market_sentiment_daily — 38 data tests total
  tests/                 custom singular test (no future-dated rows)
app/app.py                Streamlit "Ask Your Data" UI with Groq/Claude text-to-SQL
tests/
  test_ingestion.py       pytest, mocked HTTP, in-memory DuckDB
  test_sql_validator.py   adversarial tests for the SQL safety guardrail
.github/workflows/
  ingest.yml              scheduled ingestion + dbt build + failure alert
  ci.yml                  PR-triggered unit tests + isolated dbt build
  dbt-docs.yml            publishes dbt lineage graph to GitHub Pages
```

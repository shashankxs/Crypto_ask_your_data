# Ask Your Crypto Data

A premium-feeling crypto analytics dashboard: ask plain-English questions
about live cryptocurrency markets and get back a SQL-backed answer with a
chart, browse a Bloomberg-style technical chart (candlesticks, moving
averages, Bollinger Bands, RSI/MACD, comparison mode), and see market
sentiment on a live gauge.

Built to demonstrate the full modern data engineering lifecycle in one
project: **three independently-sourced ingestions → cloud warehouse →
modeled, tested, documented transformations → CI + scheduled orchestration
→ a hardened LLM query layer → a polished, data-dense UI.**

<!-- TODO: add a screenshot or GIF of the running app here -->
<!-- ![screenshot](docs/screenshot.png) -->

**Live demo:** _add your Streamlit Community Cloud URL here once deployed_

**dbt docs / lineage graph:** https://shashankxs.github.io/Crypto_ask_your_data/

## Architecture

```
CoinGecko API (3 endpoints)                    alternative.me Fear & Greed API
     │                                                       │
     ├─ ingest_coingecko.py        (markets + daily price history)
     ├─ ingest_coingecko_ohlc.py   (candlestick data)
     │                                                       │
     ▼                                                       ▼
raw.coin_market_snapshot                           raw.fear_greed_index
raw.coin_price_history
raw.coin_ohlc
     │                                                       │
     └───────────────────────────┬───────────────────────────┘
                                  ▼
                          dbt (dbt-duckdb adapter)
                          ├─ staging/  cleaned, deduped, typed views (sourced via
                          │             dbt `source()`, with freshness checks)
                          └─ marts/    dim_coin (accumulating dimension)
                                       fct_coin_latest_snapshot
                                       fct_coin_price_daily
                                       fct_coin_ohlc
                                       fct_market_sentiment_daily  (joins 2 sources)
                          59 data tests: not-null, uniqueness, referential integrity,
                          accepted ranges, custom OHLC/date sanity checks
                                  │
                                  ▼
                       MotherDuck (cloud-hosted DuckDB)
                                  │
                                  ▼
          app/app.py — "Ask Your Crypto Data" dashboard (Streamlit)
          ├─ Technical chart: candlestick/line/area, MA7/25/50, Bollinger
          │  Bands, volume subplot, collapsible RSI/MACD, comparison mode
          ├─ Fear & Greed gauge, KPI cards with embedded sparklines,
          │  scrolling ticker tape, trading-grid market table
          └─ Natural-language query: an LLM (Groq by default) converts a
             question into a read-only SELECT, validated against an
             adversarial-tested guardrail, executed, and rendered
```

**Orchestration & CI** (`.github/workflows/`):
- `ingest.yml` — refreshes all three sources and rebuilds/tests dbt models every 6 hours, with failure alerting
- `ci.yml` — on every pull request: unit tests (pytest, no secrets/network needed), then a full `dbt build` against a **throwaway, auto-torn-down** MotherDuck database, so a model change is validated before merge without ever touching production data
- `dbt-docs.yml` — publishes the dbt lineage graph + catalog to GitHub Pages on every push to `main`

## Engineering decisions (the "why")

- **MotherDuck over Snowflake/BigQuery**: same DuckDB SQL dbt and the app both already speak, zero infra to provision, free tier is enough for a project this size. Swapping to Snowflake is a `profiles.yml` change, not a rewrite.
- **Groq over OpenAI/Anthropic for the AI layer**: free tier with no credit card, which matters for a side project — and it forced a harder requirement: the SQL-safety guardrail (`validate_sql`) has to hold up regardless of which model is behind it, including a local open-weight reasoning model that occasionally returns CTEs or burns its token budget on hidden reasoning. Anthropic Claude is supported as a drop-in alternative via `LLM_PROVIDER=anthropic`.
- **An accumulating `dim_coin`** (union of every coin_id ever seen across extracts) instead of "today's top 25": the market-cap ranking and the price-history extract refresh independently, so a coin can drop out of the top 25 between runs. A naive "latest snapshot only" dimension silently broke referential integrity with historical fact rows — caught by `dbt build` failing in practice, not by inspection.
- **Validating the SQL guardrail adversarially, not just functionally**: an LLM is an untrusted component. `tests/test_sql_validator.py` throws prompt-injection and SQL-injection-style payloads at `validate_sql` (stacked statements, disguised DROP/DELETE, comment-hidden keywords, LLM preamble text) rather than only testing the happy path.
- **Two more independently-sourced datasets** (Fear & Greed Index, OHLC candlestick data) joined/modeled alongside the base price feed — proves the pipeline does real dimensional modeling across sources, not just more fields from one API call.
- **Candlesticks are real, not fabricated**: CoinGecko's free OHLC endpoint auto-selects candle width by the requested day window (~4-day candles at our 90-day window — a real API constraint, not a choice). Rather than draw fake wicks from single daily price points for shorter ranges, the 7D/30D chart views fall back to the existing daily price line and say so in the UI. See `ingestion/ingest_coingecko_ohlc.py`.
- **No new chart/indicator dependencies**: moving averages, Bollinger Bands, RSI, and MACD are hand-rolled in ~5 lines of pandas each (`app/indicators.py`) instead of pulling in `ta`/`pandas-ta`, some of which wrap TA-Lib's C extension — a notoriously painful install on Windows/CI runners for formulas this small. Table/card sparklines are hand-rolled inline SVG (`app/sparkline.py`) rather than dozens of embedded Plotly mini-charts, which is both lighter and faster to render. The Cmd+K command-palette shortcut is a ~15-line inline JS snippet (`components.inject_command_palette_shortcut`) instead of a `streamlit-shortcuts` package — the component iframe can reach `window.parent.document` because Streamlit serves everything same-origin, so the dependency wasn't worth it for this.

## Setup

1. **MotherDuck**: sign up free at [motherduck.com](https://motherduck.com). In the app, go to the gear icon → **Access Tokens** → **Create Token**.
2. **Groq** (free, no credit card): get a key at [console.groq.com/keys](https://console.groq.com/keys).
3. Copy `.env.example` to `.env` and fill in `MOTHERDUCK_TOKEN` and `GROQ_API_KEY`.
4. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
5. Seed all three data sources:
   ```
   python ingestion/ingest_coingecko.py --top 25 --history-days 90
   python ingestion/ingest_fear_greed.py --days 90
   python ingestion/ingest_coingecko_ohlc.py --top 25 --days 90
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
53 tests: ingestion logic against mocked HTTP (no live API/credentials needed), the adversarial SQL-validator suite, and the technical-indicator/sparkline formulas.

### CI/CD in GitHub Actions

Add `MOTHERDUCK_TOKEN` as a repository secret (**Settings → Secrets and variables → Actions → Repository secrets** — not Environment secrets). Optionally add a `SLACK_WEBHOOK_URL` repository **variable** for failure alerts. Then:
- Every PR triggers `ci.yml` — unit tests + a full pipeline run against an isolated, auto-deleted database (`crypto_db_ci_pr<N>`).
- Every push to `main` triggers `dbt-docs.yml`, publishing the lineage graph to GitHub Pages (enable **Settings → Pages → Source: GitHub Actions** once).
- Every 6 hours, `ingest.yml` refreshes production data.

### Deploying the app

Deploy `app/app.py` on [Streamlit Community Cloud](https://streamlit.io/cloud)
for a free public demo link. The app has its own lean `app/requirements.txt`
(no dbt dependencies) so the Cloud build stays fast. Set `MOTHERDUCK_TOKEN`,
`GROQ_API_KEY`, and `LLM_PROVIDER` in the app's Streamlit secrets.

## Using the dashboard

- **Ticker tape** at the top scrolls the top 15 coins' live price/24h change (hover to pause).
- **Technical chart**: pick a coin, a time range (7D/30D/90D/ALL), a chart type, and toggle MA7/25/50, Bollinger Bands, RSI, and MACD from the Indicators panel. Export the chart as PNG via the toolbar camera icon, or the underlying data as CSV.
- **Comparison mode** (collapsed by default): overlay 2+ coins normalized to % change from the range start.
- **Fear & Greed gauge**: the latest sentiment reading, color-banded from fear to greed.
- **Market table**: zebra-striped, with coin logos and a 14-day sparkline per coin.
- **Ask Anything**: press <kbd>⌘K</kbd>/<kbd>Ctrl+K</kbd> or click a suggested question, type your own, and get a table + chart back.

Sample questions:
- "Which 5 coins gained the most in the last 24 hours?"
- "Show bitcoin's daily price and 7-day moving average for the last 30 days."
- "Which coins are furthest below their all-time high right now?"
- "Was market sentiment fearful on the days with the biggest price drops?"

## Project layout

```
ingestion/
  ingest_coingecko.py      CoinGecko markets + daily price history (retry/backoff on rate limits)
  ingest_coingecko_ohlc.py CoinGecko candlestick (OHLC) data
  ingest_fear_greed.py     alternative.me Fear & Greed Index
dbt_project/
  models/staging/          cleaned, deduped, typed views; dbt sources + freshness checks
  models/marts/            dim_coin, fct_coin_latest_snapshot, fct_coin_price_daily,
                            fct_coin_ohlc, fct_market_sentiment_daily — 59 data tests total
  tests/                   custom singular tests (no future-dated rows, OHLC high/low sanity)
app/
  app.py                   main entry / page layout orchestration
  data.py                  all DuckDB/MotherDuck queries (cached)
  ai.py                    natural-language-to-SQL + the SQL safety guardrail
  charts.py                Plotly figure builders (technical chart, gauge, comparison)
  indicators.py            MA / Bollinger / RSI / MACD, hand-rolled in pandas
  sparkline.py             inline SVG sparklines (KPI cards, table cells)
  components.py            ticker tape, stat cards, trading-grid table, Cmd+K shortcut
  theme.py                 palette + CSS + Plotly template
tests/
  test_ingestion.py         pytest, mocked HTTP, in-memory DuckDB
  test_ingestion_ohlc.py    pytest, mocked HTTP, in-memory DuckDB
  test_sql_validator.py     adversarial tests for the SQL safety guardrail
  test_indicators.py        MA/Bollinger/RSI/MACD formula correctness
  test_sparkline.py         SVG sparkline edge cases (empty/flat/single-value series)
.github/workflows/
  ingest.yml                scheduled ingestion (all 3 sources) + dbt build + failure alert
  ci.yml                    PR-triggered unit tests + isolated dbt build
  dbt-docs.yml              publishes dbt lineage graph to GitHub Pages
```

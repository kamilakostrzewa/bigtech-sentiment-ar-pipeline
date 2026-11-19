# Sentiment & Market Impact ETL Pipeline

An automated Python ETL pipeline designed to collect financial news, intraday stock prices, and company fundamentals for Big Tech equities (`NVDA`, `AAPL`, `MSFT`, `GOOGL`, `TSLA`), score news sentiment, and analyze short-term market-adjusted **Abnormal Returns (AR)** across post-publication time windows (`15m`, `30m`, `1h`, `4h`).

*(Developed as the empirical implementation for a B.Sc. Thesis in Informatics and Econometrics at Poznań University of Economics and Business, 2026).*

---

## Project Structure

```text
bigtech-sentiment-ar-pipeline/
│
├── main.py               # Main ETL pipeline orchestrator & CLI entrypoint
├── scheduler.py          # Automated 2-hour cloud job scheduler
├── requirements.txt      # Python dependencies
├── .env.example          # Environment variables template
│
└── src/
    ├── news.py           # NewsAPI ingestion, domain blocklist & semantic filtering
    ├── finance.py        # Intraday market data (yfinance) & fundamentals (Finnhub)
    ├── sentiment.py      # VADER sentiment scoring
    └── database.py       # MongoDB Atlas connection & idempotent upsert persistence
```

---

## Data Sources

| Source | Data Collected | Frequency / Strategy |
| :--- | :--- | :--- |
| **NewsAPI** (`/v2/everything`) | Press article headlines, descriptions & metadata | Every 2 hours via scheduler (`pageSize=50`) |
| **Yahoo Finance** (`yfinance`) | 1-minute & daily OHLCV stock quotes | Fetched once per unique publication date (buffered) |
| **SPY ETF** (`yfinance`) | S&P 500 market benchmark intraday returns | Fetched alongside target equities for AR calculation |
| **Finnhub REST API** | P/E ratio, Market Cap, EPS & Earnings Surprise | Fetched per company on each pipeline execution |

---

## Key Engineering Mechanisms

- **Two-Stage Semantic Filtering (`src/news.py`):** Filters out non-financial noise (e.g., PyPI package releases, product deals, lifestyle/celebrity articles) using a curated `BLOCKED_DOMAINS` list, company-specific `EXCLUSION_PHRASES`, and a regex-based **Sector Sieve** matching domain anchor keywords (`TECH`, `FINANCE`, `AUTO`).
- **Timezone & Market Session Synchronization (`src/finance.py`):** Converts ISO 8601 `UTC` publication timestamps to New York exchange time (`America/New_York` / `EST/EDT`) via Python's built-in `zoneinfo` module and classifies NYSE/NASDAQ trading states (`Market Open`, `Next Market Open`, `Post-Market`, `Weekend`, `No Data`).
- **In-Memory Daily Buffering (`main.py`):** Caches 1-minute equity, `SPY`, and daily session summary DataFrames in memory (`daily_buffers`, `spy_buffers`, `daily_summary_buffers`) to avoid redundant Yahoo Finance requests for articles published on the same trading day.
- **Market-Adjusted Abnormal Return (AR):** Isolates company-specific news reaction from broad market movements by computing:
  $$AR_{it} = R_{it} - R_{mt}$$
  across four intraday windows (**T+15m, T+30m, T+1h, T+4h**) whenever both $T_0$ and $T+X$ fall within active trading hours.
- **Idempotent Persistence & Cloud Automation (`src/database.py`, `scheduler.py`):** Stores enriched records in **MongoDB Atlas** (`stock_analysis.news_sentiment`) using `update_one(..., upsert=True)` keyed by article URL, orchestrated continuously every 2 hours on **PythonAnywhere** (staying within NewsAPI's 100 requests/day free-tier limit).

---

## Installation & Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment variables:**
   Copy `.env.example` to `.env` and fill in your credentials:
   ```env
   NEWS_API_KEY=your_newsapi_key
   FINNHUB_KEY=your_finnhub_key
   MONGO_URI=mongodb+srv://user:password@cluster.mongodb.net/
   ```

---

## Usage

**Run once for default Big Tech tickers (`NVDA`, `AAPL`, `MSFT`, `GOOGL`, `TSLA`):**
```bash
python main.py
```

**Run for custom ticker/company pairs via CLI arguments:**
```bash
python main.py NVDA:Nvidia TSLA:Tesla
```

**Run continuous 2-hour scheduler:**
```bash
python scheduler.py
```

---

## Sample MongoDB Document Schema

```json
{
  "_id": "69ebc33c717058f057a38580",
  "url": "https://www.livemint.com/companies/meta-microsoft-look-to-trim-workfor...",
  "ticker": "MSFT",
  "company_name": "Microsoft",
  "title": "Meta, Microsoft Look to Trim Workforces Amid Heavy AI Spending",
  "description": "Meta Platforms Inc. and Microsoft Corp. have taken drastic action...",
  "sentiment": 0.4767,
  "tags": ["AI"],
  "publishedAt": "2026-04-23T18:53:50.000+00:00",
  "lag_hours": 24.5,
  "market_status": "Market Open",
  "impact_windows": {
    "15m": { "ar": 0.0648, "stock_change": 0.0337, "p0": 414.94, "p1": 415.08, "diff": 0.14 },
    "30m": { "ar": 0.1932, "stock_change": 0.2314, "p0": 414.94, "p1": 415.90, "diff": 0.96 },
    "1h":  { "ar": 0.4031, "stock_change": 0.3904, "p0": 414.94, "p1": 416.56, "diff": 1.62 },
    "4h":  { "ar": 0.7775, "stock_change": 0.4753, "p0": 414.94, "p1": 416.92, "diff": 1.98 }
  },
  "day_summary": {
    "day_open": 419.89,
    "day_close": 415.75,
    "day_change_pct": -0.99
  },
  "pro": {
    "fundamentals": { "pe": 26.44, "cap": 3209208.2 },
    "earnings": { "surprise_pct": 2.6149, "actual": 4.14, "estimate": 4.0345, "period": "2025-12-31" }
  }
}
```

---

## Known Limitations

- **NewsAPI Free Tier:** Enforces a 24-hour publication delay and a 100 requests/day quota, making the pipeline suited for retrospective dataset construction rather than real-time trading.
- **Yahoo Finance (`yfinance`):** Relies on an unofficial data feed (1-minute bars limited to the last ~8 days) and may require browser-impersonation headers (`curl_cffi`) in cloud environments.
- **Lexicon-Based Sentiment (VADER):** Optimized for general/social media text rather than domain-specific financial jargon; replacing VADER with **FinBERT** or an LLM-based classifier is a natural next step.
- **Off-Hours Publications:** Articles published during weekends, pre-market, or post-market hours store an empty `impact_windows` object (`{}`) because intraday abnormal returns cannot be measured while the exchange is closed.

import os
import logging
import sys
import argparse
import time
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import warnings

from src.database import get_mongo_collection, save_news, close_mongo
from src.finance import get_stock_data_buffer, get_price_from_buffer, get_day_summary, get_finnhub_data
from src.news import fetch_news, is_relevant, is_blocked_domain, get_news_tags
from src.sentiment import get_sentiment

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler("app.log"), logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)
warnings.simplefilter(action='ignore', category=FutureWarning)
load_dotenv()


def validate_env():
    required = ["NEWS_API_KEY", "FINNHUB_KEY", "MONGO_URI"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        logger.error(f"Brakujące klucze w .env: {missing}")
        sys.exit(1)


def run_pipeline(pairs):
    validate_env()
    news_key = os.getenv("NEWS_API_KEY")
    finnhub_key = os.getenv("FINNHUB_KEY")
    mongo_uri = os.getenv("MONGO_URI")

    col = get_mongo_collection(mongo_uri)
    if col is None:
        return

    session_stats = {}
    logger.info("Uruchomiono potok danych")

    try:
        for item in pairs:
            if ":" not in item:
                continue
            ticker, company = item.split(":", 1)
            ticker = ticker.upper()
            session_stats[ticker] = {"new": 0, "duplicates": 0, "filtered": 0}

            logger.info("\n" + "=" * 70)
            logger.info(f"Spółka: {ticker} | {company}")
            logger.info("=" * 70)

            time.sleep(2)
            pro = get_finnhub_data(ticker, finnhub_key)

            f_pe = pro.get('fundamentals', {}).get('pe', 'brak')
            f_cap = pro.get('fundamentals', {}).get('cap', 'brak')
            f_surp = pro.get('earnings', {}).get('surprise_pct', 'brak')
            f_actual = pro.get('earnings', {}).get('actual', 'brak')
            f_estimate = pro.get('earnings', {}).get('estimate', 'brak')
            f_period = pro.get('earnings', {}).get('period', 'brak')

            logger.info(f"P/E: {f_pe} | Cap: {f_cap} mln USD | Earnings Surprise: {f_surp}%")
            logger.info(f"Ostatni raport: {f_period} | EPS actual: {f_actual} | EPS estimate: {f_estimate}")
            logger.info("-" * 70)

            articles = fetch_news(company, news_key)
            daily_buffers = {}
            spy_buffers = {}
            daily_summary_buffers = {}

            for i, art in enumerate(articles, 1):
                url = art.get('url')
                title = art.get('title', '')
                desc = art.get('description', '') or ''
                cont = art.get('content', '') or ''
                pub_at_str = art.get('publishedAt')

                if not title or is_blocked_domain(url):
                    session_stats[ticker]["filtered"] += 1
                    logger.warning(f"Odrzucono (zablokowana domena / brak tytułu): {url}")
                    continue

                if not is_relevant(ticker, company, title, desc, cont):
                    session_stats[ticker]["filtered"] += 1
                    logger.warning(f"Odrzucono (szum): {title[:70]}")
                    continue

                pub_utc = datetime.strptime(pub_at_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                lag = round((datetime.now(timezone.utc) - pub_utc).total_seconds() / 3600, 1)
                day_key = pub_utc.strftime('%Y-%m-%d')
                clean_desc = " ".join(desc.split()) if desc else ""

                score, sentiment_label = get_sentiment(title, desc)
                tags = get_news_tags(title, desc)

                if day_key not in daily_buffers:
                    logger.info(f"Pobieranie danych giełdowych: {day_key}")
                    daily_buffers[day_key] = get_stock_data_buffer(ticker, pub_utc)
                    spy_buffers[day_key] = get_stock_data_buffer("SPY", pub_utc)

                if day_key not in daily_summary_buffers:
                    daily_summary_buffers[day_key] = get_day_summary(ticker, pub_utc)

                p0 = get_price_from_buffer(daily_buffers[day_key], pub_utc)
                spy0 = get_price_from_buffer(spy_buffers[day_key], pub_utc)
                day_ctx = daily_summary_buffers[day_key]

                time_windows = {"15m": 0.25, "30m": 0.5, "1h": 1.0, "4h": 4.0}
                impacts = {}

                for label, hours in time_windows.items():
                    p_f = get_price_from_buffer(daily_buffers[day_key], pub_utc + timedelta(hours=hours))
                    s_f = get_price_from_buffer(spy_buffers[day_key], pub_utc + timedelta(hours=hours))

                    if (p0['status'] == "Market Open" and p_f['status'] == "Market Open"
                            and spy0['status'] == "Market Open" and s_f['status'] == "Market Open"
                            and p0['price'] > 0 and spy0['price'] > 0):

                        stock_ret = (p_f['price'] - p0['price']) / p0['price']
                        mkt_ret = (s_f['price'] - spy0['price']) / spy0['price']

                        impacts[label] = {
                            "ar": round((stock_ret - mkt_ret) * 100, 4),
                            "stock_change": round(stock_ret * 100, 4),
                            "p0": p0['price'],
                            "p1": p_f['price'],
                            "diff": round(p_f['price'] - p0['price'], 2)
                        }

                is_dup = col.find_one({"url": url})
                status_label = "duplikat" if is_dup else "nowy"

                if is_dup:
                    session_stats[ticker]["duplicates"] += 1
                else:
                    session_stats[ticker]["new"] += 1

                emoji = '🟢' if score > 0.05 else '🔴' if score < -0.05 else '⚪'

                logger.info(f"[{status_label.upper()}] {ticker} #{i}")
                logger.info(f"Tagi:      {tags}")
                logger.info(f"Tytuł:     {title}")
                logger.info(f"Data:      {pub_at_str} (lag: {lag}h)")
                logger.info(f"Sentyment: {score} {emoji} | {sentiment_label}")

                if impacts:
                    imp_1h = impacts.get('1h', {})
                    if imp_1h:
                        logger.info(f"Impact 1h: {imp_1h['diff']} USD ({imp_1h['p0']} -> {imp_1h['p1']})")
                    ar_line = " | ".join([f"{k}: {v['ar']}%" for k, v in impacts.items()])
                    logger.info(f"AR vs SPY: {ar_line}")
                else:
                    logger.warning(f"Brak danych rynkowych (status T0: {p0['status']})")

                if day_ctx:
                    logger.info(f"Sesja:     Open {day_ctx['day_open']} | Close {day_ctx['day_close']} ({day_ctx['day_change_pct']}%)")

                logger.info(f"Opis:      {clean_desc[:160]}")
                logger.info(f"Link:      {url}")
                logger.info("-" * 70)

                if not is_dup:
                    save_news(col, url, {
                        "ticker": ticker,
                        "company_name": company,
                        "title": title,
                        "description": clean_desc,
                        "sentiment": score,
                        "tags": tags,
                        "impact_windows": impacts,
                        "market_status": p0['status'],
                        "day_summary": day_ctx,
                        "publishedAt": pub_utc,
                        "lag_hours": lag,
                        "pro": pro,
                        "url": url
                    })

        logger.info("\n" + "=" * 70)
        logger.info("Podsumowanie sesji")
        logger.info("=" * 70)
        total_new = 0
        for tick, s in session_stats.items():
            logger.info(f"{tick}: nowe: {s['new']} | duplikaty: {s['duplicates']} | odrzucone: {s['filtered']}")
            total_new += s['new']
        logger.info(f"Łącznie dodano do bazy: {total_new} rekordów")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"Błąd podczas pracy systemu: {e}")
    finally:
        close_mongo()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pairs", nargs="*")
    args = parser.parse_args()
    input_pairs = args.pairs if args.pairs else [
        "NVDA:Nvidia",
        "AAPL:Apple",
        "MSFT:Microsoft",
        "GOOGL:Google",
        "TSLA:Tesla"
    ]
    run_pipeline(input_pairs)
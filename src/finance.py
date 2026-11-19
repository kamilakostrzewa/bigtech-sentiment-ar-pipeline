import yfinance as yf
import requests
from datetime import timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import logging

logger = logging.getLogger(__name__)


def get_stock_data_buffer(symbol, date_utc):
    tz_ny = ZoneInfo('America/New_York')
    date_ny = date_utc.astimezone(tz_ny)
    day_str = date_ny.strftime('%Y-%m-%d')
    next_day = (date_ny + timedelta(days=1)).strftime('%Y-%m-%d')
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=day_str, end=next_day, interval="1m", raise_errors=False)
        if isinstance(df, pd.DataFrame) and not df.empty:
            df.index = df.index.tz_localize(None)
            return df
    except Exception as e:
        logger.error(f"Błąd pobierania danych Yahoo ({symbol}, {day_str}): {e}")
    return None


def get_price_from_buffer(df, target_utc):
    tz_ny = ZoneInfo('America/New_York')
    target_ny = target_utc.astimezone(tz_ny).replace(tzinfo=None)

    if target_ny.weekday() >= 5:
        return {"status": "Weekend", "price": 0.0}

    if df is None or df.empty:
        return {"status": "No Data", "price": 0.0}

    if target_ny.hour < 9 or (target_ny.hour == 9 and target_ny.minute < 30):
        try:
            return {"price": round(float(df['Close'].iloc[0]), 2), "status": "Next Market Open"}
        except Exception as e:
            logger.warning(f"Błąd odczytu ceny otwarcia: {e}")
            return {"status": "No Data", "price": 0.0}
    if target_ny.hour >= 16:
        return {"status": "Post-Market", "price": 0.0}

    try:
        idx = df.index.get_indexer([target_ny], method='nearest')[0]
        return {"price": round(float(df['Close'].iloc[idx]), 2), "status": "Market Open"}
    except Exception as e:
        logger.warning(f"Błąd odczytu ceny z bufora: {e}")
        return {"status": "Error", "price": 0.0}


def get_day_summary(ticker_symbol, target_datetime_utc):
    tz_ny = ZoneInfo('America/New_York')
    target_ny = target_datetime_utc.astimezone(tz_ny)
    day_str = target_ny.strftime('%Y-%m-%d')
    try:
        data = yf.Ticker(ticker_symbol).history(start=day_str, period="1d", raise_errors=False)
        if not data.empty:
            d_o = float(data['Open'].iloc[0])
            d_c = float(data['Close'].iloc[-1])
            return {
                "day_open": round(d_o, 2),
                "day_close": round(d_c, 2),
                "day_change_pct": round(((d_c - d_o) / d_o) * 100, 2)
            }
    except Exception as e:
        logger.warning(f"Błąd pobierania podsumowania dnia ({ticker_symbol}, {day_str}): {e}")
    return None


def get_finnhub_data(symbol, api_key):
    if not api_key:
        return {}
    res = {'fundamentals': {}, 'earnings': {}}
    headers = {'X-Finnhub-Token': api_key}

    try:
        r = requests.get(
            f"https://finnhub.io/api/v1/stock/metric?symbol={symbol}&metric=all",
            headers=headers,
            timeout=10
        )
        if r.status_code == 200:
            m = r.json().get('metric', {})
            res['fundamentals'] = {
                "pe": m.get('peExclExtraTTM'),
                "cap": m.get('marketCapitalization')
            }
    except Exception as e:
        logger.warning(f"Błąd pobierania metryk Finnhub ({symbol}): {e}")

    try:
        r = requests.get(
            f"https://finnhub.io/api/v1/stock/earnings?symbol={symbol}",
            headers=headers,
            timeout=10
        )
        if r.status_code == 200:
            e = r.json()
            if isinstance(e, list) and len(e) > 0:
                latest = e[0]
                res['earnings'] = {
                    "surprise_pct": latest.get('surprisePercent'),
                    "actual": latest.get('actual'),
                    "estimate": latest.get('estimate'),
                    "period": latest.get('period')
                }
    except Exception as e:
        logger.warning(f"Błąd pobierania earnings Finnhub ({symbol}): {e}")

    return res
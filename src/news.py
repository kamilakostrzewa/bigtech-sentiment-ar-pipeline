import re
import requests
import logging

logger = logging.getLogger(__name__)

# Domeny które publikują śmieci – ogłoszenia, plotki, pakiety PyPI
BLOCKED_DOMAINS = [
    "pypi.org",
    "ozbargain.com.au",
    "dealnews.com",
    "9to5toys.com",
    "gossiplankanews.com",
    "ladbible.com",
    "madshrimps.be",
    "woot.com",
    "consent.yahoo.com",
    "softpedia.com",
    "drivers.softpedia.com"
]

# Frazy jednoznacznie wskazujące że news nie dotyczy spółki giełdowej
EXCLUSION_PHRASES = {
    "TSLA": ["tesla coil", "nikola tesla", "tesla museum", "found in his", "found in her",
             "body was found", "arrested", "killing", "murder"],
    "AAPL": ["apple pie", "apple cider", "apple orchard", "apple recipe",
             "back in stock", "free shipping", "prime shipped", "% off", "refurb"],
    "GOOGL": ["how to watch", "live stream"],
    "NVDA": ["nvidia shield", "geforce rtx review", "gaming review", "graphics driver",
             "geforce driver", "driver version", "for windows", "softpedia"],
    "MSFT": ["how to watch", "live stream", "how to fix", "tutorial", "solitaire"]
}


def fetch_news(query_name, api_key, page_size=50):
    url = 'https://newsapi.org/v2/everything'
    headers = {'X-Api-Key': api_key}
    params = {
        'q': f'"{query_name}"',
        'searchIn': 'title,description',
        'sortBy': 'publishedAt',
        'language': 'en',
        'pageSize': page_size
    }
    try:
        res = requests.get(url, params=params, headers=headers, timeout=10)
        return res.json().get('articles', []) if res.status_code == 200 else []
    except Exception as e:
        logger.warning(f"Błąd pobierania newsów dla '{query_name}': {e}")
        return []


def is_blocked_domain(url):
    if not url:
        return True
    return any(domain in url for domain in BLOCKED_DOMAINS)


def is_relevant(ticker, query_name, title, desc, cont):
    full_text = (title + " " + (desc or "")).lower()

    def has_word(text, word):
        return bool(re.search(rf'\b{re.escape(word)}\b', text))

    # Wyklucz pakiety PyPI i podobne techniczne wpisy
    version_pattern = r'^\S+ \d+\.\d+[\.\d]*'
    if re.match(version_pattern, title):
        return False

    # Wyklucz znane fałszywe frazy
    for phrase in EXCLUSION_PHRASES.get(ticker.upper(), []):
        if phrase in full_text:
            return False

    sectors = {
        "TECH": [
            "ai", "chip", "software", "iphone", "gpu", "cloud", "data", "tech",
            "semiconductor", "processor", "server", "cybersecurity", "search",
            "streaming", "hardware", "robot"
        ],
        "FINANCE": [
            "stock", "market", "shares", "earnings", "quarter", "revenue", "profit",
            "nasdaq", "invest", "dividend", "buyback", "forecast", "guidance",
            "analyst", "upgrade", "downgrade", "ipo", "valuation", "ceo",
            "lawsuit", "contract"
        ],
        "AUTO": [
            "ev", "electric", "vehicle", "car", "autonomous", "autopilot", "factory",
            "charging", "supercharger", "fsd", "gigafactory", "recall", "delivery",
            "battery"
        ]
    }

    anchors = {
        "NVDA": sectors["TECH"] + sectors["FINANCE"],
        "AAPL": sectors["TECH"] + sectors["FINANCE"],
        "TSLA": sectors["AUTO"] + sectors["FINANCE"],
        "MSFT": sectors["TECH"] + sectors["FINANCE"],
        "GOOGL": sectors["TECH"] + sectors["FINANCE"]
    }

    valid_keywords = anchors.get(ticker.upper(), sectors["FINANCE"])
    name_match = has_word(full_text, query_name.lower()) or has_word(full_text, ticker.lower())
    has_context = any(has_word(full_text, word) for word in valid_keywords)
    return name_match and has_context


def get_news_tags(title, desc):
    text = (title + " " + (desc or "")).lower()
    tags = []
    kw = {
        "AI": ["ai", "llm"],
        "Finance": ["earnings", "revenue", "profit", "nasdaq", "invest", "shares",
                    "dividend", "buyback", "forecast", "guidance", "analyst",
                    "upgrade", "downgrade", "valuation"],
        "Hardware": ["chip", "iphone", "gpu", "semiconductor", "processor", "server"],
        "Auto": ["ev", "electric", "vehicle", "car", "autonomous", "recall", "delivery",
                 "gigafactory", "fsd", "supercharger"],
        "Cloud": ["cloud", "server", "cybersecurity", "streaming", "software"]
    }
    for tag, keys in kw.items():
        if any(re.search(rf'\b{re.escape(k)}\b', text) for k in keys):
            tags.append(tag)
    return tags if tags else ["General"]
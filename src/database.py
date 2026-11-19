import logging
from pymongo import MongoClient

logger = logging.getLogger(__name__)
_client = None


def get_mongo_collection(uri):
    global _client
    try:
        if _client is None:
            logger.info("Łączenie z MongoDB Atlas...")
            _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            _client.admin.command('ping')
            logger.info("Połączenie z MongoDB nawiązane.")
        return _client['stock_analysis']['news_sentiment']
    except Exception as e:
        logger.error(f"Błąd połączenia z MongoDB: {e}")
        return None


def save_news(collection, url, data):
    if collection is not None:
        try:
            collection.update_one({"url": url}, {"$set": data}, upsert=True)
        except Exception as e:
            logger.error(f"Błąd zapisu do MongoDB (url: {url}): {e}")


def close_mongo():
    global _client
    if _client:
        _client.close()
        _client = None
        logger.info("Połączenie z MongoDB zamknięte.")

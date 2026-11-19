import logging
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = logging.getLogger(__name__)
analyzer = SentimentIntensityAnalyzer()


def get_sentiment(title, desc):
    try:
        text = f"{title}. {desc}"
        score = analyzer.polarity_scores(text)['compound']

        if score > 0.05:
            status = "POSITIVE"
        elif score < -0.05:
            status = "NEGATIVE"
        else:
            status = "NEUTRAL"

        return score, status
    except Exception as e:
        logger.warning(f"Błąd analizy sentymentu: {e}")
        return 0.0, "NEUTRAL"

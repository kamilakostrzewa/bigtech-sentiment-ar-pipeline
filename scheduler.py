import schedule
import time
import logging
from main import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler("app.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

PAIRS = [
    "NVDA:Nvidia",
    "AAPL:Apple",
    "MSFT:Microsoft",
    "GOOGL:Google",
    "TSLA:Tesla"
]


def job():
    logger.info("Scheduler: uruchamianie potoku danych")
    run_pipeline(PAIRS)
    logger.info("Scheduler: zakończono, następne uruchomienie za 2 godziny")


schedule.every(2).hours.do(job)

logger.info("Scheduler uruchomiony – interwał: co 2 godziny")
job()

while True:
    schedule.run_pending()
    time.sleep(60)

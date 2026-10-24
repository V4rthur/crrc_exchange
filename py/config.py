import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "etl_log.txt"

LOG_DIR.mkdir(exist_ok=True)

load_dotenv(BASE_DIR / ".env")

CBU_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"
CBU_HISTORICAL_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/all/{date}/"
SOURCE_SYSTEM = "CBU_JSON"
REQUEST_TIMEOUT = 30  # seconds

# Retry policy for API calls (network errors, 429 and 5xx responses)
HTTP_RETRIES = 3
HTTP_BACKOFF = 2  # seconds; doubles after each failed attempt

# If the pipeline missed some days, the next run fetches them too (up to this many)
MAX_CATCHUP_DAYS = 90

# Rotating log file: 1 MB per file, 5 old files kept
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 5


SQL_SERVER = os.getenv("SQL_SERVER", "localhost")
SQL_DATABASE = os.getenv("SQL_DATABASE", "CurrencyETL")
SQL_DRIVER = os.getenv("SQL_DRIVER", "ODBC Driver 17 for SQL Server")

connection_url = URL.create(
    "mssql+pyodbc",
    query={
        "odbc_connect": (
            f"DRIVER={{{SQL_DRIVER}}};"
            f"SERVER={SQL_SERVER};"
            f"DATABASE={SQL_DATABASE};"
            f"Trusted_Connection=yes;"
            f"TrustServerCertificate=yes;"
        )
    },
)

def get_engine():
    """Return a SQLAlchemy engine for CurrencyETL database."""
    return create_engine(connection_url, fast_executemany=True)


RAW_TABLE = "raw_currency_rates"
CLEAN_TABLE = "clean_currency_rates"


def get_logger(name):
    """Return a logger that writes to the console and the rotating log file."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
        )
        fh = RotatingFileHandler(
            LOG_FILE,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        fh.setFormatter(fmt)
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(fh)
        logger.addHandler(ch)
    return logger


# ---------------------------------------------------------
# Telegram alerts
# ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

# Notify on successful runs too? False = only failures (recommended)
TELEGRAM_NOTIFY_SUCCESS = False

if __name__ == "__main__":
    from sqlalchemy import text
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT DB_NAME() AS current_db, @@VERSION AS version"))
            row = result.fetchone()
            print(f"✅ Connected to database: {row.current_db}")
            print(f"   Server info: {row.version[:60]}...")
    except Exception as e:
        print(f"❌ Connection failed: {e}")

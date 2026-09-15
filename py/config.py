import os
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
SOURCE_SYSTEM = "CBU_JSON"
REQUEST_TIMEOUT = 30  # seconds


SQL_SERVER = "localhost"
SQL_DATABASE = "CurrencyETL"
SQL_DRIVER = "ODBC Driver 17 for SQL Server"

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

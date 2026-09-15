"""
Extract step: fetch EUR-based rates from Frankfurter (ECB) API
and load them into market_currency_rates.

Handles both latest-day fetch and historical backfill in one script.
"""

import sys
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import logging
from datetime import date, timedelta

import pandas as pd
import requests

from config import LOG_FILE, REQUEST_TIMEOUT, get_engine

# ---------------------------------------------------------
# Config
# ---------------------------------------------------------
FRANKFURTER_BASE = "https://api.frankfurter.dev/v1"
SOURCE_SYSTEM = "FRANKFURTER_ECB"
TARGET_CURRENCIES = "USD,GBP,JPY,CHF,CNY"
BASE_CURRENCY = "EUR"
MARKET_TABLE = "market_currency_rates"

# ---------------------------------------------------------
# Logger
# ---------------------------------------------------------
def setup_logger():
    logger = logging.getLogger("market_extract")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
        )
        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setFormatter(fmt)
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(fh)
        logger.addHandler(ch)
    return logger


logger = setup_logger()


# ---------------------------------------------------------
# Fetch functions
# ---------------------------------------------------------
def fetch_latest():
    """Fetch today's rates from Frankfurter."""
    url = f"{FRANKFURTER_BASE}/latest?base={BASE_CURRENCY}&symbols={TARGET_CURRENCIES}"
    logger.info(f"Fetching latest from {url}")
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return _parse_response(response.json())


def fetch_range(start_date: date, end_date: date):
    """Fetch a date range from Frankfurter (max 365 days per call)."""
    url = (
        f"{FRANKFURTER_BASE}/"
        f"{start_date.strftime('%Y-%m-%d')}.."
        f"{end_date.strftime('%Y-%m-%d')}"
        f"?base={BASE_CURRENCY}&symbols={TARGET_CURRENCIES}"
    )
    logger.info(f"Fetching range from {url}")
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    data = response.json()
    rows = []
    for rate_date_str, currency_rates in data.get("rates", {}).items():
        for quote, rate in currency_rates.items():
            rows.append({
                "base_currency": BASE_CURRENCY,
                "quote_currency": quote,
                "rate": rate,
                "rate_date": rate_date_str,
                "source_system": SOURCE_SYSTEM,
            })
    logger.info(f"Parsed {len(rows)} rate records across date range")
    return rows


def _parse_response(data):
    """Parse a single-date Frankfurter response."""
    rate_date_str = data["date"]
    rows = []
    for quote, rate in data["rates"].items():
        rows.append({
            "base_currency": BASE_CURRENCY,
            "quote_currency": quote,
            "rate": rate,
            "rate_date": rate_date_str,
            "source_system": SOURCE_SYSTEM,
        })
    logger.info(f"Parsed {len(rows)} rate records for {rate_date_str}")
    return rows


# ---------------------------------------------------------
# Load (idempotent via DELETE + INSERT)
# ---------------------------------------------------------
def load_to_market(rows):
    """Load into market_currency_rates. Idempotent by (base, quote, date)."""
    if not rows:
        logger.warning("No rows to load")
        return 0

    df = pd.DataFrame(rows)
    engine = get_engine()
    rate_dates = df["rate_date"].unique().tolist()

    from sqlalchemy import text
    with engine.begin() as conn:
        # Delete existing rows for these dates
        placeholders = ",".join([f":d{i}" for i in range(len(rate_dates))])
        params = {f"d{i}": d for i, d in enumerate(rate_dates)}
        result = conn.execute(
            text(f"DELETE FROM dbo.{MARKET_TABLE} WHERE rate_date IN ({placeholders})"),
            params,
        )
        logger.info(f"Deleted {result.rowcount} existing rows for {len(rate_dates)} date(s)")

        # Insert new rows
        df.to_sql(MARKET_TABLE, conn, if_exists="append", index=False, chunksize=200)
        logger.info(f"Inserted {len(df)} rows into {MARKET_TABLE}")

    return len(df)


# ---------------------------------------------------------
# Main entry points
# ---------------------------------------------------------
def main():
    """Daily extract — fetches latest rates only."""
    try:
        rows = fetch_latest()
        count = load_to_market(rows)
        logger.info(f"[OK] Market extract completed. {count} rows loaded.")
        return count
    except Exception as e:
        logger.exception(f"[FAIL] Market extract failed: {e}")
        raise


def backfill(days_back: int = 90):
    """One-time historical backfill."""
    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)
    logger.info(f"Backfilling from {start_date} to {end_date}")

    rows = fetch_range(start_date, end_date)
    count = load_to_market(rows)
    logger.info(f"✅ Backfill completed. {count} rows loaded.")
    return count


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "backfill":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 90
        backfill(days)
    else:
        main()
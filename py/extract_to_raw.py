import json
import time
from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy import text

from config import (
    CBU_HISTORICAL_URL,
    CBU_URL,
    MAX_CATCHUP_DAYS,
    RAW_TABLE,
    SOURCE_SYSTEM,
    get_engine,
    get_logger,
)
from http_utils import get_json

REQUEST_DELAY = 0.3  # seconds between historical requests

logger = get_logger("extract")


def fetch_cbu_data():
    """Fetch the latest currency rates from the CBU JSON endpoint."""
    logger.info(f"Fetching data from {CBU_URL}")
    data = get_json(CBU_URL, logger)

    if not isinstance(data, list) or len(data) == 0:
        raise ValueError("CBU response is empty or not a list")

    logger.info(f"Received {len(data)} currency records")
    return data


def fetch_cbu_date(target_date):
    """Fetch CBU rates for a specific date. Returns [] if CBU has nothing."""
    url = CBU_HISTORICAL_URL.format(date=target_date.strftime("%Y-%m-%d"))
    data = get_json(url, logger)
    if not isinstance(data, list):
        return []
    return data


def build_rows(data):
    """Convert CBU JSON records into rows for raw_currency_rates."""
    rows = []
    for record in data:
        rows.append({
            "ccy": record.get("Ccy"),
            "ccy_nm_uz": record.get("CcyNm_UZ"),
            "ccy_nm_ru": record.get("CcyNm_RU"),
            "ccy_nm_en": record.get("CcyNm_EN"),
            "nominal": int(record["Nominal"]) if record.get("Nominal") else None,
            "rate": float(record["Rate"]) if record.get("Rate") else None,
            "diff": float(record["Diff"]) if record.get("Diff") else None,
            "date": datetime.strptime(record["Date"], "%d.%m.%Y").date()
                    if record.get("Date") else None,
            "source_system": SOURCE_SYSTEM,
            "raw_json": json.dumps(record, ensure_ascii=False),
        })
    return rows


def get_loaded_dates():
    """Return the set of rate dates already present in raw_currency_rates."""
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text(f"SELECT DISTINCT [date] FROM dbo.{RAW_TABLE} WHERE [date] IS NOT NULL")
        )
        return {row[0] for row in result}


def keep_new_rows(rows, loaded_dates):
    """
    Drop rows whose rate date is already in raw, and repeats within the batch.
    CBU answers weekend dates with the previous rate, so repeats are normal.
    """
    seen = set()
    new_rows = []
    for row in rows:
        key = (row["ccy"], row["date"])
        if row["date"] in loaded_dates or key in seen:
            continue
        seen.add(key)
        new_rows.append(row)
    return new_rows


def fetch_missed_days(loaded_dates):
    """
    Fetch the days between the last loaded rate date and today, so a run
    that was skipped (machine off, API down) doesn't leave a permanent gap.
    """
    if not loaded_dates:
        return []

    today = date.today()
    start = max(loaded_dates) + timedelta(days=1)
    earliest = today - timedelta(days=MAX_CATCHUP_DAYS)
    if start < earliest:
        logger.warning(
            f"Last loaded date is older than {MAX_CATCHUP_DAYS} days — "
            f"catching up from {earliest} only. Run backfill_history.py for the rest."
        )
        start = earliest

    missed = []
    current = start
    while current < today:
        missed.extend(fetch_cbu_date(current))
        current += timedelta(days=1)
        time.sleep(REQUEST_DELAY)

    if start < today:
        logger.info(
            f"Catch-up: fetched {len(missed)} records for {start}..{today - timedelta(days=1)}"
        )
    return missed


def load_to_raw(data, loaded_dates=frozenset()):
    """Insert currency records into raw_currency_rates, skipping dates already loaded."""
    rows = keep_new_rows(build_rows(data), loaded_dates)

    if not rows:
        logger.info(f"No new rate dates — {RAW_TABLE} is already up to date")
        return 0

    df = pd.DataFrame(rows)
    engine = get_engine()

    df.to_sql(
        RAW_TABLE,
        engine,
        if_exists="append",
        index=False,
        chunksize=100,
    )

    logger.info(
        f"Inserted {len(df)} rows into {RAW_TABLE} "
        f"({df['date'].nunique()} new rate date(s))"
    )
    return len(df)


def main():
    try:
        loaded_dates = get_loaded_dates()
        data = fetch_missed_days(loaded_dates) + fetch_cbu_data()
        count = load_to_raw(data, loaded_dates)
        logger.info(f"✅ Extract completed. {count} rows loaded.")
        return count
    except Exception as e:
        logger.exception(f"❌ Extract failed: {e}")
        raise


if __name__ == "__main__":
    main()

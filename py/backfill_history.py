import sys
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import json
import logging
import time
from datetime import date, timedelta

import pandas as pd
import requests

from config import (
    LOG_FILE,
    RAW_TABLE,
    REQUEST_TIMEOUT,
    SOURCE_SYSTEM,
    get_engine,
)

DAYS_BACK = 90                       
CBU_HISTORICAL_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/all/{date}/"
REQUEST_DELAY = 0.3                  

# ---------------------------------------------------------
# Logger
# ---------------------------------------------------------
def setup_logger():
    logger = logging.getLogger("backfill")
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


def fetch_date(target_date):
    """Fetch CBU rates for a specific date."""
    url = CBU_HISTORICAL_URL.format(date=target_date.strftime("%Y-%m-%d"))
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list) or len(data) == 0:
            return []
        return data
    except Exception as e:
        logger.warning(f"Failed to fetch {target_date}: {e}")
        return []


def build_rows(data):
    from datetime import datetime
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


def main():
    logger.info("=" * 60)
    logger.info(f"BACKFILL START | Fetching last {DAYS_BACK} days")
    logger.info("=" * 60)

    end_date = date.today()
    start_date = end_date - timedelta(days=DAYS_BACK)

    all_rows = []
    empty_dates = 0
    fetched_dates = 0

    current = start_date
    while current <= end_date:
        data = fetch_date(current)
        if data:
            rows = build_rows(data)
            all_rows.extend(rows)
            fetched_dates += 1
            logger.info(f"  {current}: {len(rows)} records")
        else:
            empty_dates += 1
        current += timedelta(days=1)
        time.sleep(REQUEST_DELAY)

    logger.info(f"Total dates fetched: {fetched_dates}")
    logger.info(f"Empty responses (likely weekends/holidays): {empty_dates}")
    logger.info(f"Total records collected: {len(all_rows)}")

    if not all_rows:
        logger.warning("No data collected. Nothing to insert.")
        return

    # Bulk insert
    df = pd.DataFrame(all_rows)
    engine = get_engine()
    df.to_sql(RAW_TABLE, engine, if_exists="append", index=False, chunksize=500)
    logger.info(f"✅ Inserted {len(df)} rows into {RAW_TABLE}")
    logger.info("Now run: python transform_to_clean.py")


if __name__ == "__main__":
    main()
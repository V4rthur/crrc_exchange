import sys
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import time
from datetime import date, timedelta

from config import get_logger
from extract_to_raw import (
    REQUEST_DELAY,
    fetch_cbu_date,
    get_loaded_dates,
    load_to_raw,
)

DAYS_BACK = 90

logger = get_logger("backfill")


def main(days_back=DAYS_BACK):
    logger.info("=" * 60)
    logger.info(f"BACKFILL START | Fetching last {days_back} days")
    logger.info("=" * 60)

    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)

    all_data = []
    empty_dates = 0
    fetched_dates = 0

    current = start_date
    while current <= end_date:
        try:
            data = fetch_cbu_date(current)
        except Exception as e:
            logger.warning(f"Failed to fetch {current}: {e}")
            data = []
        if data:
            all_data.extend(data)
            fetched_dates += 1
            logger.info(f"  {current}: {len(data)} records")
        else:
            empty_dates += 1
        current += timedelta(days=1)
        time.sleep(REQUEST_DELAY)

    logger.info(f"Total dates fetched: {fetched_dates}")
    logger.info(f"Empty or failed responses: {empty_dates}")
    logger.info(f"Total records collected: {len(all_data)}")

    # Only rate dates that aren't in raw yet are inserted, so re-running is safe
    count = load_to_raw(all_data, get_loaded_dates())
    logger.info(f"✅ Backfill completed. {count} new rows loaded.")
    logger.info("Now run: python transform_to_clean.py")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else DAYS_BACK)

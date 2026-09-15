import json
import logging
from datetime import datetime

import pandas as pd
import requests

from config import (
    CBU_URL,
    LOG_FILE,
    RAW_TABLE,
    REQUEST_TIMEOUT,
    SOURCE_SYSTEM,
    get_engine,
)

def setup_logger():
    logger = logging.getLogger("extract")
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


def fetch_cbu_data():
    """Fetch currency rates from the CBU JSON endpoint."""
    logger.info(f"Fetching data from {CBU_URL}")
    response = requests.get(CBU_URL, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()

    if not isinstance(data, list) or len(data) == 0:
        raise ValueError("CBU response is empty or not a list")

    logger.info(f"Received {len(data)} currency records")
    return data


def load_to_raw(data):
    """Insert each currency record into raw_currency_rates."""
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

    df = pd.DataFrame(rows)
    engine = get_engine()

    df.to_sql(
        RAW_TABLE,
        engine,
        if_exists="append",
        index=False,
        chunksize=100,
    )

    logger.info(f"Inserted {len(df)} rows into {RAW_TABLE}")
    return len(df)


def main():
    try:
        data = fetch_cbu_data()
        count = load_to_raw(data)
        logger.info(f"✅ Extract completed. {count} rows loaded.")
        return count
    except Exception as e:
        logger.exception(f"❌ Extract failed: {e}")
        raise


if __name__ == "__main__":
    main()
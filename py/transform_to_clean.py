import sys
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from sqlalchemy import text

from config import (
    RAW_TABLE,
    CLEAN_TABLE,
    get_engine,
    get_logger,
)

logger = get_logger("transform")


def read_raw():
    """Read all rows from raw_currency_rates."""
    engine = get_engine()
    query = f"""
        SELECT ccy, ccy_nm_en, nominal, rate, diff, [date], loaded_at
        FROM dbo.{RAW_TABLE}
    """
    df = pd.read_sql(query, engine)
    logger.info(f"Read {len(df)} rows from {RAW_TABLE}")
    return df


def transform(df):
    """Clean and transform raw data for the clean layer."""
    initial_rows = len(df)

    # Drop rows with missing critical fields
    df = df.dropna(subset=["ccy", "date", "rate", "nominal"])
    dropped = initial_rows - len(df)
    if dropped > 0:
        logger.warning(f"Dropped {dropped} rows with null critical fields")

    # Deduplicate: keep latest loaded_at per (ccy, date)
    df = df.sort_values("loaded_at").drop_duplicates(
        subset=["ccy", "date"], keep="last"
    )
    logger.info(f"After deduplication: {len(df)} rows")

    # Rename columns to match clean table
    df = df.rename(columns={
        "ccy": "currency_code",
        "ccy_nm_en": "currency_name",
        "rate": "rate_uzs",
        "diff": "diff_uzs",
        "date": "rate_date",
    })

    # Derived fields
    df["rate_per_unit"] = df["rate_uzs"] / df["nominal"]

    df["change_direction"] = "No Change"
    df.loc[df["diff_uzs"] > 0, "change_direction"] = "Increased"
    df.loc[df["diff_uzs"] < 0, "change_direction"] = "Decreased"

    df["is_appreciated"] = (df["diff_uzs"] > 0).astype(int)
    df["is_depreciated"] = (df["diff_uzs"] < 0).astype(int)

    # Drop loaded_at (SQL default fills it on insert)
    df = df.drop(columns=["loaded_at"])

    # Reorder to match table
    df = df[[
        "currency_code",
        "currency_name",
        "nominal",
        "rate_uzs",
        "diff_uzs",
        "rate_date",
        "rate_per_unit",
        "change_direction",
        "is_appreciated",
        "is_depreciated",
    ]]

    logger.info(f"Transformed {len(df)} rows")
    return df

# ---------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------
def compute_anomalies(df):
    """
    Detect unusual currency movements using:
        1. Z-score of daily diff vs currency's 30-day history
        2. Deviation from 7-day moving average
    
    Flags is_anomaly=1 if either signal exceeds threshold.
    """
    ZSCORE_THRESHOLD = 2.0     # |z| > 2 = beyond 95% confidence
    MA_DEV_THRESHOLD = 1.5     # 1.5% deviation from 7-day MA
    ZSCORE_WINDOW = 30
    MA_WINDOW = 7

    # Sort so rolling windows compute in the right order
    df = df.sort_values(["currency_code", "rate_date"]).reset_index(drop=True)

    # Group per currency for rolling calculations
    grouped = df.groupby("currency_code", group_keys=False)

    # Z-score of diff_uzs (rolling 30-day window)
    df["diff_rolling_mean"] = grouped["diff_uzs"].transform(
        lambda s: s.rolling(ZSCORE_WINDOW, min_periods=5).mean()
    )
    df["diff_rolling_std"] = grouped["diff_uzs"].transform(
        lambda s: s.rolling(ZSCORE_WINDOW, min_periods=5).std()
    )
    df["diff_zscore"] = (
        (df["diff_uzs"] - df["diff_rolling_mean"]) / df["diff_rolling_std"]
    ).round(4)

    # 7-day moving average of rate_uzs
    df["ma7_rate"] = grouped["rate_uzs"].transform(
        lambda s: s.rolling(MA_WINDOW, min_periods=3).mean()
    ).round(6)

    # % deviation from moving average
    df["ma7_deviation_pct"] = (
        ((df["rate_uzs"] - df["ma7_rate"]) / df["ma7_rate"]) * 100
    ).round(4)

    # Anomaly flags
    zscore_hit = df["diff_zscore"].abs() > ZSCORE_THRESHOLD
    ma_hit = df["ma7_deviation_pct"].abs() > MA_DEV_THRESHOLD

    df["is_anomaly"] = (zscore_hit | ma_hit).fillna(False).astype(int)

    # Human-readable reason
    def reason(row):
        reasons = []
        if pd.notna(row["diff_zscore"]) and abs(row["diff_zscore"]) > ZSCORE_THRESHOLD:
            reasons.append(f"Z-score {row['diff_zscore']:.2f}")
        if pd.notna(row["ma7_deviation_pct"]) and abs(row["ma7_deviation_pct"]) > MA_DEV_THRESHOLD:
            reasons.append(f"{row['ma7_deviation_pct']:.2f}% vs MA7")
        return "; ".join(reasons) if reasons else None

    df["anomaly_reason"] = df.apply(reason, axis=1)

    # Drop helper columns not stored in DB
    df = df.drop(columns=["diff_rolling_mean", "diff_rolling_std"])

    anomaly_count = df["is_anomaly"].sum()
    logger.info(f"Detected {anomaly_count} anomalies across dataset")

    return df

def load_to_clean(df):
    """
    Load into clean_currency_rates using DELETE + INSERT for idempotency.
    Re-runs on the same day safely replace existing rows for those dates.
    """
    if df.empty:
        logger.warning("No rows to load")
        return 0

    engine = get_engine()
    rate_dates = df["rate_date"].unique().tolist()

    with engine.begin() as conn:
        # Delete existing rows for these dates
        placeholders = ",".join([f":d{i}" for i in range(len(rate_dates))])
        params = {f"d{i}": d for i, d in enumerate(rate_dates)}
        result = conn.execute(
            text(f"DELETE FROM dbo.{CLEAN_TABLE} WHERE rate_date IN ({placeholders})"),
            params,
        )
        logger.info(
            f"Deleted {result.rowcount} existing rows for {len(rate_dates)} date(s)"
        )

        # Insert transformed rows
        df.to_sql(
            CLEAN_TABLE,
            conn,
            if_exists="append",
            index=False,
            chunksize=100,
        )
        logger.info(f"Inserted {len(df)} rows into {CLEAN_TABLE}")

    return len(df)


def main():
    try:
        raw_df = read_raw()
        clean_df = transform(raw_df)
        clean_df = compute_anomalies(clean_df)   # <-- NEW LINE
        count = load_to_clean(clean_df)
        logger.info(f"✅ Transform completed. {count} rows loaded to clean.")
        return count
    except Exception as e:
        logger.exception(f"❌ Transform failed: {e}")
        raise


if __name__ == "__main__":
    main()
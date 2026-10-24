"""
Compute daily divergence between CBU implied cross-rates and market rates.

CBU implied EUR/USD = (EUR-UZS) / (USD-UZS)
Market EUR/USD      = from Frankfurter (ECB)
Divergence          = market - implied

Positive divergence  = CBU overvalues UZS vs market
Negative divergence  = CBU undervalues UZS vs market
"""

import sys
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from sqlalchemy import text

from config import get_engine, get_logger

# ---------------------------------------------------------
# Config
# ---------------------------------------------------------
DIVERGENCE_TABLE = "currency_divergence"
QUOTE_CURRENCIES = ["USD", "GBP", "JPY", "CHF", "CNY"]
BASE_CURRENCY = "EUR"

logger = get_logger("divergence")


# ---------------------------------------------------------
# Read source data
# ---------------------------------------------------------
def read_cbu_rates():
    """Read CBU rates for EUR and target currencies from clean layer."""
    engine = get_engine()
    query = """
        SELECT rate_date, currency_code, rate_per_unit
        FROM dbo.clean_currency_rates
        WHERE currency_code IN ('EUR', 'USD', 'GBP', 'JPY', 'CHF', 'CNY')
    """
    df = pd.read_sql(query, engine)
    logger.info(f"Read {len(df)} CBU rate rows")
    return df


def read_market_rates():
    """Read market rates from Frankfurter layer."""
    engine = get_engine()
    query = """
        SELECT rate_date, quote_currency, rate
        FROM dbo.market_currency_rates
        WHERE base_currency = 'EUR'
    """
    df = pd.read_sql(query, engine)
    logger.info(f"Read {len(df)} market rate rows")
    return df


# ---------------------------------------------------------
# Compute divergence
# ---------------------------------------------------------
def compute(cbu_df, market_df):
    """
    Pivot CBU data to compute EUR-based cross-rates,
    then join with market rates and compute divergence.
    """
    # Pivot CBU: rows = date, columns = currency, values = rate_per_unit
    cbu_pivot = cbu_df.pivot_table(
        index="rate_date",
        columns="currency_code",
        values="rate_per_unit",
        aggfunc="first",
    ).reset_index()

    # Ensure EUR column exists — required for cross-rate math
    if "EUR" not in cbu_pivot.columns:
        raise ValueError("EUR not found in CBU data — cannot compute cross-rates")

    # Compute CBU-implied EUR/X cross-rates
    # If UZS per 1 EUR = 14000 and UZS per 1 USD = 12800,
    # then implied EUR/USD = 14000 / 12800 = 1.09375
    rows = []
    for quote in QUOTE_CURRENCIES:
        if quote not in cbu_pivot.columns:
            logger.warning(f"CBU doesn't have {quote} — skipping")
            continue
        subset = cbu_pivot[["rate_date", "EUR", quote]].copy()
        subset["cbu_implied_rate"] = subset["EUR"] / subset[quote]
        subset["quote_currency"] = quote
        subset["base_currency"] = BASE_CURRENCY
        rows.append(subset[["rate_date", "base_currency", "quote_currency", "cbu_implied_rate"]])

    cbu_implied = pd.concat(rows, ignore_index=True)
    logger.info(f"Computed {len(cbu_implied)} CBU-implied cross-rate values")

    # Prepare market data for join
    market_df = market_df.rename(columns={
        "rate": "market_rate",
        "quote_currency": "quote_currency",
    })
    market_df["base_currency"] = BASE_CURRENCY

    # Inner join — only dates present in both sources
    merged = pd.merge(
        cbu_implied,
        market_df[["rate_date", "base_currency", "quote_currency", "market_rate"]],
        on=["rate_date", "base_currency", "quote_currency"],
        how="inner",
    )

    # Compute divergence
    merged["absolute_divergence"] = (merged["market_rate"] - merged["cbu_implied_rate"]).round(6)
    merged["pct_divergence"] = (
        (merged["absolute_divergence"] / merged["market_rate"]) * 100
    ).round(4)

    logger.info(f"Final divergence records: {len(merged)}")
    return merged


# ---------------------------------------------------------
# Load
# ---------------------------------------------------------
def load(df):
    """Load into currency_divergence table with truncate-and-reload."""
    if df.empty:
        logger.warning("No rows to load")
        return 0

    engine = get_engine()
    with engine.begin() as conn:
        # Simple approach: truncate and reload
        # (Analytical table, no history preservation needed — always current)
        conn.execute(text(f"TRUNCATE TABLE dbo.{DIVERGENCE_TABLE}"))
        logger.info(f"Truncated {DIVERGENCE_TABLE}")

        df.to_sql(DIVERGENCE_TABLE, conn, if_exists="append", index=False, chunksize=500)
        logger.info(f"Inserted {len(df)} rows into {DIVERGENCE_TABLE}")

    return len(df)


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------
def main():
    try:
        cbu_df = read_cbu_rates()
        market_df = read_market_rates()
        divergence_df = compute(cbu_df, market_df)
        count = load(divergence_df)
        logger.info(f"✅ Divergence computed. {count} rows loaded.")
        return count
    except Exception as e:
        logger.exception(f"❌ Divergence computation failed: {e}")
        raise


if __name__ == "__main__":
    main()
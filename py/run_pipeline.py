import notifier
from config import TELEGRAM_NOTIFY_SUCCESS
import socket

import sys
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import logging
import os
import time
import traceback
from datetime import datetime

from config import LOG_FILE
import extract_to_raw
import transform_to_clean
import audit


# ---------------------------------------------------------
# Logger
# ---------------------------------------------------------
def setup_logger():
    logger = logging.getLogger("pipeline")
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
# Detect trigger source
# ---------------------------------------------------------
def detect_trigger():
    """Guess whether run was triggered by scheduler or user."""
    # Task Scheduler sets specific env vars
    if os.environ.get("USERNAME") and not sys.stdin.isatty():
        return "scheduler"
    return "manual"


# ---------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------
def run():
    start_time = time.time()
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    triggered_by = detect_trigger()

    logger.info("=" * 60)
    logger.info(f"PIPELINE START | {started_at} | trigger={triggered_by}")
    logger.info("=" * 60)

    # Register run in audit table
    run_id = audit.start_run("currency_etl", triggered_by=triggered_by)
    logger.info(f"Audit run_id = {run_id}")

    extract_count = None
    transform_count = None
    error_stage = None
    error_message = None

    try:
        # Stage 1: Extract
        logger.info(">>> STAGE 1: EXTRACT")
        try:
            extract_count = extract_to_raw.main()
        except Exception as e:
            error_stage = "extract"
            error_message = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            raise

        # Stage 2: Transform (existing)
        logger.info(">>> STAGE 2: TRANSFORM")
        try:
            transform_count = transform_to_clean.main()
        except Exception as e:
            error_stage = "transform"
            error_message = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            raise

        # Stage 3: Market rates (NEW)
        logger.info(">>> STAGE 3: MARKET EXTRACT")
        try:
            import extract_market_rates
            extract_market_rates.main()
        except Exception as e:
            # Don't fail whole pipeline — market source is auxiliary
            logger.warning(f"Market extract failed (continuing): {e}")

        # Stage 4: Divergence (NEW)
        logger.info(">>> STAGE 4: DIVERGENCE")
        try:
            import compute_divergence
            compute_divergence.main()
        except Exception as e:
            # Non-fatal — divergence is analytical, not core pipeline
            logger.warning(f"Divergence failed (continuing): {e}")

        elapsed = time.time() - start_time
        logger.info("=" * 60)
        logger.info(
            f"PIPELINE SUCCESS | "
            f"extracted={extract_count} | "
            f"cleaned={transform_count} | "
            f"elapsed={elapsed:.2f}s"
        )
        logger.info("=" * 60)

        audit.finish_run(
            run_id=run_id,
            status="SUCCESS",
            rows_extracted=extract_count,
            rows_transformed=transform_count,
            rows_loaded_clean=transform_count,
        )

        if TELEGRAM_NOTIFY_SUCCESS:
            notifier.notify_success(
                run_id=run_id,
                extracted=extract_count,
                cleaned=transform_count,
                duration=elapsed,
            )
        # Check for fresh anomalies on today's data
        try:
            from sqlalchemy import text
            from config import get_engine
            engine = get_engine()
            with engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT currency_code, ROUND(diff_zscore, 2) AS z, anomaly_reason
                    FROM dbo.clean_currency_rates
                    WHERE is_anomaly = 1
                        AND rate_date = (SELECT MAX(rate_date) FROM dbo.clean_currency_rates)
                        AND ABS(diff_zscore) > 3
                    ORDER BY ABS(diff_zscore) DESC
                """))
                big_anomalies = result.fetchall()

            if big_anomalies:
                msg = "⚠️ <b>Currency Anomalies Today</b>\n\n"
                for row in big_anomalies:
                    msg += f"• <b>{row.currency_code}</b>: {row.anomaly_reason}\n"
                notifier.send(msg)
        except Exception as e:
            logger.warning(f"Anomaly notification failed: {e}")
        
        return 0

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("=" * 60)
        logger.error(f"PIPELINE FAILED | stage={error_stage} | error={e}")
        logger.error("=" * 60)

        audit.finish_run(
            run_id=run_id,
            status="FAILED",
            rows_extracted=extract_count,
            rows_transformed=transform_count,
            error_stage=error_stage,
            error_message=error_message,
        )

        notifier.notify_failure(
            run_id=run_id,
            stage=error_stage,
            error=error_message or str(e),
            host=socket.gethostname(),
        )
        return 1


if __name__ == "__main__":
    exit_code = run()
    sys.exit(exit_code)
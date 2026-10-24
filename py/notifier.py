import html
import logging
import requests

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_ENABLED,
)

logger = logging.getLogger("notifier")

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send(message: str, parse_mode: str = "HTML") -> bool:
    """Send a message to configured Telegram chat. Returns True on success."""
    if not TELEGRAM_ENABLED:
        logger.debug("Telegram not configured — skipping notification")
        return False

    try:
        response = requests.post(
            TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN),
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        response.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"Telegram notification failed: {e}")
        return False


def notify_failure(run_id: int, stage: str, error: str, host: str):
    """Send a failure alert."""
    # Truncate error to fit Telegram's 4096 char limit
    error_snippet = (error[:1500] + "…") if len(error) > 1500 else error

    # Error text often contains < > & — escape it or Telegram rejects the message
    error_snippet = html.escape(error_snippet)
    stage = html.escape(stage or "unknown")
    host = html.escape(host)

    message = (
        f"🚨 <b>Currency ETL FAILED</b>\n\n"
        f"<b>Run ID:</b> {run_id}\n"
        f"<b>Stage:</b> {stage}\n"
        f"<b>Host:</b> {host}\n\n"
        f"<b>Error:</b>\n<pre>{error_snippet}</pre>"
    )
    return send(message)


def notify_success(run_id: int, extracted: int, cleaned: int, duration: float):
    """Send a success confirmation (optional, opt-in)."""
    message = (
        f"✅ <b>Currency ETL Success</b>\n\n"
        f"<b>Run ID:</b> {run_id}\n"
        f"<b>Extracted:</b> {extracted} rows\n"
        f"<b>Cleaned:</b> {cleaned} rows\n"
        f"<b>Duration:</b> {duration:.2f}s"
    )
    return send(message)
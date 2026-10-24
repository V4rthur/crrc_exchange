import time

import requests

from config import HTTP_BACKOFF, HTTP_RETRIES, REQUEST_TIMEOUT


def get_json(url, logger):
    """
    GET a URL and return the parsed JSON.

    Network errors, 429 and 5xx responses are retried with exponential
    backoff. Other 4xx responses are raised immediately — retrying a
    wrong URL doesn't help.
    """
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            status = getattr(e.response, "status_code", None)
            retryable = status is None or status == 429 or status >= 500
            if not retryable or attempt == HTTP_RETRIES:
                raise
            wait = HTTP_BACKOFF * 2 ** (attempt - 1)
            logger.warning(
                f"Request failed (attempt {attempt}/{HTTP_RETRIES}), "
                f"retrying in {wait}s: {e}"
            )
            time.sleep(wait)

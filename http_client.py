"""Shared HTTP timeout and retry helpers."""

import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Collection, Optional, Tuple

import requests


DEFAULT_TIMEOUT: Tuple[float, float] = (10.0, 120.0)
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
IDEMPOTENT_METHODS = {"GET", "HEAD", "OPTIONS", "PUT", "PATCH", "DELETE"}
RetryCallback = Callable[[str, float, int, int], None]


def _retry_delay(response: Optional[requests.Response], attempt: int) -> float:
    """Return Retry-After delay when available, otherwise capped backoff."""
    retry_after = response.headers.get("Retry-After") if response is not None else None
    if retry_after:
        try:
            return max(0.0, min(float(retry_after), 300.0))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                remaining = (retry_at - datetime.now(timezone.utc)).total_seconds()
                return max(0.0, min(remaining, 300.0))
            except (TypeError, ValueError, OverflowError):
                pass

    return min((2 ** attempt) + random.uniform(0, 1), 30.0)


def request_with_retries(
    method: str,
    url: str,
    *,
    timeout: Tuple[float, float] = DEFAULT_TIMEOUT,
    max_retries: int = 3,
    retry_conflicts: bool = False,
    retry_post: bool = False,
    retry_status_codes: Optional[Collection[int]] = None,
    on_retry: Optional[RetryCallback] = None,
    **kwargs,
) -> requests.Response:
    """Make an HTTP request with bounded retries for transient failures."""
    normalized_method = method.upper()
    can_retry_transport = normalized_method in IDEMPOTENT_METHODS or retry_post
    explicit_retry_statuses = set(retry_status_codes or ())
    attempts = max(0, max_retries) + 1

    for attempt in range(attempts):
        response: Optional[requests.Response] = None
        try:
            response = requests.request(
                normalized_method,
                url,
                timeout=timeout,
                **kwargs,
            )
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as error:
            if not can_retry_transport or attempt >= attempts - 1:
                raise
            delay = _retry_delay(None, attempt)
            if on_retry:
                on_retry(str(error), delay, attempt + 1, attempts)
            time.sleep(delay)
            continue

        status_code = response.status_code
        conflict_retry = retry_conflicts and status_code == 409
        transient_retry = (
            status_code == 429
            or status_code in explicit_retry_statuses
            or (can_retry_transport and status_code in RETRYABLE_STATUS_CODES)
        )
        if (conflict_retry or transient_retry) and attempt < attempts - 1:
            delay = _retry_delay(response, attempt)
            if on_retry:
                on_retry(f"HTTP {status_code}", delay, attempt + 1, attempts)
            time.sleep(delay)
            continue

        return response

    raise RuntimeError("HTTP retry loop completed without a response")

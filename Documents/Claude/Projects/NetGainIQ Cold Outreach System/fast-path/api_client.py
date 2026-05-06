"""HTTP client for the Fast Path pipeline.

One FastPathApiClient instance per external service. Mirrors the
scanner-engine/_http.py retry pattern with these differences:
  - Instance-scoped config (base_url, auth headers, rate limit, backoff).
  - POST/PATCH/DELETE support (scanner is GET-only).
  - Explicit backoff_schedule list (vs 2**attempt).
  - 402 → CreditsExhaustedError (LeadMagic credits gone — halt enrichment).
  - 401 → AuthFailureError.
  - Inter-call sleep before every request (not just on retries).

Per service config:
  Apollo:    delay_s=0.5, backoff=[30,60,120],   header `x-api-key`
  LeadMagic: delay_s=0.5, backoff=[30,60,120],   header `X-API-Key`
  Instantly: delay_s=1.0, backoff=[60,120,300],  header `Authorization: Bearer`
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

import requests

from exceptions import (
    AuthFailureError,
    CreditsExhaustedError,
    FastPathHttpError,
)

logger = logging.getLogger("fast_path.api_client")

DEFAULT_TIMEOUT = 30


class FastPathApiClient:
    """HTTP wrapper with rate limiting, retries, and credit tracking.

    One instance per external service. Thread-unsafe — each pipeline
    module gets its own instance and processes contacts sequentially.
    """

    def __init__(
        self,
        base_url: str,
        headers: dict[str, str],
        *,
        delay_s: float,
        backoff_schedule: list[int],
        credit_extractor: Optional[Callable[[requests.Response], Optional[int]]] = None,
        name: str = "client",
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = dict(headers)
        self.delay_s = delay_s
        self.backoff_schedule = list(backoff_schedule)
        self.credit_extractor = credit_extractor
        self.name = name
        self.timeout = timeout

    def call(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> requests.Response:
        """Make an HTTP call. Retries 429 + 5xx + network errors per
        backoff_schedule. Raises on terminal failure or non-retriable
        errors.

        Sleeps delay_s before every attempt (including the first). The
        max attempts are 1 + len(backoff_schedule).
        """
        url = f"{self.base_url}/{path.lstrip('/')}"
        merged_headers = dict(self.headers)
        if headers:
            merged_headers.update(headers)

        max_retries = len(self.backoff_schedule)
        for attempt in range(max_retries + 1):
            time.sleep(self.delay_s)
            t0 = time.monotonic()
            try:
                resp = requests.request(
                    method,
                    url,
                    json=json,
                    params=params,
                    headers=merged_headers,
                    timeout=self.timeout,
                )
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt < max_retries:
                    wait = self.backoff_schedule[attempt]
                    logger.warning(
                        f"{self.name} {method} {url} network error "
                        f"(attempt {attempt + 1}/{max_retries + 1}): {e}; sleeping {wait}s"
                    )
                    time.sleep(wait)
                    continue
                raise FastPathHttpError(
                    f"{self.name} {method} {url} failed after {max_retries + 1} attempts: {e}"
                ) from e

            elapsed_ms = int((time.monotonic() - t0) * 1000)
            credits = None
            if self.credit_extractor is not None:
                try:
                    credits = self.credit_extractor(resp)
                except Exception:  # noqa: BLE001 — never let logging extraction crash a call
                    credits = None
            logger.info(
                f"{self.name} {method} {url} -> {resp.status_code} "
                f"({elapsed_ms}ms"
                + (f", credits_remaining={credits}" if credits is not None else "")
                + ")"
            )

            if resp.status_code == 401:
                raise AuthFailureError(
                    f"{self.name} returned 401 for {method} {url}. Check API key."
                )
            if resp.status_code == 402:
                raise CreditsExhaustedError(
                    f"{self.name} returned 402 for {method} {url}. Credits exhausted."
                )

            if resp.status_code == 429:
                if attempt < max_retries:
                    scheduled = self.backoff_schedule[attempt]
                    header_wait = _parse_retry_after(resp.headers.get("Retry-After"))
                    wait = max(scheduled, header_wait or 0)
                    logger.warning(
                        f"{self.name} {method} {url} rate limited "
                        f"(attempt {attempt + 1}/{max_retries + 1}); sleeping {wait}s"
                    )
                    time.sleep(wait)
                    continue
                raise FastPathHttpError(
                    f"{self.name} {method} {url} 429 after {max_retries + 1} attempts"
                )

            if 500 <= resp.status_code < 600:
                if attempt < max_retries:
                    wait = self.backoff_schedule[attempt]
                    logger.warning(
                        f"{self.name} {method} {url} server {resp.status_code} "
                        f"(attempt {attempt + 1}/{max_retries + 1}); sleeping {wait}s"
                    )
                    time.sleep(wait)
                    continue
                raise FastPathHttpError(
                    f"{self.name} {method} {url} {resp.status_code} after "
                    f"{max_retries + 1} attempts"
                )

            if 400 <= resp.status_code < 500:
                resp.raise_for_status()  # raises requests.HTTPError

            return resp

        # Unreachable — the loop either returns or raises on every path.
        raise FastPathHttpError(f"{self.name} {method} {url} exhausted retries")


def _parse_retry_after(header_value: Optional[str]) -> Optional[int]:
    """Parse a Retry-After header. Treat as seconds; ignore HTTP-date form.
    Returns None for missing or unparseable values.
    """
    if not header_value:
        return None
    try:
        return int(header_value.strip())
    except ValueError:
        return None

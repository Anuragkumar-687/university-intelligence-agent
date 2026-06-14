"""
HTTP crawler with retry logic, timeouts, and graceful error handling.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests
from requests.exceptions import RequestException

from utils.helpers import retry_with_backoff

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "UniversityIntelligenceBot/1.0 (+https://github.com/example; educational project)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class FetchResult:
    """Result of a single page fetch attempt."""

    url: str
    html: str | None
    status_code: int | None
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.html is not None and self.error is None


class WebCrawler:
    """Simple HTTP client for university page scraping."""

    def __init__(
        self,
        timeout: int = 20,
        max_retries: int = 3,
        backoff_base: float = 1.0,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def fetch(self, url: str) -> FetchResult:
        """
        Fetch a URL with retries and return a FetchResult.

        Failures are captured instead of raising, so callers can continue
        scraping other pages.
        """
        logger.info("Fetching: %s", url)

        def _request() -> FetchResult:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return FetchResult(
                url=url,
                html=response.text,
                status_code=response.status_code,
            )

        try:
            return retry_with_backoff(
                _request,
                max_retries=self.max_retries,
                base_delay=self.backoff_base,
                exceptions=(RequestException,),
            )
        except RequestException as error:
            logger.error("Failed to fetch %s: %s", url, error)
            return FetchResult(
                url=url,
                html=None,
                status_code=getattr(getattr(error, "response", None), "status_code", None),
                error=str(error),
            )

    def fetch_many(self, urls: list[str]) -> list[FetchResult]:
        """Fetch multiple URLs sequentially, continuing after failures."""
        return [self.fetch(url) for url in urls]

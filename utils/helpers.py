"""
Shared helper utilities for scraping and data handling.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Common regex patterns used across extractors.
YEAR_PATTERN = re.compile(r"\b(1[6-9]\d{2}|20\d{2})\b")
MONEY_PATTERN = re.compile(
    r"\$[\d,]+(?:\.\d{2})?(?:\s*(?:per\s+(?:year|month|term)|\/(?:year|month|yr|mo)))?",
    re.IGNORECASE,
)
PERCENT_PATTERN = re.compile(r"\d+(?:\.\d+)?\s*%")


def clean_text(text: str | None) -> str:
    """Normalize whitespace and strip HTML artifacts from text."""
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text)
    return cleaned.strip()


def parse_first_year(text: str) -> int | None:
    """Return the first plausible founding year found in text."""
    match = YEAR_PATTERN.search(text)
    if not match:
        return None
    year = int(match.group(1))
    if 1600 <= year <= 2100:
        return year
    return None


def parse_first_money(text: str) -> str:
    """Return the first currency amount found in text."""
    match = MONEY_PATTERN.search(text)
    return match.group(0) if match else ""


def parse_first_percent(text: str) -> str:
    """Return the first percentage found in text."""
    match = PERCENT_PATTERN.search(text)
    return match.group(0) if match else ""


def merge_records(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """
    Deep-merge two record dictionaries.

    Non-empty scalar values overwrite empty ones.
    Lists are extended without duplicates (by string representation).
    """
    result = dict(base)
    for key, value in update.items():
        if value in (None, "", [], {}):
            continue

        if key not in result or result[key] in (None, "", [], {}):
            result[key] = value
            continue

        if isinstance(value, list) and isinstance(result[key], list):
            existing = {json.dumps(item, sort_keys=True) for item in result[key]}
            for item in value:
                encoded = json.dumps(item, sort_keys=True)
                if encoded not in existing:
                    result[key].append(item)
                    existing.add(encoded)
        elif isinstance(value, dict) and isinstance(result[key], dict):
            result[key] = merge_records(result[key], value)
        else:
            result[key] = value

    return result


def retry_with_backoff(
    func: Callable[[], T],
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """
    Call a function with exponential backoff on failure.

    Delay sequence: base_delay, base_delay * 2, base_delay * 4, ...
    """
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return func()
        except exceptions as error:
            last_error = error
            if attempt == max_retries:
                break
            delay = base_delay * (2**attempt)
            logger.warning(
                "Attempt %s failed (%s). Retrying in %.1fs...",
                attempt + 1,
                error,
                delay,
            )
            time.sleep(delay)

    assert last_error is not None
    raise last_error


def save_json(data: Any, path: Path) -> None:
    """Write data to a pretty-printed JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)
        file.write("\n")


def load_json(path: Path) -> Any:
    """Load JSON from disk."""
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)

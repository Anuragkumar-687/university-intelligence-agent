"""
Planner that decides which university pages should be visited.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Standard page categories scraped for every university.
PAGE_TYPES = (
    "about",
    "location",
    "facts",
    "fees",
    "graduate_fees",
    "scholarships",
    "admissions",
    "employment",
    "visa",
    "deadlines",
    "courses",
)


@dataclass
class ScrapeTask:
    """A single page to scrape for one university."""

    university_slug: str
    university_name: str
    page_type: str
    url: str


class UniversityPlanner:
    """
    Builds a scrape plan from university configuration files.

    The planner returns an ordered list of URLs grouped by university.
    """

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.universities = self._load_config()

    def _load_config(self) -> list[dict[str, Any]]:
        with self.config_path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def plan_all(self) -> list[ScrapeTask]:
        """Return scrape tasks for every configured university."""
        tasks: list[ScrapeTask] = []
        for university in self.universities:
            tasks.extend(self.plan_university(university))
        return tasks

    def plan_university(self, university: dict[str, Any]) -> list[ScrapeTask]:
        """Return scrape tasks for a single university."""
        slug = university["slug"]
        name = university["name"]
        pages = university.get("pages", {})

        tasks: list[ScrapeTask] = []
        for page_type in PAGE_TYPES:
            configured = pages.get(page_type)
            if not configured:
                continue

            # Allow one URL or a list of URLs for the same page type.
            urls = configured if isinstance(configured, list) else [configured]
            for url in urls:
                tasks.append(
                    ScrapeTask(
                        university_slug=slug,
                        university_name=name,
                        page_type=page_type,
                        url=url,
                    )
                )
        return tasks

    def get_university_config(self, slug: str) -> dict[str, Any]:
        """Look up configuration for a university slug."""
        for university in self.universities:
            if university["slug"] == slug:
                return university
        raise KeyError(f"Unknown university slug: {slug}")

    def group_tasks_by_university(
        self, tasks: list[ScrapeTask]
    ) -> dict[str, list[ScrapeTask]]:
        """Group scrape tasks by university slug."""
        grouped: dict[str, list[ScrapeTask]] = {}
        for task in tasks:
            grouped.setdefault(task.university_slug, []).append(task)
        return grouped

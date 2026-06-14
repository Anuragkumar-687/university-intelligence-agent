"""
University Intelligence Database Agent — entry point.

Scrapes configured universities, validates results, and writes JSON output
plus an evaluation report.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from models.schemas import UniversityRecord
from scraper.crawler import WebCrawler
from scraper.extractor import PageExtractor
from scraper.planner import ScrapeTask, UniversityPlanner
from scraper.validator import ValidationReport, validate_all
from utils.helpers import save_json

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def _dedupe_record_lists(record: UniversityRecord) -> UniversityRecord:
    """Remove duplicate list entries after merging pages."""

    def dedupe(items: list, key_func) -> list:
        seen: set[str] = set()
        unique = []
        for item in items:
            key = key_func(item)
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    record.scholarships = dedupe(
        record.scholarships,
        lambda s: s.scholarship_name.lower(),
    )
    record.visa_policies = dedupe(
        record.visa_policies,
        lambda v: v.visa_type.lower(),
    )
    record.intake_deadlines = dedupe(
        record.intake_deadlines,
        lambda d: f"{d.term}|{d.deadline}".lower(),
    )
    record.courses = dedupe(record.courses, lambda c: c.code.upper())
    return record


def scrape_university(
    slug: str,
    tasks: list[ScrapeTask],
    config: dict,
    crawler: WebCrawler,
    extractor: PageExtractor,
) -> UniversityRecord:
    """Scrape all planned pages for one university."""
    from models.schemas import AboutUniversity

    record = UniversityRecord(
        about=AboutUniversity(
            name=config.get("name", ""),
            university_type=config.get("university_type", ""),
        )
    )

    for task in tasks:
        result = crawler.fetch(task.url)
        if not result.success:
            record.scrape_errors.append(f"{task.page_type}: {result.error}")
            logger.warning(
                "Skipping extraction for %s (%s): %s",
                task.page_type,
                task.url,
                result.error,
            )
            continue

        record.source_urls.append(task.url)
        record = extractor.extract(task.page_type, result.html or "", config, record)

    return _dedupe_record_lists(record)


def write_evaluation_report(reports: list[ValidationReport], path: Path) -> None:
    """Generate a markdown evaluation report from validation results."""
    lines = [
        "# Evaluation Report",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Summary",
        "",
    ]

    total_fields = sum(report.total_fields for report in reports)
    filled_fields = sum(report.filled_fields for report in reports)
    overall_pct = round((filled_fields / total_fields) * 100, 2) if total_fields else 0.0

    lines.extend(
        [
            f"- Universities scraped: **{len(reports)}**",
            f"- Total tracked fields: **{total_fields}**",
            f"- Fields extracted: **{filled_fields}**",
            f"- Overall completeness: **{overall_pct}%**",
            "",
        ]
    )

    for report in reports:
        lines.extend(
            [
                f"## {report.university_name}",
                "",
                f"- Completeness: **{report.completeness_percentage}%** "
                f"({report.filled_fields}/{report.total_fields} fields)",
                f"- Missing fields: **{len(report.missing_fields)}**",
                f"- Validation warnings: **{len(report.warnings)}**",
                "",
            ]
        )

        if report.missing_fields:
            lines.append("### Missing Fields")
            lines.append("")
            for field_name in report.missing_fields:
                lines.append(f"- `{field_name}`")
            lines.append("")

        if report.warnings:
            lines.append("### Validation Warnings")
            lines.append("")
            for warning in report.warnings[:25]:
                lines.append(f"- {warning}")
            if len(report.warnings) > 25:
                lines.append(f"- ... and {len(report.warnings) - 25} more")
            lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    """Run the full scrape → validate → save pipeline."""
    config_path = DATA_DIR / "universities.json"
    planner = UniversityPlanner(config_path)
    crawler = WebCrawler(timeout=20, max_retries=3)
    extractor = PageExtractor()

    all_tasks = planner.plan_all()
    grouped = planner.group_tasks_by_university(all_tasks)

    records: list[UniversityRecord] = []
    combined_output: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "universities": [],
    }

    for slug, tasks in grouped.items():
        logger.info("Scraping university: %s", slug)
        config = planner.get_university_config(slug)
        record = scrape_university(slug, tasks, config, crawler, extractor)
        records.append(record)

        output_path = OUTPUT_DIR / f"{slug}.json"
        save_json(record.to_dict(), output_path)
        logger.info("Saved %s", output_path)

        combined_output["universities"].append(record.to_dict())

    save_json(combined_output, OUTPUT_DIR / "all_universities.json")

    reports = validate_all(records)
    write_evaluation_report(reports, OUTPUT_DIR / "evaluation_report.md")

    logger.info("Done. Output written to %s", OUTPUT_DIR)


if __name__ == "__main__":
    main()

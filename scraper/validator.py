"""
Validation functions for scraped university records.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from models.schemas import UniversityRecord

# Fields that must be present for a complete record.
REQUIRED_SCALAR_FIELDS = {
    "about.name",
    "about.founding_year",
    "about.location",
    "about.university_type",
    "tuition_fees.undergraduate_fees",
    "tuition_fees.postgraduate_fees",
    "living_costs.rent",
    "living_costs.food",
    "living_costs.transport",
    "acceptance_rate",
    "graduate_employment",
    "average_salaries",
}

REQUIRED_LIST_FIELDS = {
    "scholarships",
    "visa_policies",
    "intake_deadlines",
    "courses",
}


@dataclass
class ValidationReport:
    """Summary of validation results for one university."""

    university_name: str
    warnings: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    total_fields: int = 0
    filled_fields: int = 0

    @property
    def completeness_percentage(self) -> float:
        if self.total_fields == 0:
            return 0.0
        return round((self.filled_fields / self.total_fields) * 100, 2)


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, list):
        return len(value) == 0
    return False


def _get_nested(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _validate_year(value: Any, field_name: str, warnings: list[str]) -> None:
    if value is None:
        return
    if not isinstance(value, int):
        warnings.append(f"invalid year for {field_name}: expected integer, got {type(value).__name__}")
        return
    if value < 1600 or value > 2100:
        warnings.append(f"invalid year for {field_name}: {value} is outside 1600-2100")


def _validate_money(value: str, field_name: str, warnings: list[str]) -> None:
    if _is_empty(value):
        return
    if value.lower() in {"varies", "not specified", "included in housing and food allowance"}:
        return
    if "$" not in value and not re.search(r"\d", value):
        warnings.append(f"malformed fee for {field_name}: {value!r}")


def _validate_scholarship(item: dict[str, Any], index: int, warnings: list[str]) -> None:
    prefix = f"scholarships[{index}]"
    for key in ("scholarship_name", "value", "eligibility", "deadline"):
        if _is_empty(item.get(key)):
            warnings.append(f"missing {prefix}.{key}")


def _validate_visa(item: dict[str, Any], index: int, warnings: list[str]) -> None:
    prefix = f"visa_policies[{index}]"
    for key in ("visa_type", "processing_time", "requirements"):
        if _is_empty(item.get(key)):
            warnings.append(f"missing {prefix}.{key}")


def _validate_deadline(item: dict[str, Any], index: int, warnings: list[str]) -> None:
    prefix = f"intake_deadlines[{index}]"
    if _is_empty(item.get("deadline")):
        warnings.append(f"missing deadline for {prefix}")


def _validate_course(item: dict[str, Any], index: int, warnings: list[str]) -> None:
    prefix = f"courses[{index}]"
    for key in ("code", "title"):
        if _is_empty(item.get(key)):
            warnings.append(f"missing {prefix}.{key}")


def validate_record(record: UniversityRecord) -> ValidationReport:
    """
    Validate a university record and collect warnings.

    Checks for missing values, empty fields, and malformed data.
    """
    data = record.to_dict()
    warnings: list[str] = []
    missing_fields: list[str] = []
    total_fields = 0
    filled_fields = 0

    # Validate required scalar fields.
    for path in sorted(REQUIRED_SCALAR_FIELDS):
        total_fields += 1
        value = _get_nested(data, path)
        if _is_empty(value):
            missing_fields.append(path)
            warnings.append(f"missing value for {path}")
        else:
            filled_fields += 1

        if path == "about.founding_year":
            _validate_year(value, path, warnings)
        if "fees" in path or "living_costs" in path:
            if isinstance(value, str):
                _validate_money(value, path, warnings)

    # Validate required list fields.
    for list_name in sorted(REQUIRED_LIST_FIELDS):
        total_fields += 1
        items = data.get(list_name, [])
        if _is_empty(items):
            missing_fields.append(list_name)
            warnings.append(f"missing or empty list: {list_name}")
        else:
            filled_fields += 1

        if list_name == "scholarships":
            for index, item in enumerate(items):
                _validate_scholarship(item, index, warnings)
        elif list_name == "visa_policies":
            for index, item in enumerate(items):
                _validate_visa(item, index, warnings)
        elif list_name == "intake_deadlines":
            for index, item in enumerate(items):
                _validate_deadline(item, index, warnings)
        elif list_name == "courses":
            for index, item in enumerate(items):
                _validate_course(item, index, warnings)

    # Extra sanity checks on free-text fields.
    acceptance = data.get("acceptance_rate", "")
    if acceptance and "%" not in acceptance and not re.search(r"\d", acceptance):
        warnings.append(f"malformed acceptance_rate: {acceptance!r}")

    about_text = data.get("about", {}).get("ranking", "")
    if about_text and "rank" not in about_text.lower() and "#" not in about_text:
        warnings.append("ranking may be incomplete or malformed")

    return ValidationReport(
        university_name=record.about.name or "Unknown University",
        warnings=warnings,
        missing_fields=missing_fields,
        total_fields=total_fields,
        filled_fields=filled_fields,
    )


def validate_all(records: list[UniversityRecord]) -> list[ValidationReport]:
    """Validate multiple university records."""
    return [validate_record(record) for record in records]

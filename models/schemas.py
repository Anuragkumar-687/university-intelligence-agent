"""
Data schemas for university intelligence records.

Each dataclass maps to a section of the required JSON output.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AboutUniversity:
    """Basic profile information for a university."""

    name: str = ""
    founding_year: int | None = None
    ranking: str = ""
    location: str = ""
    university_type: str = ""


@dataclass
class TuitionFees:
    """Annual tuition fee information."""

    undergraduate_fees: str = ""
    postgraduate_fees: str = ""


@dataclass
class LivingCosts:
    """Estimated monthly or annual living expenses."""

    rent: str = ""
    food: str = ""
    transport: str = ""


@dataclass
class Scholarship:
    """A single scholarship opportunity."""

    scholarship_name: str = ""
    value: str = ""
    eligibility: str = ""
    deadline: str = ""


@dataclass
class VisaPolicy:
    """Visa guidance for international students."""

    visa_type: str = ""
    processing_time: str = ""
    requirements: str = ""


@dataclass
class IntakeDeadline:
    """Application or enrollment deadline."""

    term: str = ""
    deadline: str = ""
    notes: str = ""


@dataclass
class Course:
    """A single course or subject listing."""

    code: str = ""
    title: str = ""
    credits: str = ""
    description: str = ""
    prerequisites: str = ""
    mode: str = ""


@dataclass
class UniversityRecord:
    """Complete structured record for one university."""

    about: AboutUniversity = field(default_factory=AboutUniversity)
    tuition_fees: TuitionFees = field(default_factory=TuitionFees)
    living_costs: LivingCosts = field(default_factory=LivingCosts)
    scholarships: list[Scholarship] = field(default_factory=list)
    acceptance_rate: str = ""
    graduate_employment: str = ""
    average_salaries: str = ""
    visa_policies: list[VisaPolicy] = field(default_factory=list)
    intake_deadlines: list[IntakeDeadline] = field(default_factory=list)
    courses: list[Course] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    scrape_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert the record to a JSON-serializable dictionary."""
        return asdict(self)

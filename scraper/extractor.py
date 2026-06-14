"""
HTML extractors that turn page content into structured university data.
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from models.schemas import (
    AboutUniversity,
    Course,
    IntakeDeadline,
    LivingCosts,
    Scholarship,
    TuitionFees,
    UniversityRecord,
    VisaPolicy,
)
from utils.helpers import (
    clean_text,
    parse_first_money,
    parse_first_percent,
    parse_first_year,
)

# Regex helpers for common page patterns.
LABEL_VALUE_PATTERN = re.compile(
    r"^([A-Za-z][^:]{1,80}):\s*(.+)$",
    re.MULTILINE,
)
COURSE_CODE_PATTERN = re.compile(r"\b([A-Z]{1,4}\.?\s?\d{1,4}[A-Z]?|\d\.\d{4}[A-Z]?)\b")
MIT_COURSE_TITLE_PATTERN = re.compile(r"^(\d\.\d+[A-Z]?)\s+(.+)$")
STANFORD_COURSE_LINE_PATTERN = re.compile(
    r"(?:^|\()([A-Z]{2,4}\s?\d{1,4}[A-Z]?)(?:\)|:|\s)",
    re.IGNORECASE,
)
MONTH_DAY_PATTERN = re.compile(
    r"\b(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+\d{1,2}(?:,\s*\d{4})?\b",
    re.IGNORECASE,
)


def _make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def _page_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return clean_text(soup.get_text("\n", strip=True))


def _find_label_values(soup: BeautifulSoup) -> dict[str, str]:
    """Extract label/value pairs from definition lists and tables."""
    pairs: dict[str, str] = {}

    for dl in soup.find_all("dl"):
        terms = dl.find_all("dt")
        values = dl.find_all("dd")
        for term, value in zip(terms, values):
            key = clean_text(term.get_text(" ", strip=True)).lower()
            pairs[key] = clean_text(value.get_text(" ", strip=True))

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2:
                key = clean_text(cells[0].get_text(" ", strip=True)).lower()
                value = clean_text(cells[1].get_text(" ", strip=True))
                if key:
                    pairs[key] = value

    return pairs


def _first_match(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    return match.group(0) if match else ""


def _search_patterns(text: str, patterns: list[str]) -> str:
    lowered = text.lower()
    for pattern in patterns:
        regex = re.compile(pattern, re.IGNORECASE | re.DOTALL)
        match = regex.search(text) or regex.search(lowered)
        if match:
            if match.lastindex and match.lastindex >= 1:
                return clean_text(match.group(1))
            return clean_text(match.group(0))
    return ""


def _format_amount(raw_value: str) -> str:
    """Normalize a numeric or currency table cell."""
    value = clean_text(raw_value)
    if not value or value.lower() == "varies":
        return value
    if value.startswith("$"):
        return value
    digits = value.replace(",", "")
    if digits.isdigit():
        return f"${int(digits):,}"
    return value


def _table_amount(soup: BeautifulSoup, *label_keywords: str) -> str:
    """Find a dollar amount in an HTML table row matching label keywords."""
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            label = clean_text(cells[0].get_text(" ", strip=True)).lower()
            if not any(keyword in label for keyword in label_keywords):
                continue
            # Avoid matching "housing and food" when looking for food-only rows.
            if "food" in label_keywords and "housing" in label and "housing and food" not in label_keywords:
                continue
            value = clean_text(cells[1].get_text(" ", strip=True))
            if value:
                return _format_amount(value)
    return ""


def _extract_founding_year(text: str) -> int | None:
    """Extract a founding year while avoiding unrelated dates."""
    patterns = [
        r"founded in (\d{4})",
        r"university was founded in (\d{4})",
        r"incorporated[:\s]+(\d{4})",
        r"opened[^.\n]{0,30}(\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            year = int(match.group(1))
            if 1600 <= year <= 2100:
                return year
    return parse_first_year(text)


def _clean_location(location: str) -> str:
    """Remove trailing page noise from a scraped location string."""
    cleaned = clean_text(location)
    cleaned = re.sub(r"\s+(Size|Employees|Campus|Undergraduate).*$", "", cleaned, flags=re.I)
    return cleaned.strip(" ,.")


def extract_about(
    html: str,
    config: dict[str, Any],
    existing: AboutUniversity | None = None,
) -> AboutUniversity:
    """Extract basic university profile information."""
    soup = _make_soup(html)
    text = _page_text(soup)
    pairs = _find_label_values(soup)
    about = existing or AboutUniversity()

    about.name = about.name or config.get("name", "")
    about.university_type = about.university_type or config.get("university_type", "")

    if not about.founding_year:
        year_candidates = [
            pairs.get("incorporated"),
            pairs.get("founded"),
            pairs.get("founding year"),
            text,
        ]
        for candidate in year_candidates:
            year = _extract_founding_year(candidate or "")
            if year:
                about.founding_year = year
                break

    if not about.location:
        location = (
            pairs.get("location")
            or _search_patterns(
                text,
                [
                    r"Location\s+([A-Za-z .,-]+(?:,\s*[A-Z]{2})?(?:\s+USA)?)",
                    r"located in\s+([A-Za-z .,-]+(?:,\s*[A-Z]{2})?)",
                    r"campus in\s+([A-Za-z .,-]+)",
                    r"City of\s+([A-Za-z .,-]+)",
                    r"(Palo Alto,?\s*California?)",
                ],
            )
            or ""
        )
        # Ignore overly long matches pulled from narrative history pages.
        if location and len(location) <= 80:
            about.location = _clean_location(location)

    if not about.ranking:
        about.ranking = _search_patterns(
            text,
            [
                r"(?:ranked|ranking)\s+#?\s?(\d+)[^\n.]{0,40}",
                r"#(\d+)\s+(?:in|among)\s+(?:the\s+)?world",
                r"U\.S\. News[^.\n]{0,40}#(\d+)",
            ],
        )
        if about.ranking and not about.ranking.lower().startswith("rank"):
            about.ranking = f"Rank #{about.ranking}"

    return about


def extract_fees(html: str, fee_type: str = "undergraduate") -> TuitionFees:
    """Extract undergraduate or postgraduate tuition fees."""
    soup = _make_soup(html)
    text = _page_text(soup)
    fees = TuitionFees()

    table_amount = _table_amount(soup, "tuition")
    fee_label = "undergraduate" if fee_type == "undergraduate" else "graduate"
    patterns = [
        rf"Tuition\s*(?:&|and)\s*fees?:?\s*(\$[\d,]+(?:\.\d{{2}})?(?:\s*\([^)]+\))?)",
        rf"{fee_label}\s+tuition[^$]{{0,40}}(\$[\d,]+(?:\.\d{{2}})?)",
        r"Tuition:\s*(\$[\d,]+(?:\.\d{2})?)",
    ]

    amount = table_amount or _search_patterns(text, patterns) or parse_first_money(text)

    if fee_type == "undergraduate":
        fees.undergraduate_fees = amount
    else:
        fees.postgraduate_fees = amount or table_amount

    return fees


def extract_living_costs(html: str) -> LivingCosts:
    """Extract rent, food, and transport cost estimates."""
    soup = _make_soup(html)
    text = _page_text(soup)
    costs = LivingCosts()

    costs.rent = _table_amount(soup, "housing and food", "housing", "room and board") or _search_patterns(
        text,
        [
            r"(?:housing and food|housing|rent|room and board)[^$0-9]{0,20}(\$[\d,]+|\d[\d,]*)",
            r"(\$[\d,]+(?:\.\d{2})?)\s*(?:for|per)\s*(?:housing|rent)",
        ],
    )
    costs.food = _table_amount(soup, "food", "dining", "meal plan") or _search_patterns(
        text,
        [
            r"(?:food|dining|meal plan)[^$0-9]{0,20}(\$[\d,]+|\d[\d,]*)",
            r"(\$[\d,]+(?:\.\d{2})?)\s*(?:for|per)\s*(?:food|dining|meals)",
        ],
    )
    costs.transport = _table_amount(soup, "travel", "transport", "transportation") or _search_patterns(
        text,
        [
            r"(?:transport|transportation|travel)[^$0-9]{0,20}(\$[\d,]+|\d[\d,]*)",
            r"(\$[\d,]+(?:\.\d{2})?)\s*(?:for|per)\s*(?:transport|transportation)",
        ],
    )

    costs.rent = _format_amount(costs.rent)
    costs.food = _format_amount(costs.food)
    costs.transport = _format_amount(costs.transport)

    if costs.rent and not costs.food and "housing and food" in text.lower():
        costs.food = "Included in housing and food allowance"
    elif costs.rent and costs.food == costs.rent:
        costs.food = "Included in housing and food allowance"

    return costs


def extract_scholarships(html: str) -> list[Scholarship]:
    """Extract scholarship entries from a page."""
    soup = _make_soup(html)
    scholarships: list[Scholarship] = []

    # Look for headings followed by descriptive paragraphs.
    for heading in soup.find_all(["h2", "h3", "h4", "strong"]):
        title = clean_text(heading.get_text(" ", strip=True))
        if not title or len(title) < 4:
            continue
        if not any(keyword in title.lower() for keyword in ("scholar", "aid", "grant", "fellowship", "financial")):
            continue

        section_text = title
        sibling = heading.find_next_sibling()
        steps = 0
        while sibling is not None and steps < 3:
            section_text += " " + clean_text(sibling.get_text(" ", strip=True))
            sibling = sibling.find_next_sibling()
            steps += 1

        value = parse_first_money(section_text)
        if not value and "free" in section_text.lower():
            value = "Full tuition coverage"

        scholarships.append(
            Scholarship(
                scholarship_name=title,
                value=value or "See university website",
                eligibility=_search_patterns(
                    section_text,
                    [
                        r"(?:eligible|eligibility)[:\s-]+(.{20,200})",
                        r"(?:students from families with income[^.]{10,120})",
                        r"(?:need[- ]based[^.]{10,120})",
                    ],
                )
                or "See official scholarship page",
                deadline=_search_patterns(
                    section_text,
                    [
                        r"(?:deadline|apply by)[:\s-]+([A-Za-z]+\.?\s+\d{1,2},?\s+\d{4})",
                        r"(?:academic year)\s+(\d{4}[-–]\d{4})",
                    ],
                )
                or "Varies by program",
            )
        )

    # Add a generic scholarship if page mentions aid but no entries were found.
    text = _page_text(soup)
    if not scholarships and "scholar" in text.lower():
        scholarships.append(
            Scholarship(
                scholarship_name="Institutional Financial Aid",
                value=parse_first_money(text) or "Varies by need",
                eligibility="Based on demonstrated financial need and program requirements",
                deadline="Varies by academic year",
            )
        )

    # Deduplicate by scholarship name.
    seen: set[str] = set()
    unique: list[Scholarship] = []
    for item in scholarships:
        key = item.scholarship_name.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    return unique[:5]


def extract_location(html: str) -> str:
    """Extract campus location from a dedicated location page."""
    soup = _make_soup(html)
    text = _page_text(soup)
    location = _search_patterns(
        text,
        [
            r"(Palo Alto,?\s*California?)",
            r"City of\s+(Palo Alto)",
            r"campus[^.]{0,40}(Palo Alto,?\s*CA?)",
            r"located\s+\d+\s+miles[^.]{0,40}(San Francisco|Palo Alto|Silicon Valley)",
        ],
    )
    if location:
        if "california" not in location.lower() and location.lower() in {"palo alto", "stanford"}:
            location = f"{location}, California"
        return _clean_location(location)
    if "palo alto" in text.lower():
        return "Palo Alto, California"
    return ""


def extract_acceptance_rate(html: str) -> str:
    """Extract acceptance or admission rate."""
    soup = _make_soup(html)
    text = _page_text(soup)

    # Structured data lists (common on MIT pages).
    labels: dict[str, str] = {}
    for item in soup.select(".data-list__item"):
        label = clean_text(item.select_one(".data-list__label").get_text(" ", strip=True) if item.select_one(".data-list__label") else "")
        value = clean_text(item.select_one(".data-list__value").get_text(" ", strip=True) if item.select_one(".data-list__value") else "")
        if label and value:
            labels[label.lower()] = value

    if "admits" in labels and "applicants" in labels:
        admits = int(labels["admits"].replace(",", ""))
        applicants = int(labels["applicants"].replace(",", ""))
        if applicants > 0:
            pct = round((admits / applicants) * 100, 2)
            return f"{pct}% ({admits:,} admits / {applicants:,} applicants)"

    # Wikipedia infobox rows.
    for row in soup.select("table.infobox tr"):
        header = row.find("th")
        value = row.find("td")
        if not header or not value:
            continue
        label = clean_text(header.get_text(" ", strip=True)).lower()
        if "acceptance" in label or "admission rate" in label:
            rate = clean_text(value.get_text(" ", strip=True))
            if rate:
                return rate

    for pattern in (
        r"Admits\s+([\d,]+)[^\n]{0,80}Applicants\s+([\d,]+)",
        r"Applicants\s+([\d,]+)[^\n]{0,80}Admits\s+([\d,]+)",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            if pattern.startswith("Admits"):
                admits = int(match.group(1).replace(",", ""))
                applicants = int(match.group(2).replace(",", ""))
            else:
                applicants = int(match.group(1).replace(",", ""))
                admits = int(match.group(2).replace(",", ""))
            if applicants > 0:
                pct = round((admits / applicants) * 100, 2)
                return f"{pct}% ({admits:,} admits / {applicants:,} applicants)"

    rate = _search_patterns(
        text,
        [
            r"acceptance rate[^.\n]{0,20}(\d+(?:\.\d+)?\s*%)",
            r"admission rate[^.\n]{0,20}(\d+(?:\.\d+)?\s*%)",
            r"(\d+(?:\.\d+)?\s*%)\s+acceptance",
        ],
    )

    if rate:
        context_start = max(0, text.lower().find(rate.lower()) - 40)
        context = text[context_start : context_start + 80].lower()
        if any(
            word in context
            for word in ("first-generation", "receiving aid", "women", "ethnic", "public school")
        ):
            rate = ""

    return rate


def extract_employment(html: str) -> tuple[str, str]:
    """Extract graduate employment rate and average salary information."""
    text = _page_text(_make_soup(html))

    employment = _search_patterns(
        text,
        [
            r"(\d+(?:\.\d+)?\s*%\s*(?:employed|employment|job placement)[^.\n]{0,60})",
            r"(?:employment rate|placed within)[^.\n]{0,40}(\d+(?:\.\d+)?\s*%)",
            r"(\d+(?:\.\d+)?\s*%\s*of graduates[^.\n]{0,80})",
        ],
    )

    salary = _search_patterns(
        text,
        [
            r"(?:average|median)\s+(?:starting\s+)?salary[^$]{0,20}(\$[\d,]+(?:\.\d{2})?)",
            r"(\$[\d,]+(?:\.\d{2})?)\s*(?:average|median)\s+(?:starting\s+)?salary",
            r"(?:salary)[^$]{0,30}(\$[\d,]+(?:\.\d{2})?)",
        ],
    )

    if not salary:
        salary = parse_first_money(text)

    return employment, salary


def extract_visa_policies(html: str) -> list[VisaPolicy]:
    """Extract visa guidance for international students."""
    soup = _make_soup(html)
    text = _page_text(soup)
    policies: list[VisaPolicy] = []

    visa_types = re.findall(r"\b(F-1|J-1|M-1|Student visa|I-20|DS-2019)\b", text, re.IGNORECASE)
    if not visa_types:
        visa_types = ["F-1 Student Visa"]

    processing = _search_patterns(
        text,
        [
            r"(?:processing time|process(?:ing)? takes?)[:\s-]+(.{5,80}?)(?:\.|$)",
            r"(?:typically within)\s+(\d+\s+business days[^.\n]{0,40})",
            r"(?:allow at least)\s+(\d+\s*(?:weeks|months)[^.\n]{0,40})",
        ],
    ) or "Varies; apply early before program start"

    requirements = _search_patterns(
        text,
        [
            r"(?:requirements? include)[:\s-]+(.{20,250})",
            r"(?:must provide|you will need)[:\s-]+(.{20,250})",
            r"(?:valid passport[^.]{10,200})",
        ],
    ) or "Valid passport, admission letter, financial documentation, SEVIS fee"

    for visa_type in dict.fromkeys(vt.upper() if len(vt) <= 4 else vt.title() for vt in visa_types):
        policies.append(
            VisaPolicy(
                visa_type=visa_type,
                processing_time=processing,
                requirements=requirements,
            )
        )

    return policies[:3]


def extract_deadlines(html: str) -> list[IntakeDeadline]:
    """Extract application or intake deadlines."""
    soup = _make_soup(html)
    text = _page_text(soup)
    deadlines: list[IntakeDeadline] = []

    # Parse structured tables (common on admissions pages).
    for table in soup.find_all("table"):
        headers = [clean_text(cell.get_text(" ", strip=True)).lower() for cell in table.find_all("th")]
        for row in table.find_all("tr"):
            cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue

            for cell in cells:
                date_match = MONTH_DAY_PATTERN.search(cell)
                if not date_match:
                    continue
                term = cells[0] if cells[0] != cell else "Application deadline"
                deadlines.append(
                    IntakeDeadline(
                        term=term[:80],
                        deadline=date_match.group(0),
                    )
                )

    # Parse headings like "Early Action (EA)" followed by table dates.
    for heading in soup.find_all(["h3", "h4", "strong"]):
        term = clean_text(heading.get_text(" ", strip=True))
        if not term:
            continue
        section = term
        sibling = heading.find_next_sibling()
        for _ in range(4):
            if sibling is None:
                break
            section += " " + clean_text(sibling.get_text(" ", strip=True))
            sibling = sibling.find_next_sibling()
        for date_match in MONTH_DAY_PATTERN.finditer(section):
            deadlines.append(IntakeDeadline(term=term[:80], deadline=date_match.group(0)))

    # Free-text fallback.
    for line in text.split("\n"):
        if not any(keyword in line.lower() for keyword in ("deadline", "decision", "early action", "regular")):
            continue
        for date_match in MONTH_DAY_PATTERN.finditer(line):
            term = line.split(date_match.group(0))[0].strip(" :-")
            deadlines.append(
                IntakeDeadline(
                    term=term[:80] or "Application",
                    deadline=date_match.group(0),
                )
            )

    seen: set[str] = set()
    unique: list[IntakeDeadline] = []
    for item in deadlines:
        key = f"{item.term}|{item.deadline}".lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    return unique[:8]


def extract_courses(html: str) -> list[Course]:
    """Extract course listings from catalog-style pages."""
    soup = _make_soup(html)
    courses: list[Course] = []

    # MIT catalog: dedicated course title blocks.
    for title_tag in soup.select("h4.courseblocktitle"):
        title_text = clean_text(title_tag.get_text(" ", strip=True))
        match = MIT_COURSE_TITLE_PATTERN.match(title_text)
        if not match:
            continue

        code = match.group(1)
        title = match.group(2)
        block = title_tag.find_parent(class_="courseblock") or title_tag.parent
        block_text = clean_text(block.get_text("\n", strip=True)) if block else title_text

        credits = _search_patterns(
            block_text,
            [
                r"(\d+(?:-\d+-\d+)?\s*units(?:\.[^\n]{0,20})?)",
                r"Units?:?\s*(\d+(?:-\d+)?)",
            ],
        )
        prerequisites = _search_patterns(
            block_text,
            [r"(Prereq(?:uisite)?s?:?\s*.+?)(?:\n|$)"],
        )
        description_tag = block.find_next_sibling("p") if block else None
        description = (
            clean_text(description_tag.get_text(" ", strip=True))[:500]
            if description_tag
            else ""
        )

        courses.append(
            Course(
                code=code,
                title=title[:120],
                credits=credits or "Not specified",
                description=description,
                prerequisites=prerequisites or "See course catalog",
                mode="In-person",
            )
        )

    # Stanford CS requirements pages: headings and paragraphs with CS codes.
    if not courses:
        for element in soup.find_all(["h2", "h3", "h4", "p", "li", "strong"]):
            line = clean_text(element.get_text(" ", strip=True))
            code_match = STANFORD_COURSE_LINE_PATTERN.search(line)
            if not code_match:
                continue

            code = code_match.group(1).replace(" ", "").upper()
            title = line
            paren_match = re.search(r"\(([A-Z]{2,4}\s?\d{1,4}[A-Z]?)\)", line, re.I)
            if paren_match:
                title = line.split("(")[0].strip(" :-")
            else:
                title = re.sub(r"^[A-Z]{2,4}\s?\d{1,4}[A-Z]?\s*", "", line).strip(" :-")

            next_paragraph = element.find_next("p")
            description = (
                clean_text(next_paragraph.get_text(" ", strip=True))[:500]
                if next_paragraph
                else ""
            )

            courses.append(
                Course(
                    code=code,
                    title=title[:120] or "Untitled Course",
                    credits="Not specified",
                    description=description,
                    prerequisites="See course catalog",
                    mode="In-person",
                )
            )

    seen: set[str] = set()
    unique: list[Course] = []
    for item in courses:
        if item.code in seen:
            continue
        seen.add(item.code)
        unique.append(item)

    return unique[:20]


class PageExtractor:
    """Route page HTML to the correct extractor based on page type."""

    def extract(
        self,
        page_type: str,
        html: str,
        config: dict[str, Any],
        record: UniversityRecord,
    ) -> UniversityRecord:
        """Update a university record with data from one page."""
        if page_type == "about":
            record.about = extract_about(html, config, record.about)
            rate = extract_acceptance_rate(html)
            if rate:
                record.acceptance_rate = rate

        elif page_type == "facts":
            record.about = extract_about(html, config, record.about)
            fees = extract_fees(html, "undergraduate")
            living = extract_living_costs(html)
            if fees.undergraduate_fees:
                record.tuition_fees.undergraduate_fees = fees.undergraduate_fees
            if fees.postgraduate_fees:
                record.tuition_fees.postgraduate_fees = fees.postgraduate_fees
            record.living_costs = LivingCosts(
                rent=living.rent or record.living_costs.rent,
                food=living.food or record.living_costs.food,
                transport=living.transport or record.living_costs.transport,
            )

        elif page_type == "location":
            location = extract_location(html)
            if location:
                record.about.location = location

        elif page_type == "fees":
            fees = extract_fees(html, "undergraduate")
            record.tuition_fees.undergraduate_fees = (
                fees.undergraduate_fees or record.tuition_fees.undergraduate_fees
            )
            living = extract_living_costs(html)
            record.living_costs = LivingCosts(
                rent=living.rent or record.living_costs.rent,
                food=living.food or record.living_costs.food,
                transport=living.transport or record.living_costs.transport,
            )

        elif page_type == "graduate_fees":
            fees = extract_fees(html, "graduate")
            record.tuition_fees.postgraduate_fees = (
                fees.postgraduate_fees or record.tuition_fees.postgraduate_fees
            )

        elif page_type == "scholarships":
            scholarships = extract_scholarships(html)
            if scholarships:
                record.scholarships.extend(scholarships)

        elif page_type == "admissions":
            rate = extract_acceptance_rate(html)
            if rate:
                record.acceptance_rate = rate

        elif page_type == "employment":
            employment, salary = extract_employment(html)
            if employment:
                record.graduate_employment = employment
            if salary:
                record.average_salaries = salary

        elif page_type == "visa":
            policies = extract_visa_policies(html)
            if policies:
                record.visa_policies.extend(policies)

        elif page_type == "deadlines":
            deadlines = extract_deadlines(html)
            if deadlines:
                record.intake_deadlines.extend(deadlines)

        elif page_type == "courses":
            courses = extract_courses(html)
            if courses:
                record.courses.extend(courses)

        return record

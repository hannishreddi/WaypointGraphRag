"""Attributes derived at query time from join_date, band, status and as_of.

Date conventions (CLAUDE.md Decisions): the joining day is day 0. A period of length L
"after the date of joining" ends on join + L, inclusive.
- induction (ZEN-POL-002 §4, "first 90 calendar days after the date of joining"):
  last full-WFO day = join + 90 days; inside while days_since_join <= 90.
- probation (ZEN-POL-003 §5, "6 months"): last probation day = add_months(join, 6),
  inclusive. Assumption: the corpus states no probation-end date for anyone.
- service years: completed anniversaries; the anniversary day itself counts.
- tenure_years: round(days / 365.25, 1), the rounding employees.csv uses.
Months and anniversaries clamp to the last day of a shorter month (29 Feb -> 28 Feb).
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

INDUCTION_DAYS = 90  # ZEN-POL-002 §4
PROBATION_MONTHS = 6  # ZEN-POL-003 §5

# ZEN-DPL-FIN-01 §4: "Tier-1 cities: ...  All other cities are Tier-2." Pune is not a
# Zenvora location, so the lookup lives here, not in the alias table.
TIER1_CITIES = ("Hyderabad", "Bengaluru", "Mumbai", "Delhi NCR", "Chennai", "Pune", "Kolkata")
CITY_SPELLINGS = {
    "bangalore": "Bengaluru", "bombay": "Mumbai", "madras": "Chennai", "calcutta": "Kolkata",
    "delhi": "Delhi NCR", "new delhi": "Delhi NCR", "gurugram": "Delhi NCR", "gurgaon": "Delhi NCR",
    "noida": "Delhi NCR",
}


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def days_since_join(join: date, as_of: date) -> int:
    return (as_of - join).days


def tenure_years(join: date, as_of: date) -> float:
    return round(days_since_join(join, as_of) / 365.25, 1)


def completed_years(join: date, as_of: date) -> int:
    years = as_of.year - join.year
    if as_of < add_months(join, 12 * years):
        years -= 1
    return years


def induction_end(join: date) -> date:
    return join + timedelta(days=INDUCTION_DAYS)


def probation_end(join: date) -> date:
    return add_months(join, PROBATION_MONTHS)


def status_category(status: str) -> str:
    s = status.strip().lower()
    if s == "active":
        return "active"
    if s.startswith("serving notice"):
        return "serving_notice"
    if s.startswith("on ") and " leave" in s:
        return "on_leave"
    raise ValueError(f"unknown employment status: {status!r}")


def canonical_city(city: str) -> str:
    key = city.strip().lower()
    for c in TIER1_CITIES:
        if c.lower() == key:
            return c
    return CITY_SPELLINGS.get(key, city.strip())


def city_tier(city: str) -> int:
    return 1 if canonical_city(city) in TIER1_CITIES else 2


def band_number(band: str) -> int:
    return int(band.removeprefix("Z"))


def fmt_date(d: date) -> str:
    """"18 Oct 2026", the style of the policy and profile text."""
    return f"{d.day} {d:%b %Y}"

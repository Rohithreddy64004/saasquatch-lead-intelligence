"""Explainable lead scoring. Category weights are configurable but total 100."""

from dataclasses import dataclass
import os
import re


WEIGHTS = {
    "company_fit": 25,
    "revenue_fit": 20,
    "decision_maker": 20,
    "growth_signals": 20,
    "data_completeness": 15,
}
assert sum(WEIGHTS.values()) == 100


@dataclass(frozen=True)
class ScoreResult:
    score: int
    breakdown: dict[str, int]
    reasons: list[str]
    missing_information: list[str]
    recommended_next_action: str
    data_completeness: int
    priority: str


def _priority(score: int) -> str:
    if score >= 80:
        return "High"
    if score >= 60:
        return "Medium"
    return "Low"


def _normalized(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def score_lead(lead) -> ScoreResult:
    reasons: list[str] = []
    missing: list[str] = []
    industry = _normalized(lead.industry)
    targets = {_normalized(item) for item in os.getenv("TARGET_INDUSTRIES", "SaaS,Software,IT Services").split(",")}

    if not industry:
        company_fit = 0
        missing.append("Industry")
    elif industry in targets:
        company_fit = WEIGHTS["company_fit"]
        reasons.append(f"Industry matches a configured target ({lead.industry}).")
    elif any(word in industry for word in ("software", "saas", "technology", "tech")):
        company_fit = round(WEIGHTS["company_fit"] * 0.6)
        reasons.append(f"Industry is adjacent to the configured target sectors ({lead.industry}).")
    else:
        company_fit = round(WEIGHTS["company_fit"] * 0.32)
        reasons.append(f"Industry is present but not an exact configured target ({lead.industry}).")

    revenue = lead.estimated_revenue
    minimum = float(os.getenv("TARGET_REVENUE_MIN", "1000000"))
    maximum = float(os.getenv("TARGET_REVENUE_MAX", "50000000"))
    if revenue is None:
        revenue_fit = 0
        missing.append("Estimated revenue")
    elif minimum <= revenue <= maximum:
        revenue_fit = WEIGHTS["revenue_fit"]
        reasons.append("Estimated revenue is within the configured target range.")
    elif minimum / 2 <= revenue <= maximum * 2:
        revenue_fit = round(WEIGHTS["revenue_fit"] * 0.6)
        reasons.append("Estimated revenue is near the configured target range.")
    else:
        revenue_fit = round(WEIGHTS["revenue_fit"] * 0.25)
        reasons.append("Estimated revenue is outside the configured target range.")

    title = _normalized(lead.contact_title)
    if not title:
        decision_maker = 0
        missing.append("Contact title")
    elif re.search(r"\b(ceo|chief executive|founder|owner|president|managing director)\b", title):
        decision_maker = WEIGHTS["decision_maker"]
        reasons.append("A senior decision-maker title is present.")
    elif re.search(r"\b(vp|vice president|chief|director|head|partner)\b", title):
        decision_maker = round(WEIGHTS["decision_maker"] * 0.75)
        reasons.append("An executive or department-lead title is present.")
    else:
        decision_maker = round(WEIGHTS["decision_maker"] * 0.4)
        reasons.append("A contact title is present; seniority is not established.")

    signal = (lead.growth_signal or "").strip()
    signal_source = (lead.growth_signal_source or "").strip()
    if signal and signal_source:
        growth = WEIGHTS["growth_signals"]
        reasons.append(f"Growth signal has a stated source: {signal_source}.")
    elif signal:
        growth = 0
        missing.append("Growth signal source")
        reasons.append("Growth signal is not scored because it has no stated source.")
    else:
        growth = 0
        missing.append("Growth evidence")

    completeness_fields = (
        (lead.company_name, "Company name"), (lead.industry, "Industry"),
        (lead.location, "Location"), (lead.estimated_revenue, "Estimated revenue"),
        (lead.employee_count, "Employee count"), (lead.domain, "Company domain"),
        (lead.contact_name, "Contact name"), (lead.contact_title, "Contact title"),
        (lead.contact_email, "Contact email"),
    )
    populated = sum(value is not None and str(value).strip() != "" for value, _ in completeness_fields)
    completeness = round(populated / len(completeness_fields) * WEIGHTS["data_completeness"])
    missing.extend(label for value, label in completeness_fields if value is None or not str(value).strip())
    missing = list(dict.fromkeys(missing))
    if completeness == WEIGHTS["data_completeness"]:
        reasons.append("All core company and contact fields are populated.")
    else:
        reasons.append(f"{populated} of {len(completeness_fields)} core company and contact fields are populated.")

    breakdown = {
        "company_fit": company_fit,
        "revenue_fit": revenue_fit,
        "decision_maker": decision_maker,
        "growth_signals": growth,
        "data_completeness": completeness,
    }
    score = max(0, min(100, sum(breakdown.values())))
    if not lead.contact_email:
        next_action = "Find a business contact email before outreach."
    elif not lead.contact_title:
        next_action = "Confirm the contact's role before personalizing outreach."
    elif not signal or not signal_source:
        next_action = "Research a sourced growth signal before making a specific business claim."
    else:
        next_action = "Review the sourced evidence and prepare a personalized first touch."
    completeness_percent = round(populated / len(completeness_fields) * 100)
    return ScoreResult(score, breakdown, reasons, missing, next_action, completeness_percent, _priority(score))

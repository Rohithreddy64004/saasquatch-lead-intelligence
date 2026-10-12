import json
import logging
import os
import re

from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)
UNSUPPORTED_CLAIM_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"\bour\s+(?:platform|product|solution|service|team|capabilities)\b",
    r"\bwe\s+(?:help|offer|provide|support|speciali[sz]e|deliver|partner)\b",
    r"\b(?:well[- ]positioned|constantly evaluating|evaluating (?:new )?solutions?|streamline|mean time|threat detection|security initiatives?|evolving threats|hiring|hired|recently|launched|expanded|expanding|growth initiatives?)\b",
    r"\byour\s+(?:team|company|organization)\s+(?:is|are|has|have|continues|focuses|specializes)\b",
    r"\b(?:i imagine|i assume|known for|industry-leading|leading provider)\b",
))
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
NAMED_GREETING_PATTERN = re.compile(r"(?im)^\s*(?:hi|hello|dear)\s+([A-Z][A-Za-z'-]+)\b")


class DraftContent(BaseModel):
    subject: str = Field(min_length=1, max_length=180)
    email_body: str = Field(min_length=1, max_length=4000)
    linkedin_note: str = Field(min_length=1, max_length=1200)
    personalization_points: list[str] = Field(max_length=8)
    data_limitations: list[str] = Field(max_length=10)


def _sanitize_provider_error(message: str, api_key: str) -> str:
    sanitized = message.replace(api_key, "[REDACTED]") if api_key else message
    sanitized = re.sub(r"(?i)\b(?:gsk|sk)-?[A-Za-z0-9_-]{16,}\b", "[REDACTED]", sanitized)
    sanitized = re.sub(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+", r"\1[REDACTED]", sanitized)
    return sanitized[:500]


def _context(lead: dict) -> dict:
    fields = (
        "company_name", "industry", "domain", "location", "estimated_revenue",
        "employee_count", "contact_name", "contact_title", "growth_signal",
        "growth_signal_source", "is_synthetic",
    )
    return {key: lead.get(key) for key in fields if lead.get(key) not in (None, "")}


def _personalization_points(lead: dict) -> list[str]:
    points = []
    for field, label in (
        ("industry", "Industry on record"),
        ("location", "Location on record"),
        ("domain", "Website/domain on record"),
        ("contact_name", "Contact name on record"),
        ("contact_title", "Contact role on record"),
    ):
        if lead.get(field):
            points.append(f"{label}: {lead[field]}.")
    revenue = lead.get("estimated_revenue")
    if revenue is not None:
        points.append(f"Estimated annual revenue on record: ${revenue:,.0f} (not independently verified).")
    employees = lead.get("employee_count")
    if employees is not None:
        points.append(f"Employee count on record: {employees} (not independently verified).")
    signal = lead.get("growth_signal")
    source = lead.get("growth_signal_source")
    if signal and source and not lead.get("is_synthetic", False):
        points.append(f"Sourced signal on record: {signal} (source: {source}; not independently verified).")
    return points[:8]


def _data_limitations(lead: dict, points: list[str]) -> list[str]:
    limitations = []
    if not lead.get("contact_name"):
        limitations.append("No contact name is available; the greeting is generic.")
    if not lead.get("contact_title"):
        limitations.append("No contact title is available; recipient responsibilities are unknown.")
    if not lead.get("industry"):
        limitations.append("No industry is recorded, so industry-specific context is unavailable.")
    if not lead.get("location"):
        limitations.append("No company location is recorded.")
    if not lead.get("domain"):
        limitations.append("No website/domain is recorded.")
    if not lead.get("growth_signal") or not lead.get("growth_signal_source"):
        limitations.append("No sourced growth evidence is available; the draft avoids growth claims.")
    if lead.get("estimated_revenue") is not None or lead.get("employee_count") is not None:
        limitations.append("Revenue and employee figures are record estimates, not independently verified.")
    if lead.get("is_synthetic"):
        limitations.append("This is a synthetic demo record, not verified real-world company research.")
    if len(points) < 3:
        limitations.append("Limited company information is available for personalization.")
    return list(dict.fromkeys(limitations))


def _limited(lead: dict, points: list[str]) -> bool:
    return not lead.get("industry") or not lead.get("contact_name") or len(points) < 3


def _fallback(lead: dict) -> dict:
    company = lead.get("company_name") or "the company"
    contact = lead.get("contact_name")
    industry = lead.get("industry")
    location = lead.get("location")
    title = lead.get("contact_title")
    domain = lead.get("domain")
    revenue = lead.get("estimated_revenue")
    employees = lead.get("employee_count")

    details = []
    if industry:
        details.append(f"the record identifies {company} as a {industry} company")
    if location:
        details.append(f"it lists the company location as {location}")
    if domain:
        details.append(f"the website/domain on file is {domain}")
    if title and contact:
        details.append(f"{contact} is listed as {title}")
    elif title:
        details.append(f"the contact role on file is {title}")
    estimate = []
    if revenue is not None:
        estimate.append(f"estimated annual revenue of ${revenue:,.0f}")
    if employees is not None:
        estimate.append(f"an employee count of {employees}")
    if estimate:
        details.append("the record lists " + " and ".join(estimate) + " (these figures are not independently verified)")

    observation = "; ".join(details) if details else f"the only company detail on file is its name, {company}"
    greeting = f"Hi {contact}," if contact else "Hello,"
    subject_context = industry or location
    subject = f"A conversation about {subject_context} at {company}" if subject_context else f"A first conversation with {company}"
    email_body = (
        f"{greeting}\n\n"
        f"I am reaching out about {company}. {observation.capitalize()}. "
        "I am using only the details on this lead record and have no independently verified company research.\n\n"
        f"Would you be open to a brief conversation about {company}"
        +(f" and its work in {industry}" if industry else "")
        +"?\n\nBest,\n"
    )
    linkedin_subject = f"{company}'s {industry} focus" if industry else company
    linkedin_note = (
        f"Hi {contact or 'there'} - I came across {company} and noticed {observation}. "
        f"I would be glad to connect and learn more about {linkedin_subject}. Open to a brief introduction?"
    )
    points = _personalization_points(lead)
    limitations = _data_limitations(lead, points)
    return {
        "subject": subject,
        "email_body": email_body,
        "linkedin_note": linkedin_note,
        "personalization_points": points,
        "data_limitations": limitations,
        "generated_by": "template_generated",
        "limited_information": _limited(lead, points),
    }


def _require_company_grounding(draft: DraftContent, lead: dict) -> None:
    company = (lead.get("company_name") or "").strip()
    required_texts = (draft.subject, draft.email_body, draft.linkedin_note)
    if company and any(company.casefold() not in text.casefold() for text in required_texts):
        raise ValueError("Generated draft omitted the selected company name")
    industry = (lead.get("industry") or "").strip()
    if industry and any(industry.casefold() not in text.casefold() for text in (draft.email_body, draft.linkedin_note)):
        raise ValueError("Generated draft omitted the recorded industry context")
    all_text = "\n".join(required_texts)
    if any(pattern.search(all_text) for pattern in UNSUPPORTED_CLAIM_PATTERNS):
        raise ValueError("Generated draft contains an unsupported business claim")
    contact_name = (lead.get("contact_name") or "").casefold()
    allowed_greeting_names = set(contact_name.split())
    for greeting in NAMED_GREETING_PATTERN.findall(all_text):
        if not contact_name or greeting.casefold() not in allowed_greeting_names:
            raise ValueError("Generated draft invented a contact name")
    recorded_email = (lead.get("contact_email") or "").casefold()
    if any(email.casefold() != recorded_email for email in EMAIL_PATTERN.findall(all_text)):
        raise ValueError("Generated draft invented an email address")
    synthetic_signal = (lead.get("growth_signal") or "").strip()
    if lead.get("is_synthetic") and synthetic_signal and synthetic_signal.casefold() in all_text.casefold():
        raise ValueError("Generated draft treated a synthetic signal as real-world evidence")


def generate_outreach(lead: dict) -> dict:
    context = _context(lead)
    points = _personalization_points(context)
    limitations = _data_limitations(context, points)
    limited = _limited(context, points)
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return _fallback(context)

    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    try:
        from groq import Groq

        response = Groq(api_key=api_key).chat.completions.create(
            model=model,
            temperature=0.25,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": (
                    "Write a specific first-touch email and short LinkedIn note using only the supplied lead JSON. "
                    "Return one JSON object with string fields subject, email_body, linkedin_note, plus string arrays "
                    "personalization_points and data_limitations. The subject, email body, and LinkedIn note must each "
                    "name the exact company. The email and LinkedIn note must use the recorded industry when present. "
                    "Make the rationale specific to the company's recorded industry, location, website, contact role, "
                    "or sourced evidence; do not merely swap a company name into a generic template. Never invent news, "
                    "a relationship, initiatives, hiring, products or benefits offered by the sender, financial facts, "
                    "or verification. Do not claim what the recipient's team is doing unless it is in the input. "
                    "Growth signals may be used "
                    "only when they have a source; synthetic records are not real-world evidence. Revenue and employee "
                    "values are unverified estimates and may only be described explicitly as estimates from the record. "
                    "If details are missing, avoid claims and state the limitation. Do not invent a contact name or email."
                )},
                {"role": "user", "content": json.dumps(context, ensure_ascii=True)},
            ],
        )
        draft = DraftContent.model_validate_json(response.choices[0].message.content or "")
        _require_company_grounding(draft, context)
        # Use server-derived metadata so the UI shows only recorded facts and known gaps.
        return {
            **draft.model_dump(),
            "personalization_points": points,
            "data_limitations": limitations,
            "generated_by": "groq",
            "limited_information": limited,
        }
    except Exception as exc:
        logger.warning(
            "Groq outreach failed; using company-grounded template exception_type=%s detail=%s",
            type(exc).__name__,
            _sanitize_provider_error(str(exc), api_key),
        )
        return _fallback(context)
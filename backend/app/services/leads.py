from datetime import datetime, timezone
import re
from types import SimpleNamespace

from bson import ObjectId
from fastapi import HTTPException
from pydantic import BaseModel
from pymongo.asynchronous.collection import AsyncCollection

from app.models import LeadDocument
from app.schemas import LeadInput, LeadResponse
from app.scoring.engine import score_lead


def normalize_domain(value: str | None) -> str | None:
    if not value:
        return None
    domain = re.sub(r"^https?://", "", value.strip().lower())
    domain = domain.split("/", 1)[0].split(":", 1)[0].rstrip(".")
    return domain.removeprefix("www.") or None


def normalize_text(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def normalized_identity(company_name: str, location: str | None) -> tuple[str, str]:
    return normalize_text(company_name), normalize_text(location)


def duplicate_filter(company_name: str, location: str | None, domain: str | None) -> dict:
    normalized_name, normalized_location = normalized_identity(company_name, location)
    clauses = [{
        "normalized_company_name": normalized_name,
        "normalized_location": normalized_location,
    }]
    normalized_domain = normalize_domain(domain)
    if normalized_domain:
        clauses.insert(0, {"normalized_domain": normalized_domain})
    return {"$or": clauses}


def build_document(payload: LeadInput | dict, *, source: str | None = None, is_synthetic: bool | None = None, saved: bool = False) -> dict:
    values = payload.model_dump() if isinstance(payload, BaseModel) else dict(payload)
    values["domain"] = normalize_domain(values.get("domain"))
    if source is not None:
        values["source"] = source
    if is_synthetic is not None:
        values["is_synthetic"] = is_synthetic
    now = datetime.now(timezone.utc)
    values.setdefault("saved", saved)
    values.setdefault("created_at", now)
    values.setdefault("updated_at", now)
    identity_name, identity_location = normalized_identity(values["company_name"], values.get("location"))
    scoring_input = SimpleNamespace(**values)
    result = score_lead(scoring_input)
    document = LeadDocument(
        **values,
        normalized_domain=values["domain"],
        normalized_company_name=identity_name,
        normalized_location=identity_location,
        fallback_key=(f"{identity_name}|{identity_location}" if not values["domain"] else None),
        score=result.score,
        score_breakdown=result.breakdown,
        reasons=result.reasons,
        missing_information=result.missing_information,
        recommended_next_action=result.recommended_next_action,
        data_completeness=result.data_completeness,
        priority=result.priority,
    )
    return document.model_dump(exclude={"id"})


def to_record(document: dict) -> LeadDocument:
    values = {key: value for key, value in document.items() if key != "_id"}
    values["id"] = str(document["_id"])
    return LeadDocument.model_validate(values)


def serialize_lead(document: dict) -> dict:
    record = to_record(document)
    return LeadResponse.model_validate(record.model_dump()).model_dump(mode="json")


def parse_object_id(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(status_code=422, detail="lead_id must be a valid MongoDB ObjectId")
    return ObjectId(value)


def build_filter(
    *, search: str | None = None, industry: str | None = None, location: str | None = None,
    revenue_min: float | None = None, revenue_max: float | None = None,
    priority: str | None = None, min_score: int | None = None, saved_only: bool = False,
) -> dict:
    clauses: list[dict] = []
    if search and search.strip():
        pattern = re.escape(search.strip())
        clauses.append({"$or": [
            {field: {"$regex": pattern, "$options": "i"}}
            for field in ("company_name", "contact_name", "domain")
        ]})
    if industry:
        clauses.append({"industry": industry})
    if location and location.strip():
        clauses.append({"location": {"$regex": re.escape(location.strip()), "$options": "i"}})
    revenue = {}
    if revenue_min is not None:
        revenue["$gte"] = revenue_min
    if revenue_max is not None:
        revenue["$lte"] = revenue_max
    if revenue:
        clauses.append({"estimated_revenue": revenue})
    if priority:
        clauses.append({"priority": priority})
    if min_score is not None:
        clauses.append({"score": {"$gte": min_score}})
    if saved_only:
        clauses.append({"saved": True})
    if not clauses:
        return {}
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def combine_filters(*filters: dict) -> dict:
    present = [query for query in filters if query]
    if not present:
        return {}
    return present[0] if len(present) == 1 else {"$and": present}


async def insert_lead(collection: AsyncCollection, payload: LeadInput, *, source: str | None = None, is_synthetic: bool | None = None, saved: bool = False) -> dict | None:
    document = build_document(payload, source=source, is_synthetic=is_synthetic, saved=saved)
    duplicate = await collection.find_one(duplicate_filter(document["company_name"], document.get("location"), document.get("normalized_domain")), {"_id": 1})
    if duplicate:
        return None
    result = await collection.insert_one(document)
    document["_id"] = result.inserted_id
    return document

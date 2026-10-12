import csv
import io
import math
import re
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pymongo.errors import DuplicateKeyError, PyMongoError
from pymongo.asynchronous.collection import AsyncCollection
from starlette.concurrency import run_in_threadpool

from app.database import get_collection
from app.models import LeadDocument
from app.schemas import ImportReport, LeadCreate, LeadResponse, OutreachDraft, SaveInput
from app.scoring.engine import WEIGHTS
from app.services.leads import (
    build_document,
    build_filter,
    combine_filters,
    duplicate_filter,
    normalize_domain,
    parse_object_id,
    serialize_lead,
    to_record,
)
from app.services.outreach import generate_outreach

router = APIRouter(prefix="/api")


def dashboard_pipeline() -> list[dict]:
    field_count = {"$add": [
        {"$cond": [{"$and": [
            {"$ne": [{"$ifNull": [f"${field}", None]}, None]},
            {"$ne": [f"${field}", ""]},
        ]}, 1, 0]}
        for field in (
            "company_name", "industry", "location", "estimated_revenue", "employee_count",
            "domain", "contact_name", "contact_title", "contact_email",
        )
    ]}
    contact_complete = {"$and": [
        {"$ne": [{"$ifNull": [f"${field}", ""]}, ""]}
        for field in ("contact_name", "contact_title", "contact_email")
    ]}
    return [
        {"$set": {"_field_count": field_count, "_contact_complete": contact_complete}},
        {"$facet": {
            "metrics": [{"$group": {
                "_id": None,
                "total_leads": {"$sum": 1},
                "high_priority_leads": {"$sum": {"$cond": [{"$eq": ["$priority", "High"]}, 1, 0]}},
                "average_score": {"$avg": "$score"},
                "complete_contacts": {"$sum": {"$cond": ["$_contact_complete", 1, 0]}},
                "average_field_count": {"$avg": "$_field_count"},
            }}],
            "distribution": [{"$group": {"_id": "$priority", "count": {"$sum": 1}}}],
            "recent_leads": [{"$sort": {"created_at": -1, "_id": -1}}, {"$limit": 6}],
            "top_leads": [{"$sort": {"score": -1, "company_name": 1}}, {"$limit": 5}],
            "industries": [{"$match": {"industry": {"$type": "string", "$ne": ""}}}, {"$group": {"_id": "$industry"}}, {"$sort": {"_id": 1}}],
            "locations": [{"$match": {"location": {"$type": "string", "$ne": ""}}}, {"$group": {"_id": "$location"}}, {"$sort": {"_id": 1}}],
        }},
    ]


async def dashboard_data(collection: AsyncCollection) -> dict:
    cursor = await collection.aggregate(dashboard_pipeline())
    aggregation = await cursor.to_list(length=1)
    facets = aggregation[0] if aggregation else {}
    metrics = (facets.get("metrics") or [{}])[0]
    total = metrics.get("total_leads", 0)
    contacts = metrics.get("complete_contacts", 0)
    distribution_counts = {item["_id"]: item["count"] for item in facets.get("distribution", [])}
    return {
        "total_leads": total,
        "high_priority_leads": metrics.get("high_priority_leads", 0),
        "average_score": round(metrics.get("average_score") or 0, 1),
        "complete_contact_percentage": round(contacts / total * 100) if total else 0,
        "data_completeness_percentage": round((metrics.get("average_field_count") or 0) / 9 * 100) if total else 0,
        "distribution": [{"priority": label, "count": distribution_counts.get(label, 0)} for label in ("High", "Medium", "Low")],
        "recent_leads": [serialize_lead(document) for document in facets.get("recent_leads", [])],
        "top_leads": [serialize_lead(document) for document in facets.get("top_leads", [])],
        "industries": [item["_id"] for item in facets.get("industries", [])],
        "locations": [item["_id"] for item in facets.get("locations", [])],
        "score_weights": WEIGHTS,
    }


@router.get("/health")
async def health(collection: AsyncCollection = Depends(get_collection)):
    try:
        await collection.database.command("ping")
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail="MongoDB is unavailable") from exc
    return {"status": "ok", "service": "saasquatch-lead-intelligence"}


@router.get("/dashboard")
async def dashboard(collection: AsyncCollection = Depends(get_collection)):
    return await dashboard_data(collection)


@router.get("/leads")
async def list_leads(
    search: str | None = None,
    industry: str | None = None,
    location: str | None = None,
    revenue_min: float | None = Query(default=None, ge=0),
    revenue_max: float | None = Query(default=None, ge=0),
    priority: str | None = Query(default=None, pattern="^(High|Medium|Low)$"),
    min_score: int | None = Query(default=None, ge=0, le=100),
    saved_only: bool = False,
    sort_by: str = Query(default="created_at", pattern="^(company_name|score|estimated_revenue|created_at)$"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    collection: AsyncCollection = Depends(get_collection),
):
    if revenue_min is not None and revenue_max is not None and revenue_min > revenue_max:
        raise HTTPException(status_code=422, detail="Minimum revenue cannot exceed maximum revenue")
    query = build_filter(search=search, industry=industry, location=location,
                         revenue_min=revenue_min, revenue_max=revenue_max,
                         priority=priority, min_score=min_score, saved_only=saved_only)
    total = await collection.count_documents(query)
    direction = -1 if sort_dir == "desc" else 1
    sort_field = "company_name" if sort_by == "company_name" else ("score" if sort_by == "score" else sort_by)
    cursor = collection.find(query).sort([(sort_field, direction), ("_id", direction)])
    documents = await cursor.skip((page - 1) * page_size).limit(page_size).to_list(length=page_size)
    return {
        "items": [serialize_lead(document) for document in documents],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size),
    }


@router.get("/leads/export")
async def export_leads(
    selected_ids: str | None = None,
    search: str | None = None,
    industry: str | None = None,
    location: str | None = None,
    revenue_min: float | None = None,
    revenue_max: float | None = None,
    priority: str | None = None,
    min_score: int | None = None,
    saved_only: bool = False,
    collection: AsyncCollection = Depends(get_collection),
):
    if revenue_min is not None and revenue_max is not None and revenue_min > revenue_max:
        raise HTTPException(status_code=422, detail="Minimum revenue cannot exceed maximum revenue")
    query = build_filter(search=search, industry=industry, location=location,
                         revenue_min=revenue_min, revenue_max=revenue_max,
                         priority=priority, min_score=min_score, saved_only=saved_only)
    if selected_ids:
        try:
            ids = [parse_object_id(value) for value in selected_ids.split(",") if value]
        except HTTPException as exc:
            raise HTTPException(status_code=422, detail="selected_ids must be comma-separated MongoDB ObjectIds") from exc
        query = combine_filters(query, {"_id": {"$in": ids}})
    documents = await collection.find(query).sort([("created_at", -1), ("_id", -1)]).to_list(length=None)
    output = io.StringIO(newline="")
    columns = ["company_name", "industry", "location", "estimated_revenue", "employee_count", "domain",
               "contact_name", "contact_title", "contact_email", "score", "company_fit", "revenue_fit",
               "decision_maker", "growth_signals", "data_completeness", "priority", "reasons", "missing_information"]
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for document in documents:
        row = serialize_lead(document)
        record = {key: row.get(key, "") for key in columns}
        record.update(row["score_breakdown"])
        record["reasons"] = " | ".join(row["reasons"])
        record["missing_information"] = " | ".join(row["missing_information"])
        for key, value in record.items():
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
                record[key] = "'" + value
        writer.writerow(record)
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=leads-export.csv"})


@router.post("/leads", response_model=LeadResponse, status_code=201)
async def create_lead(payload: LeadCreate, collection: AsyncCollection = Depends(get_collection)):
    query = duplicate_filter(payload.company_name, payload.location, payload.domain)
    if await collection.find_one(query, {"_id": 1}):
        raise HTTPException(status_code=409, detail="A lead with this company identity already exists")
    document = build_document(payload)
    try:
        result = await collection.insert_one(document)
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail="A lead with this company identity already exists") from exc
    document["_id"] = result.inserted_id
    return serialize_lead(document)


ALIASES = {
    "company_name": ("company", "company name", "company_name", "name", "account"),
    "industry": ("industry", "sector"),
    "location": ("location", "city", "company location"),
    "estimated_revenue": ("revenue", "estimated revenue", "estimated_revenue", "annual revenue"),
    "employee_count": ("employees", "employee count", "employee_count", "headcount"),
    "domain": ("domain", "website", "company domain", "url"),
    "contact_name": ("contact", "contact name", "contact_name", "full name"),
    "contact_title": ("title", "contact title", "contact_title", "job title"),
    "contact_email": ("email", "contact email", "contact_email"),
    "growth_signal": ("growth signal", "growth_signal", "growth evidence"),
    "growth_signal_source": ("growth source", "growth_signal_source", "signal source"),
}


def parse_number(value: str | None, *, integer: bool = False) -> int | float | None:
    if value is None or not value.strip():
        return None
    cleaned = value.strip().replace(",", "").replace("$", "")
    multiplier = 1
    if cleaned[-1:].lower() in ("k", "m", "b"):
        multiplier = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}[cleaned[-1].lower()]
        cleaned = cleaned[:-1]
    number = float(cleaned) * multiplier
    if not math.isfinite(number) or number < 0 or (integer and number % 1):
        raise ValueError("must be a non-negative whole number" if integer else "must be non-negative")
    return int(number) if integer else number


@router.post("/leads/import", response_model=ImportReport)
async def import_leads(file: UploadFile = File(...), collection: AsyncCollection = Depends(get_collection)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a .csv file")
    content = await file.read(5_000_001)
    if len(content) > 5_000_000:
        raise HTTPException(status_code=413, detail="CSV files must be 5 MB or smaller")
    try:
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise ValueError("CSV must contain a header row")
        headers = {re.sub(r"\s+", " ", header.strip().lower()): header for header in reader.fieldnames if header}
        mapping = {target: next((headers[alias] for alias in aliases if alias in headers), None) for target, aliases in ALIASES.items()}
        if mapping["company_name"] is None:
            raise ValueError("Required column missing: company or company_name")
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid CSV: {exc}") from exc
    accepted = rejected = duplicates = 0
    errors = []
    for row_number, row in enumerate(rows, start=2):
        try:
            if None in row:
                raise ValueError("row has more values than the header")
            values = {key: (row.get(header, "") or "").strip() if header else None for key, header in mapping.items()}
            if not values["company_name"]:
                raise ValueError("company name is required")
            values["estimated_revenue"] = parse_number(values["estimated_revenue"])
            values["employee_count"] = parse_number(values["employee_count"], integer=True)
            values["domain"] = normalize_domain(values["domain"])
            payload = LeadCreate.model_validate(values)
            query = duplicate_filter(payload.company_name, payload.location, payload.domain)
            if await collection.find_one(query, {"_id": 1}):
                duplicates += 1
                continue
            document = build_document(payload, source="CSV import", is_synthetic=False)
            try:
                await collection.insert_one(document)
                accepted += 1
            except DuplicateKeyError:
                duplicates += 1
        except (ValueError, TypeError) as exc:
            rejected += 1
            if len(errors) < 50:
                errors.append(f"Row {row_number}: {exc}")
    return {"accepted": accepted, "rejected": rejected, "duplicates": duplicates, "errors": errors}


@router.get("/leads/{lead_id}", response_model=LeadResponse)
async def get_lead(lead_id: str, collection: AsyncCollection = Depends(get_collection)):
    document = await collection.find_one({"_id": parse_object_id(lead_id)})
    if not document:
        raise HTTPException(status_code=404, detail="Lead not found")
    return serialize_lead(document)


@router.post("/leads/{lead_id}/score")
async def recalculate_score(lead_id: str, collection: AsyncCollection = Depends(get_collection)):
    object_id = parse_object_id(lead_id)
    document = await collection.find_one({"_id": object_id})
    if not document:
        raise HTTPException(status_code=404, detail="Lead not found")
    payload = {key: document.get(key) for key in LeadCreate.model_fields if key in document}
    rebuilt = build_document(payload, saved=document.get("saved", False))
    rebuilt["created_at"] = document["created_at"]
    await collection.update_one({"_id": object_id}, {"$set": rebuilt})
    document.update(rebuilt)
    return serialize_lead(document)


@router.post("/leads/{lead_id}/outreach", response_model=OutreachDraft)
async def create_outreach(lead_id: str, collection: AsyncCollection = Depends(get_collection)):
    document = await collection.find_one({"_id": parse_object_id(lead_id)})
    if not document:
        raise HTTPException(status_code=404, detail="Lead not found")
    record = to_record(document)
    return await run_in_threadpool(generate_outreach, record.model_dump())


@router.post("/leads/{lead_id}/save", response_model=LeadResponse)
async def save_lead(lead_id: str, payload: SaveInput, collection: AsyncCollection = Depends(get_collection)):
    object_id = parse_object_id(lead_id)
    result = await collection.update_one(
        {"_id": object_id}, {"$set": {"saved": payload.saved, "updated_at": datetime.now(timezone.utc)}}
    )
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="Lead not found")
    document = await collection.find_one({"_id": object_id})
    return serialize_lead(document)
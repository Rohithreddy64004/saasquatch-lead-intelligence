import os
import logging
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Request
from pymongo import ASCENDING, AsyncMongoClient
from pymongo.asynchronous.collection import AsyncCollection

BACKEND_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def load_backend_environment(env_file: str | Path = BACKEND_ENV_FILE) -> bool:
    return load_dotenv(env_file, override=False)


load_backend_environment()
logger = logging.getLogger(__name__)



def mongo_settings() -> tuple[str, str]:
    uri = os.getenv("MONGODB_URI", "").strip()
    database_name = os.getenv("MONGODB_DATABASE", "").strip()
    if not uri:
        raise RuntimeError("MONGODB_URI is required. Configure it in backend/.env.")
    if not database_name:
        raise RuntimeError("MONGODB_DATABASE is required. Configure it in backend/.env.")
    return uri, database_name


async def connect_database():
    try:
        uri, database_name = mongo_settings()
    except Exception as exc:
        logger.error(
            "MongoDB startup failure stage=configuration exception_type=%s detail=%s",
            type(exc).__name__,
            sanitize_mongo_error(str(exc)),
        )
        raise

    client = None
    stage = "client initialization"
    try:
        client = AsyncMongoClient(uri, serverSelectionTimeoutMS=5000, tz_aware=True)
        stage = "Atlas ping"
        await client.admin.command("ping")
        stage = "collection selection"
        collection = client[database_name]["leads"]
        stage = "index creation"
        await collection.create_index("normalized_domain", unique=True, partialFilterExpression={"normalized_domain": {"$type": "string"}}, name="uq_leads_domain")
        await collection.create_index("fallback_key", unique=True, partialFilterExpression={"fallback_key": {"$type": "string"}}, name="uq_leads_name_location_fallback")
        await collection.create_index("normalized_company_name", name="ix_leads_normalized_company")
        await collection.create_index([("normalized_company_name", ASCENDING), ("normalized_location", ASCENDING)], name="ix_leads_name_location")
        await collection.create_index("location", name="ix_leads_location")
        await collection.create_index("industry", name="ix_leads_industry")
        await collection.create_index("priority", name="ix_leads_priority")
        await collection.create_index("score", name="ix_leads_score")
        await collection.create_index([("saved", ASCENDING), ("created_at", ASCENDING)], name="ix_leads_saved_created")
        await collection.create_index("created_at", name="ix_leads_created")
        return client, collection
    except Exception as exc:
        detail = sanitize_mongo_error(str(exc), uri=uri, database_name=database_name)
        logger.error(
            "MongoDB startup failure stage=%s exception_type=%s detail=%s",
            stage,
            type(exc).__name__,
            detail or "<no safe detail available>",
        )
        if client is not None:
            try:
                await client.close()
            except Exception:
                pass
        raise RuntimeError(
            "Could not connect to or initialize MongoDB. Verify MONGODB_URI, "
            "MONGODB_DATABASE, Atlas network access, and database permissions."
        ) from None


def sanitize_mongo_error(message: str, *, uri: str = "", database_name: str = "") -> str:
    sanitized = message
    for secret in (uri, database_name):
        if secret:
            sanitized = sanitized.replace(secret, "[REDACTED]")
    sanitized = re.sub(r"(?i)mongodb(?:\+srv)?://[^\s'\"<>]+", "mongodb://[REDACTED]", sanitized)
    sanitized = re.sub(r"(?i)(mongodb(?:\+srv)?://)[^/@\s]+:[^/@\s]+@", r"\1[REDACTED]@", sanitized)
    sanitized = re.sub(r"(?<![\w])[^\s/:@]+:[^\s/@]+@(?=[^\s,;]+)", "[REDACTED]@", sanitized)
    return sanitized[:1000]


async def close_database(client: AsyncMongoClient | None) -> None:
    if client is not None:
        await client.close()


def get_collection(request: Request) -> AsyncCollection:
    collection = getattr(request.app.state, "leads", None)
    if collection is None:
        raise RuntimeError("MongoDB is not initialized")
    return collection

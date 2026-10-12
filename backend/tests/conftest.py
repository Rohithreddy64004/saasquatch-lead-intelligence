import os
import re
from copy import deepcopy

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.main import create_app


os.environ.pop("GROQ_API_KEY", None)


class FakeInsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class FakeInsertManyResult:
    def __init__(self, inserted_ids):
        self.inserted_ids = inserted_ids


class FakeUpdateResult:
    def __init__(self, matched_count):
        self.matched_count = matched_count


def _matches(document, query):
    for key, condition in query.items():
        if key == "$and":
            if not all(_matches(document, clause) for clause in condition):
                return False
            continue
        if key == "$or":
            if not any(_matches(document, clause) for clause in condition):
                return False
            continue
        value = document.get(key)
        if isinstance(condition, dict):
            if "$in" in condition and value not in condition["$in"]:
                return False
            if "$regex" in condition:
                flags = re.IGNORECASE if condition.get("$options") == "i" else 0
                if value is None or not re.search(condition["$regex"], str(value), flags):
                    return False
            if "$gte" in condition and (value is None or value < condition["$gte"]):
                return False
            if "$lte" in condition and (value is None or value > condition["$lte"]):
                return False
        elif value != condition:
            return False
    return True


class FakeCursor:
    def __init__(self, documents):
        self.documents = documents

    def sort(self, specification):
        for field, direction in reversed(specification):
            self.documents.sort(
                key=lambda item: (item.get(field) is None, item.get(field)),
                reverse=direction < 0,
            )
        return self

    def skip(self, count):
        self.documents = self.documents[count:]
        return self

    def limit(self, count):
        self.documents = self.documents[:count]
        return self

    async def to_list(self, length=None):
        result = deepcopy(self.documents)
        return result if length is None else result[:length]


class FakeCollection:
    def __init__(self):
        self.documents = []
        self.last_pipeline = None
        self.database = self
        self.fail_ping = False

    async def command(self, command_name):
        if self.fail_ping:
            from pymongo.errors import ServerSelectionTimeoutError
            raise ServerSelectionTimeoutError("isolated fake failure")
        assert command_name == "ping"
        return {"ok": 1}

    async def count_documents(self, query):
        return sum(_matches(document, query) for document in self.documents)

    async def find_one(self, query, projection=None):
        for document in self.documents:
            if _matches(document, query):
                return deepcopy(document)
        return None

    def find(self, query):
        return FakeCursor([deepcopy(document) for document in self.documents if _matches(document, query)])

    async def insert_one(self, document):
        for stored in self.documents:
            if document.get("normalized_domain") and stored.get("normalized_domain") == document["normalized_domain"]:
                from pymongo.errors import DuplicateKeyError
                raise DuplicateKeyError("duplicate normalized domain")
            if document.get("fallback_key") and stored.get("fallback_key") == document["fallback_key"]:
                from pymongo.errors import DuplicateKeyError
                raise DuplicateKeyError("duplicate fallback identity")
        stored = deepcopy(document)
        stored["_id"] = ObjectId()
        self.documents.append(stored)
        return FakeInsertResult(stored["_id"])

    async def insert_many(self, documents, ordered=True):
        ids = []
        for document in documents:
            result = await self.insert_one(document)
            ids.append(result.inserted_id)
        return FakeInsertManyResult(ids)

    async def update_one(self, query, update):
        for document in self.documents:
            if _matches(document, query):
                document.update(deepcopy(update.get("$set", {})))
                return FakeUpdateResult(1)
        return FakeUpdateResult(0)

    async def aggregate(self, pipeline):
        self.last_pipeline = pipeline
        documents = deepcopy(self.documents)
        facet_stage = next(stage["$facet"] for stage in pipeline if "$facet" in stage)
        counts = {priority: sum(item.get("priority") == priority for item in documents) for priority in ("High", "Medium", "Low")}
        field_names = ("company_name", "industry", "location", "estimated_revenue", "employee_count", "domain", "contact_name", "contact_title", "contact_email")
        complete_count = lambda item: sum(item.get(field) is not None and item.get(field) != "" for field in field_names)
        complete_contacts = sum(all(item.get(field) for field in ("contact_name", "contact_title", "contact_email")) for item in documents)
        total = len(documents)
        metrics = [{
            "total_leads": total,
            "high_priority_leads": counts["High"],
            "average_score": sum(item["score"] for item in documents) / total if total else None,
            "complete_contacts": complete_contacts,
            "average_field_count": sum(complete_count(item) for item in documents) / total if total else None,
        }] if total else []
        by_recent = sorted(documents, key=lambda item: (item.get("created_at"), item["_id"]), reverse=True)
        by_top = sorted(documents, key=lambda item: (-item["score"], item["company_name"]))
        result = [{
            "metrics": metrics,
            "distribution": [{"_id": name, "count": count} for name, count in counts.items() if count],
            "recent_leads": by_recent[:6],
            "top_leads": by_top[:5],
            "industries": [{"_id": value} for value in sorted({item["industry"] for item in documents if item.get("industry")})],
            "locations": [{"_id": value} for value in sorted({item["location"] for item in documents if item.get("location")})],
        }]
        assert "metrics" in facet_stage and "distribution" in facet_stage
        return FakeCursor(result)


@pytest.fixture
def mongo_collection():
    return FakeCollection()


@pytest.fixture
def client(mongo_collection):
    async def connector():
        return None, mongo_collection

    application = create_app(connector=connector, seed_data=True)
    with TestClient(application) as test_client:
        yield test_client
import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.database import mongo_settings
from app.models import LeadDocument
from app.schemas import LeadCreate
from app.services.leads import build_document, duplicate_filter, normalize_domain


def test_mongo_settings_require_uri_and_database_without_exposing_values(monkeypatch):
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.setenv("MONGODB_DATABASE", "test_db")
    with pytest.raises(RuntimeError, match="MONGODB_URI is required"):
        mongo_settings()

    monkeypatch.setenv("MONGODB_URI", "mongodb+srv://user:placeholder@cluster.example/")
    monkeypatch.delenv("MONGODB_DATABASE", raising=False)
    with pytest.raises(RuntimeError, match="MONGODB_DATABASE is required"):
        mongo_settings()


def test_pydantic_mongo_document_validates_fields_and_normalized_identity():
    payload = LeadCreate(company_name="  Example Systems ", location="Denver, CO", domain="https://WWW.Example.invalid/path")
    assert payload.company_name == "Example Systems"
    assert normalize_domain(payload.domain) == "example.invalid"
    document = build_document(payload)
    validated = LeadDocument.model_validate({**document, "_id": "ignored"})
    assert validated.normalized_company_name == "example systems"
    assert validated.normalized_location == "denver co"
    assert validated.normalized_domain == "example.invalid"
    assert validated.score == validated.score_breakdown["data_completeness"]
    assert validated.score_breakdown["company_fit"] == 0
    with pytest.raises(ValidationError):
        LeadCreate(company_name="Invalid Score", estimated_revenue=-10)


def test_duplicate_filter_checks_domain_and_name_location_fallback():
    query = duplicate_filter("Acme Inc.", "Austin, TX", "https://www.ACME.example/path")
    assert query["$or"] == [
        {"normalized_domain": "acme.example"},
        {"normalized_company_name": "acme inc", "normalized_location": "austin tx"},
    ]


def test_async_connection_factory_selects_configured_database_and_indexes(monkeypatch):
    import app.database as database

    class FakeAdmin:
        async def command(self, command):
            assert command == "ping"

    class FakeCollection:
        def __init__(self):
            self.indexes = []

        async def create_index(self, keys, **options):
            self.indexes.append((keys, options))

    class FakeDatabase:
        def __init__(self):
            self.collection = FakeCollection()

        def __getitem__(self, name):
            assert name == "leads"
            return self.collection

    class FakeClient:
        def __init__(self, uri, **options):
            self.uri = uri
            self.options = options
            self.admin = FakeAdmin()
            self.database = FakeDatabase()

        def __getitem__(self, name):
            assert name == "isolated_test_db"
            return self.database

    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("MONGODB_DATABASE", "isolated_test_db")
    monkeypatch.setattr(database, "AsyncMongoClient", FakeClient)
    client, collection = asyncio.run(database.connect_database())
    assert client.uri == "mongodb://localhost:27017"
    assert client.options["serverSelectionTimeoutMS"] == 5000
    assert len(collection.indexes) >= 8
    assert any(options.get("name") == "uq_leads_domain" for _, options in collection.indexes)
    assert any(options.get("name") == "ix_leads_score" for _, options in collection.indexes)


def test_async_connection_factory_closes_client_when_ping_fails(monkeypatch, caplog):
    import app.database as database
    from pymongo.errors import ServerSelectionTimeoutError

    password_sentinel = "QA_ONLY_SENTINEL_PASSWORD"
    database_sentinel = "QA_ONLY_SENTINEL_DATABASE"
    uri_sentinel = f"mongodb+srv://qa-user:{password_sentinel}@cluster.invalid/"

    class FakeAdmin:
        async def command(self, _command):
            raise ServerSelectionTimeoutError(f"TLS handshake failed for {uri_sentinel}; db={database_sentinel}")

    class FakeClient:
        last = None

        def __init__(self, *_args, **_kwargs):
            self.admin = FakeAdmin()
            self.closed = False
            FakeClient.last = self

        async def close(self):
            self.closed = True

    monkeypatch.setenv("MONGODB_URI", uri_sentinel)
    monkeypatch.setenv("MONGODB_DATABASE", database_sentinel)
    monkeypatch.setattr(database, "AsyncMongoClient", FakeClient)
    with pytest.raises(RuntimeError) as error:
        asyncio.run(database.connect_database())
    assert "TLS handshake failed" in caplog.text
    assert "ServerSelectionTimeoutError" in caplog.text
    assert uri_sentinel not in caplog.text
    assert password_sentinel not in caplog.text
    assert database_sentinel not in caplog.text
    assert "[REDACTED]" in caplog.text
    assert "Could not connect" in str(error.value)
    assert FakeClient.last.closed is True


def test_backend_env_loader_reads_values_from_isolated_file(monkeypatch, tmp_path):
    from app.database import load_backend_environment, mongo_settings

    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.delenv("MONGODB_DATABASE", raising=False)
    env_file = Path(tmp_path) / ".env"
    env_file.write_text(
        "MONGODB_URI=mongodb://test-host.invalid:27017\nMONGODB_DATABASE=isolated_test_db\n",
        encoding="utf-8",
    )
    assert load_backend_environment(env_file)
    assert mongo_settings() == ("mongodb://test-host.invalid:27017", "isolated_test_db")
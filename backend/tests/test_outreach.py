import json
from types import SimpleNamespace

import groq

from app.services import outreach


def _groq_payload(context):
    company = context["company_name"]
    industry = context.get("industry", "the listed industry")
    return {
        "subject": f"A {industry} conversation with {company}",
        "email_body": f"Hello {context.get('contact_name') or 'there'}, I am reaching out about {company} and its recorded {industry} focus.",
        "linkedin_note": f"Hi {context.get('contact_name') or 'there'}, I would like to connect about {company}'s {industry} focus.",
        "personalization_points": [f"Industry on record: {industry}"],
        "data_limitations": [],
    }


def test_groq_gets_each_selected_company_context_and_returns_distinct_drafts(monkeypatch):
    captured_contexts = []

    class FakeCompletions:
        def create(self, **kwargs):
            context = json.loads(kwargs["messages"][1]["content"])
            captured_contexts.append(context)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(_groq_payload(context))))])

    class FakeGroq:
        def __init__(self, api_key):
            assert api_key == "TEST_ONLY_GROQ_KEY_SENTINEL"
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setenv("GROQ_API_KEY", "TEST_ONLY_GROQ_KEY_SENTINEL")
    monkeypatch.setattr(groq, "Groq", FakeGroq)
    company_a = {
        "company_name": "Northstar Freight", "industry": "Logistics", "domain": "northstar.example",
        "location": "Austin, TX", "estimated_revenue": 8200000, "employee_count": 62,
        "contact_name": "Jamie Example", "contact_title": "Founder", "growth_signal": "New warehouse",
        "growth_signal_source": "Synthetic demo only", "is_synthetic": True,
    }
    company_b = {
        "company_name": "Juniper Clinical", "industry": "Healthcare Technology", "domain": "juniper.example",
        "location": "Denver, CO", "estimated_revenue": 4200000, "employee_count": 24,
        "contact_name": "Morgan Example", "contact_title": "CEO",
    }

    draft_a = outreach.generate_outreach(company_a)
    draft_b = outreach.generate_outreach(company_b)

    assert len(captured_contexts) == 2
    assert captured_contexts[0]["company_name"] == company_a["company_name"]
    assert captured_contexts[0]["domain"] == company_a["domain"]
    assert captured_contexts[0]["estimated_revenue"] == company_a["estimated_revenue"]
    assert captured_contexts[0]["employee_count"] == company_a["employee_count"]
    assert captured_contexts[0]["growth_signal_source"] == company_a["growth_signal_source"]
    assert captured_contexts[1]["company_name"] == company_b["company_name"]
    for field in ("subject", "email_body", "linkedin_note"):
        assert company_a["company_name"] in draft_a[field]
        assert company_b["company_name"] in draft_b[field]
        assert draft_a[field] != draft_b[field]
    assert draft_a["generated_by"] == draft_b["generated_by"] == "groq"
    assert draft_a["personalization_points"]
    assert any("synthetic" in item.lower() for item in draft_a["data_limitations"])


def test_missing_contact_uses_generic_greeting_without_inventing_person_or_email(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    lead = {"company_name": "Lumen Scheduling", "industry": "Healthcare Technology"}

    draft = outreach.generate_outreach(lead)

    assert draft["generated_by"] == "template_generated"
    assert draft["limited_information"] is True
    assert "Hello," in draft["email_body"]
    assert "Hi there" in draft["linkedin_note"]
    assert "@" not in draft["email_body"]
    assert "Lumen Scheduling" in draft["subject"]
    assert any("contact name" in item.lower() for item in draft["data_limitations"])


def test_groq_failure_uses_company_specific_fallback(monkeypatch, caplog):
    key = "gsk_QA_SENTINEL_NOT_A_REAL_API_KEY_123456789"

    class BrokenGroq:
        def __init__(self, api_key):
            assert api_key == key
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.fail))

        @staticmethod
        def fail(**_kwargs):
            raise RuntimeError(f"provider failed for {key}")

    monkeypatch.setenv("GROQ_API_KEY", key)
    monkeypatch.setattr(groq, "Groq", BrokenGroq)
    lead = {"company_name": "Copper Finch Analytics", "industry": "Financial Services", "location": "Boise, ID"}

    draft = outreach.generate_outreach(lead)

    assert draft["generated_by"] == "template_generated"
    assert "Copper Finch Analytics" in draft["subject"]
    assert "Financial Services" in draft["email_body"]
    assert "Boise, ID" in draft["linkedin_note"]
    assert key not in caplog.text
    assert "RuntimeError" in caplog.text


def test_invalid_groq_json_uses_company_specific_fallback(monkeypatch):
    class InvalidGroq:
        def __init__(self, api_key):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **_: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))])))

    monkeypatch.setenv("GROQ_API_KEY", "TEST_ONLY_KEY")
    monkeypatch.setattr(groq, "Groq", InvalidGroq)

    draft = outreach.generate_outreach({"company_name": "Blue Maple Commerce", "industry": "Retail Software"})

    assert draft["generated_by"] == "template_generated"
    assert "Blue Maple Commerce" in draft["subject"]
    assert "Retail Software" in draft["email_body"]
    assert "Blue Maple Commerce" in draft["linkedin_note"]


def test_unsupported_sender_product_claim_uses_grounded_fallback(monkeypatch):
    class ClaimingGroq:
        def __init__(self, _api_key):
            def create(**_kwargs):
                result = _groq_payload({"company_name": "Harbor Ledger", "industry": "Financial Services"})
                result["email_body"] += " Our platform can streamline your operations."
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(result)))])

            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))

    monkeypatch.setenv("GROQ_API_KEY", "TEST_ONLY_KEY")
    monkeypatch.setattr(groq, "Groq", ClaimingGroq)
    draft = outreach.generate_outreach({"company_name": "Harbor Ledger", "industry": "Financial Services"})

    assert draft["generated_by"] == "template_generated"
    assert "Harbor Ledger" in draft["email_body"]
    assert "our platform" not in draft["email_body"].lower()


def test_groq_invented_contact_name_is_rejected_when_contact_missing(monkeypatch):
    class InventingGroq:
        def __init__(self, _api_key):
            def create(**_kwargs):
                result = _groq_payload({"company_name": "Northwind Robotics", "industry": "Robotics"})
                result["email_body"] = result["email_body"].replace("Hello there", "Hi Morgan")
                result["linkedin_note"] = result["linkedin_note"].replace("there", "Morgan")
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(result)))])

            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))

    monkeypatch.setenv("GROQ_API_KEY", "TEST_ONLY_KEY")
    monkeypatch.setattr(groq, "Groq", InventingGroq)
    draft = outreach.generate_outreach({"company_name": "Northwind Robotics", "industry": "Robotics"})

    assert draft["generated_by"] == "template_generated"
    assert "Hello," in draft["email_body"]
    assert "Morgan" not in draft["email_body"]


def test_groq_invented_email_address_is_rejected(monkeypatch):
    class EmailInventingGroq:
        def __init__(self, _api_key):
            def create(**_kwargs):
                result = _groq_payload({"company_name": "Juniper Supply", "industry": "Logistics"})
                result["email_body"] += " Contact me at alex@juniper.example."
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(result)))])

            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))

    monkeypatch.setenv("GROQ_API_KEY", "TEST_ONLY_KEY")
    monkeypatch.setattr(groq, "Groq", EmailInventingGroq)
    draft = outreach.generate_outreach({"company_name": "Juniper Supply", "industry": "Logistics"})

    assert draft["generated_by"] == "template_generated"
    assert "alex@juniper.example" not in draft["email_body"]
from bson import ObjectId


def test_health_and_dashboard_use_aggregation(client, mongo_collection):
    assert client.get("/api/health").json()["status"] == "ok"
    dashboard = client.get("/api/dashboard").json()
    assert dashboard["total_leads"] == 48
    assert dashboard["average_score"] > 0
    assert sum(row["count"] for row in dashboard["distribution"]) == 48
    assert dashboard["recent_leads"]
    assert dashboard["top_leads"][0]["score"] >= dashboard["top_leads"][-1]["score"]
    assert "$facet" in mongo_collection.last_pipeline[-1]


def test_health_reports_mongo_unavailable_as_503(client, mongo_collection):
    mongo_collection.fail_ping = True
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["detail"] == "MongoDB is unavailable"


def test_lead_filtering_sorting_pagination_detail_and_score(client):
    first_page = client.get("/api/leads?page=1&page_size=5&sort_by=company_name&sort_dir=asc").json()
    second_page = client.get("/api/leads?page=2&page_size=5&sort_by=company_name&sort_dir=asc").json()
    assert len(first_page["items"]) == 5
    assert first_page["total"] == 48
    assert first_page["items"][0]["company_name"] < second_page["items"][0]["company_name"]
    assert first_page["items"][0]["id"] != second_page["items"][0]["id"]

    selected = client.get("/api/leads?industry=SaaS&location=Austin&revenue_min=1000000&priority=High&min_score=80").json()
    assert selected["items"]
    assert all(item["industry"] == "SaaS" and "Austin" in item["location"] and item["score"] >= 80 for item in selected["items"])
    saved = client.get("/api/leads?saved_only=true").json()
    assert saved["total"] == 3
    assert client.get("/api/leads?revenue_min=5&revenue_max=2").status_code == 422

    lead_id = first_page["items"][0]["id"]
    detail = client.get(f"/api/leads/{lead_id}").json()
    assert detail["id"] == lead_id
    assert sum(detail["score_breakdown"].values()) == detail["score"]
    saved_before_rescore = client.post(f"/api/leads/{lead_id}/save", json={"saved": True}).json()
    assert client.get("/api/leads/not-an-object-id").status_code == 422
    assert client.get(f"/api/leads/{ObjectId()}").status_code == 404
    rescored = client.post(f"/api/leads/{lead_id}/score").json()
    assert rescored["score"] == detail["score"]
    assert rescored["saved"] is True
    assert rescored["created_at"] == saved_before_rescore["created_at"]


def test_create_validation_and_domain_or_name_location_duplicate_detection(client):
    payload = {"company_name": "A New Fictional Co", "location": "Denver CO", "domain": "https://www.new-fic.example/path"}
    created = client.post("/api/leads", json=payload)
    assert created.status_code == 201
    assert created.json()["domain"] == "new-fic.example"
    assert client.post("/api/leads", json={**payload, "company_name": "Different Name"}).status_code == 409
    assert client.post("/api/leads", json={"company_name": "a new fictional co", "location": "Denver, CO"}).status_code == 409
    assert client.post("/api/leads", json={"company_name": "   "}).status_code == 422
    assert client.post("/api/leads", json={"company_name": "Negative Revenue", "estimated_revenue": -1}).status_code == 422


def test_complete_and_incomplete_records_have_validated_score_fields(client):
    complete_payload = {
        "company_name": "Complete Sample Systems", "industry": "SaaS", "location": "Austin, TX",
        "estimated_revenue": 5_000_000, "employee_count": 40, "domain": "complete-sample.example",
        "contact_name": "Alex Example", "contact_title": "Founder & CEO",
        "contact_email": "alex@example.invalid", "growth_signal": "Synthetic sample hiring signal",
        "growth_signal_source": "Synthetic demonstration record",
    }
    complete = client.post("/api/leads", json=complete_payload).json()
    incomplete = client.post("/api/leads", json={"company_name": "Incomplete Sample"}).json()
    assert complete["score"] == 100
    assert complete["data_completeness"] == 100
    assert incomplete["score"] == incomplete["score_breakdown"]["data_completeness"]
    assert incomplete["score_breakdown"]["company_fit"] == 0
    assert incomplete["score_breakdown"]["revenue_fit"] == 0
    assert incomplete["data_completeness"] < 100
    assert "Industry" in incomplete["missing_information"]


def test_save_and_template_outreach_without_groq_key(client, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    lead_id = client.get("/api/leads?page_size=1").json()["items"][0]["id"]
    saved = client.post(f"/api/leads/{lead_id}/save", json={"saved": True}).json()
    assert saved["saved"] is True
    draft = client.post(f"/api/leads/{lead_id}/outreach").json()
    assert draft["generated_by"] == "template_generated"
    assert draft["subject"]
    assert draft["email_body"]
    assert draft["linkedin_note"]
    assert isinstance(draft["personalization_points"], list)
    assert isinstance(draft["data_limitations"], list)
    assert client.post(f"/api/leads/{ObjectId()}/save", json={"saved": True}).status_code == 404


def test_outreach_endpoint_passes_selected_lead_context(client, monkeypatch):
    import app.api.routes as routes

    selected = client.get("/api/leads?page_size=1").json()["items"][0]
    received = {}

    def fake_generator(lead):
        received.update(lead)
        return {
            "subject": f"A conversation about {lead['company_name']}",
            "email_body": f"Hello, I am reaching out about {lead['company_name']} in {lead['industry']}.",
            "linkedin_note": f"Connect with {lead['company_name']} about {lead['industry']}.",
            "personalization_points": [f"Industry on record: {lead['industry']}"],
            "data_limitations": [],
            "generated_by": "groq",
            "limited_information": False,
        }

    monkeypatch.setattr(routes, "generate_outreach", fake_generator)
    response = client.post(f"/api/leads/{selected['id']}/outreach")

    assert response.status_code == 200
    assert received["company_name"] == selected["company_name"]
    assert received["domain"] == selected["domain"]
    assert received["estimated_revenue"] == selected["estimated_revenue"]
    assert received["employee_count"] == selected["employee_count"]
    assert received["contact_name"] == selected["contact_name"]
    assert response.json()["email_body"].find(selected["company_name"]) >= 0


def test_import_validates_rows_and_counts_duplicates(client):
    content = (
        "company_name,industry,location,revenue,domain,contact_name,contact_email\n"
        "New Sample Co,SaaS,Denver CO,2500000,new-sample.example,Pat Example,pat@example.invalid\n"
        "Different name,SaaS,Denver CO,2500000,https://www.new-sample.example/x,Pat Example,pat@example.invalid\n"
        "Broken Row,SaaS,Austin,not-a-number,bad.example,,\n"
    )
    response = client.post("/api/leads/import", files={"file": ("leads.csv", content, "text/csv")})
    assert response.status_code == 200
    assert response.json()["accepted"] == 1
    assert response.json()["duplicates"] == 1
    assert response.json()["rejected"] == 1
    assert "Row 4" in response.json()["errors"][0]
    imported = client.get("/api/leads?search=New%20Sample%20Co").json()["items"][0]
    assert imported["source"] == "CSV import"
    assert imported["is_synthetic"] is False


def test_import_invalid_csv_and_malformed_rows(client):
    assert client.post("/api/leads/import", files={"file": ("leads.txt", "company_name\nName", "text/plain")}).status_code == 400
    missing_header = client.post("/api/leads/import", files={"file": ("leads.csv", "industry,location\nSaaS,Austin", "text/csv")})
    assert missing_header.status_code == 400
    malformed = client.post("/api/leads/import", files={"file": ("leads.csv", "company_name,industry\nToo,Many,Cells", "text/csv")})
    assert malformed.json()["rejected"] == 1
    non_finite = client.post("/api/leads/import", files={"file": ("leads.csv", "company_name,revenue\nNonfinite,nan", "text/csv")})
    assert non_finite.json()["rejected"] == 1


def test_export_selected_and_formula_injection(client):
    created = client.post("/api/leads", json={"company_name": "=1+1", "location": "Formula City"})
    assert created.status_code == 201
    lead_id = created.json()["id"]
    response = client.get(f"/api/leads/export?selected_ids={lead_id}")
    assert response.status_code == 200
    assert "'=1+1" in response.text
    assert client.get("/api/leads/export?selected_ids=not-an-id").status_code == 422
    high = client.get("/api/leads/export?priority=High")
    assert "company_fit" in high.text and "missing_information" in high.text
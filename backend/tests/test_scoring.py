from types import SimpleNamespace

from app.scoring.engine import WEIGHTS, score_lead


def complete_lead(**overrides):
    values = {
        "company_name": "Example Systems",
        "industry": "SaaS",
        "location": "Austin, TX",
        "estimated_revenue": 5_000_000,
        "employee_count": 40,
        "domain": "example.invalid",
        "contact_name": "Alex Morgan",
        "contact_title": "Founder & CEO",
        "contact_email": "alex@example.invalid",
        "growth_signal": "Synthetic demo hiring signal.",
        "growth_signal_source": "Synthetic demo data; not researched.",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_weights_total_one_hundred_and_perfect_fit_scores_high():
    result = score_lead(complete_lead())
    assert sum(WEIGHTS.values()) == 100
    assert result.breakdown == WEIGHTS
    assert result.score == 100
    assert result.priority == "High"
    assert result.data_completeness == 100


def test_priority_boundaries():
    from app.scoring.engine import _priority

    assert _priority(80) == "High"
    assert _priority(79) == "Medium"
    assert _priority(60) == "Medium"
    assert _priority(59) == "Low"
    assert _priority(0) == "Low"


def test_missing_fields_and_unsourced_growth_receive_no_positive_credit():
    result = score_lead(complete_lead(
        industry=None, estimated_revenue=None, contact_title=None,
        growth_signal="Claim with no citation", growth_signal_source=None,
        contact_name=None, contact_email=None, location=None, domain=None,
        employee_count=None,
    ))
    assert result.breakdown["company_fit"] == 0
    assert result.breakdown["revenue_fit"] == 0
    assert result.breakdown["decision_maker"] == 0
    assert result.breakdown["growth_signals"] == 0
    assert result.score < 80
    assert result.data_completeness < 100
    assert "Growth signal source" in result.missing_information
    assert "Industry" in result.missing_information
    assert "Contact email" in result.missing_information


def test_category_calculations_award_partial_credit_for_near_fits():
    result = score_lead(complete_lead(
        industry="Logistics", estimated_revenue=75_000_000,
        contact_title="Sales Manager", growth_signal=None, growth_signal_source=None,
    ))
    assert result.breakdown["company_fit"] == 8
    assert result.breakdown["revenue_fit"] == 12
    assert result.breakdown["decision_maker"] == 8
    assert result.breakdown["growth_signals"] == 0
    assert result.priority in {"Low", "Medium"}


def test_partial_credit_scales_with_configured_weight(monkeypatch):
    from app.scoring import engine

    monkeypatch.setitem(engine.WEIGHTS, "company_fit", 30)
    result = engine.score_lead(complete_lead(industry="Logistics"))
    assert result.breakdown["company_fit"] == 10

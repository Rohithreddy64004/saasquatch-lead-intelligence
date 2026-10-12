"""MongoDB lead document validation schemas."""

from datetime import datetime, timezone

from pydantic import ConfigDict, Field

from app.schemas import LeadInput


class LeadDocument(LeadInput):
    model_config = ConfigDict(extra="ignore")

    id: str = ""
    normalized_domain: str | None = None
    normalized_company_name: str
    normalized_location: str
    fallback_key: str | None = None
    saved: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    score: int = Field(ge=0, le=100)
    score_breakdown: dict[str, int]
    reasons: list[str]
    missing_information: list[str]
    recommended_next_action: str
    data_completeness: int = Field(ge=0, le=100)
    priority: str = Field(pattern="^(High|Medium|Low)$")
from datetime import datetime
 
from typing import Literal 

 
from pydantic import BaseModel, ConfigDict, Field, field_validator



class LeadInput(BaseModel):
    company_name: str = Field(min_length=1, max_length=180)
    industry: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=120)
    estimated_revenue: float | None = Field(default=None, ge=0)
    employee_count: int | None = Field(default=None, ge=0)
    domain: str | None = Field(default=None, max_length=180)
    contact_name: str | None = Field(default=None, max_length=120)
    contact_title: str | None = Field(default=None, max_length=120)
    contact_email: str | None = Field(default=None, max_length=180)
    growth_signal: str | None = Field(default=None, max_length=1000)
    growth_signal_source: str | None = Field(default=None, max_length=180)
    source: str = Field(default="Manual entry", max_length=80)
    is_synthetic: bool = False

    @field_validator("company_name")
    @classmethod
    def trim_company_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Company name cannot be blank")
        return value


class LeadCreate(LeadInput):
    pass


class OutreachDraft(BaseModel):
    subject: str
    email_body: str
    linkedin_note: str
    personalization_points: list[str]
    data_limitations: list[str]
    generated_by: Literal["groq", "template_generated"]
    limited_information: bool


class SaveInput(BaseModel):
    saved: bool


class ImportReport(BaseModel):
    accepted: int
    rejected: int
    duplicates: int
    errors: list[str]


class LeadResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    company_name: str
    industry: str | None
    location: str | None
    estimated_revenue: float | None
    employee_count: int | None
    domain: str | None
    contact_name: str | None
    contact_title: str | None
    contact_email: str | None
    growth_signal: str | None
    growth_signal_source: str | None
    source: str
    is_synthetic: bool
    saved: bool
    created_at: datetime
    updated_at: datetime
    score: int
    score_breakdown: dict[str, int]
    reasons: list[str]
    missing_information: list[str]
    recommended_next_action: str
    data_completeness: int
    priority: str


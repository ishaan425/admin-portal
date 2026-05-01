"""Contracts for Enterprise job opening APIs."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


WorkMode = Literal["onsite", "remote", "hybrid"]
EmploymentType = Literal["full_time", "part_time", "contract", "internship"]
JobStatus = Literal["draft", "published", "archived"]


class JobContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QScorePreferences(JobContractModel):
    min_overall: int | None = Field(default=None, ge=0, le=100)


class JobOpeningBase(JobContractModel):
    title: str = Field(min_length=1, max_length=200)
    company_name: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=200)
    work_mode: WorkMode
    employment_type: EmploymentType
    experience_min_years: int | None = Field(default=None, ge=0, le=80)
    experience_max_years: int | None = Field(default=None, ge=0, le=80)
    skills: list[str] = Field(default_factory=list, max_length=50)
    description: str | None = Field(default=None, max_length=12000)
    responsibilities: list[str] = Field(default_factory=list, max_length=50)
    requirements: list[str] = Field(default_factory=list, max_length=50)
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=3)
    open_positions: int | None = Field(default=None, ge=1, le=100000)
    application_deadline: date | None = None
    external_apply_url: str | None = Field(default=None, max_length=2000)
    qscore_preferences: QScorePreferences = Field(default_factory=QScorePreferences)

    @field_validator("title", "company_name", "department", "location", "currency", mode="before")
    @classmethod
    def strip_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("skills", "responsibilities", "requirements")
    @classmethod
    def normalize_string_list(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in value:
            normalized = item.strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key not in seen:
                seen.add(key)
                cleaned.append(normalized)
        return cleaned

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else None

    @model_validator(mode="after")
    def validate_ranges(self) -> "JobOpeningBase":
        if (
            self.experience_min_years is not None
            and self.experience_max_years is not None
            and self.experience_min_years > self.experience_max_years
        ):
            raise ValueError("experience_min_years cannot exceed experience_max_years.")
        if self.salary_min is not None and self.salary_max is not None and self.salary_min > self.salary_max:
            raise ValueError("salary_min cannot exceed salary_max.")
        return self


class JobOpeningCreate(JobOpeningBase):
    pass


class JobOpeningUpdate(JobContractModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    company_name: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=200)
    work_mode: WorkMode | None = None
    employment_type: EmploymentType | None = None
    experience_min_years: int | None = Field(default=None, ge=0, le=80)
    experience_max_years: int | None = Field(default=None, ge=0, le=80)
    skills: list[str] | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=12000)
    responsibilities: list[str] | None = Field(default=None, max_length=50)
    requirements: list[str] | None = Field(default=None, max_length=50)
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=3)
    open_positions: int | None = Field(default=None, ge=1, le=100000)
    application_deadline: date | None = None
    external_apply_url: str | None = Field(default=None, max_length=2000)
    qscore_preferences: QScorePreferences | None = None

    @field_validator("title", "company_name", "department", "location", "currency", mode="before")
    @classmethod
    def strip_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("skills", "responsibilities", "requirements")
    @classmethod
    def normalize_string_list(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return JobOpeningBase.normalize_string_list(value)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else None


class JobOpeningResponse(JobContractModel):
    id: str
    organization_id: str
    created_by_clerk_user_id: str
    title: str
    status: JobStatus
    metadata: dict
    created_at: str | None = None
    updated_at: str | None = None

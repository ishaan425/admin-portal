"""Pydantic schema for parsed resume data."""

from __future__ import annotations

import re
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def string_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def string_list(value: Any) -> list[str]:
    return [string_value(item) for item in list_value(value) if string_value(item)]


def normalize_person_name(value: Any) -> str:
    name = re.sub(r"\s+", " ", string_value(value))
    if not name:
        return ""

    return " ".join(_normalize_name_token(token) for token in name.split(" "))


def normalize_email(value: Any) -> str:
    return string_value(value).lower()


def normalize_url(value: Any) -> str:
    return string_value(value)


def _normalize_name_token(token: str) -> str:
    parts = re.split(r"([-'])", token)
    return "".join(_normalize_simple_name_part(part) for part in parts)


def _normalize_simple_name_part(part: str) -> str:
    if part in {"-", "'"} or not part:
        return part
    if len(part) <= 2 and part.isupper():
        return part

    upper_count = sum(1 for char in part if char.isupper())
    has_lower = any(char.islower() for char in part)
    if part.isupper() or (has_lower and upper_count > 1):
        return part[:1].upper() + part[1:].lower()
    return part


class ResumeBaseModel(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)


class PersonalInfo(ResumeBaseModel):
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""
    website: str = ""
    other_links: list[str] = Field(default_factory=list)

    @field_validator(
        "full_name",
        "email",
        "phone",
        "location",
        "linkedin",
        "github",
        "portfolio",
        "website",
        mode="before",
    )
    @classmethod
    def coerce_string(cls, value: Any) -> str:
        return string_value(value)

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str) -> str:
        return normalize_person_name(value)

    @field_validator("email")
    @classmethod
    def normalize_email_address(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("linkedin", "github", "portfolio", "website")
    @classmethod
    def normalize_profile_url(cls, value: str) -> str:
        return normalize_url(value)

    @field_validator("other_links", mode="before")
    @classmethod
    def coerce_string_list(cls, value: Any) -> list[str]:
        return [normalize_url(item) for item in string_list(value)]


class Experience(ResumeBaseModel):
    id: str = Field(default_factory=new_id)
    company: str = ""
    position: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    is_current: bool = False
    description: str = ""
    bullets: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)

    @field_validator(
        "id",
        "company",
        "position",
        "location",
        "start_date",
        "end_date",
        "description",
        mode="before",
    )
    @classmethod
    def coerce_string(cls, value: Any) -> str:
        return string_value(value)

    @field_validator("id")
    @classmethod
    def ensure_id(cls, value: str) -> str:
        return value or new_id()

    @field_validator("bullets", "technologies", mode="before")
    @classmethod
    def coerce_string_list(cls, value: Any) -> list[str]:
        return string_list(value)


class Education(ResumeBaseModel):
    id: str = Field(default_factory=new_id)
    institution: str = ""
    degree: str = ""
    field: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    details: list[str] = Field(default_factory=list)

    @field_validator(
        "id",
        "institution",
        "degree",
        "field",
        "location",
        "start_date",
        "end_date",
        mode="before",
    )
    @classmethod
    def coerce_string(cls, value: Any) -> str:
        return string_value(value)

    @field_validator("id")
    @classmethod
    def ensure_id(cls, value: str) -> str:
        return value or new_id()

    @field_validator("details", mode="before")
    @classmethod
    def coerce_string_list(cls, value: Any) -> list[str]:
        return string_list(value)


class Language(ResumeBaseModel):
    name: str = ""
    proficiency: str = ""

    @model_validator(mode="before")
    @classmethod
    def accept_plain_string(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"name": value, "proficiency": ""}
        return value

    @field_validator("name", "proficiency", mode="before")
    @classmethod
    def coerce_string(cls, value: Any) -> str:
        return string_value(value)


class Skills(ResumeBaseModel):
    technical: list[str] = Field(default_factory=list)
    soft: list[str] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=list)

    @field_validator("technical", "soft", mode="before")
    @classmethod
    def coerce_string_list(cls, value: Any) -> list[str]:
        return string_list(value)

    @field_validator("languages", mode="before")
    @classmethod
    def coerce_languages(cls, value: Any) -> list[Any]:
        return list_value(value)


class Certification(ResumeBaseModel):
    id: str = Field(default_factory=new_id)
    name: str = ""
    issuer: str = ""
    issue_date: str = ""
    expiry_date: str = ""
    credential_id: str = ""
    url: str = ""

    @field_validator(
        "id",
        "name",
        "issuer",
        "issue_date",
        "expiry_date",
        "credential_id",
        "url",
        mode="before",
    )
    @classmethod
    def coerce_string(cls, value: Any) -> str:
        return string_value(value)

    @field_validator("id")
    @classmethod
    def ensure_id(cls, value: str) -> str:
        return value or new_id()


class Project(ResumeBaseModel):
    id: str = Field(default_factory=new_id)
    name: str = ""
    description: str = ""
    bullets: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    url: str = ""
    start_date: str = ""
    end_date: str = ""

    @field_validator(
        "id",
        "name",
        "description",
        "url",
        "start_date",
        "end_date",
        mode="before",
    )
    @classmethod
    def coerce_string(cls, value: Any) -> str:
        return string_value(value)

    @field_validator("id")
    @classmethod
    def ensure_id(cls, value: str) -> str:
        return value or new_id()

    @field_validator("bullets", "technologies", mode="before")
    @classmethod
    def coerce_string_list(cls, value: Any) -> list[str]:
        return string_list(value)


class ParsedResume(ResumeBaseModel):
    personal_info: PersonalInfo = Field(default_factory=PersonalInfo)
    summary: str = ""
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: Skills = Field(default_factory=Skills)
    certifications: list[Certification] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    confidence: float = 0.0
    warnings: list[str] = Field(default_factory=list)

    @field_validator("summary", mode="before")
    @classmethod
    def coerce_string(cls, value: Any) -> str:
        return string_value(value)

    @field_validator("experience", "education", "certifications", "projects", mode="before")
    @classmethod
    def coerce_object_list(cls, value: Any) -> list[Any]:
        return list_value(value)

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @field_validator("warnings", mode="before")
    @classmethod
    def coerce_warnings(cls, value: Any) -> list[str]:
        return string_list(value)

    @model_validator(mode="after")
    def dedupe_generated_ids(self) -> ParsedResume:
        for items in (self.experience, self.education, self.certifications, self.projects):
            seen: set[str] = set()
            for item in items:
                if item.id in seen:
                    item.id = new_id()
                seen.add(item.id)
        return self

"""Typed contracts for resume upload API, queue, and worker boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


RESUME_UPLOAD_JOB_TYPE = "resume_upload_batch"


@dataclass(frozen=True)
class UploadedResume:
    file_name: str
    content_type: str
    content: bytes


@dataclass(frozen=True)
class ResumeUploadQueuePayload:
    batch_id: str
    organization_id: str
    uploaded_by_clerk_user_id: str
    resend_invites: bool = True
    job_type: str = RESUME_UPLOAD_JOB_TYPE

    def to_message(self) -> dict[str, Any]:
        return {
            "job_type": self.job_type,
            "batch_id": self.batch_id,
            "organization_id": self.organization_id,
            "uploaded_by_clerk_user_id": self.uploaded_by_clerk_user_id,
            "resend_invites": self.resend_invites,
        }


@dataclass(frozen=True)
class ResumeUploadJob:
    batch_id: str
    organization_id: str
    uploaded_by_clerk_user_id: str
    resend_invites: bool = True


class ResumeUploadContractModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ResumeUploadOrganizationResult(ResumeUploadContractModel):
    id: str
    name: str
    slug: str


class ResumeUploadWorkerItemResult(ResumeUploadContractModel):
    resume_parse_item_id: str
    file_name: str
    resume_file_key: str | None = None
    status: str
    extracted_email: str = ""
    extracted_full_name: str = ""
    error_message: str | None = None


class ResumeUploadWorkerResult(ResumeUploadContractModel):
    batch_id: str
    organization: ResumeUploadOrganizationResult
    status: str | None = None
    parsed_count: int = 0
    failed_count: int = 0
    invited_count: int = 0
    invite_failed_count: int = 0
    invite_skipped_count: int = 0
    items: list[ResumeUploadWorkerItemResult] = Field(default_factory=list)

"""Pydantic response contracts for Admin Portal API endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ApiResponseModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class HealthResponse(ApiResponseModel):
    status: str


class ReadyResponse(ApiResponseModel):
    status: str


class OrganizationResponse(ApiResponseModel):
    id: str
    name: str = ""
    slug: str = ""
    logo_url: str | None = None


class AdminMemberResponse(ApiResponseModel):
    clerk_user_id: str | None = None
    email: str
    full_name: str
    member_type: str
    role_key: str
    status: str


class AdminMeResponse(ApiResponseModel):
    organization: OrganizationResponse
    admin: AdminMemberResponse


class ResumeUploadItemResponse(ApiResponseModel):
    resume_parse_item_id: str
    file_name: str
    resume_file_key: str | None = None
    parse_status: str = "pending"
    parse_error_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    extracted_email: str = ""
    extracted_full_name: str = ""
    candidate_profile_id: str | None = None
    invite_status: str = "not_attempted"
    clerk_invitation_id: str | None = None
    invite_error_message: str | None = None


class ResumeUploadBatchResponse(ApiResponseModel):
    batch_id: str
    status: str
    organization: OrganizationResponse | None = None
    uploaded_by_clerk_user_id: str | None = None
    total_files: int = 0
    parsed_count: int = 0
    failed_count: int = 0
    created_at: str | None = None
    completed_at: str | None = None
    items: list[ResumeUploadItemResponse] = Field(default_factory=list)


class ResumeUploadEnqueueResponse(ResumeUploadBatchResponse):
    queue_message_id: str


class LinkedMemberResponse(ApiResponseModel):
    organization_id: str
    email: str
    member_type: str
    role_key: str


class ClerkWebhookResponse(ApiResponseModel):
    status: str
    linked: bool
    reason: str
    candidate_profile_id: str | None = None
    organization_id: str | None = None
    clerk_user_id: str | None = None
    linked_members: list[LinkedMemberResponse] = Field(default_factory=list)

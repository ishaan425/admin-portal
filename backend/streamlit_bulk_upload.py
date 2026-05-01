"""Streamlit UI for local bulk resume upload testing."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests
import streamlit as st


DEFAULT_API_URL = "http://127.0.0.1:8000"
DEMO_ORG_ADMINS = {
    "lpu": "local_lpu_admin",
    "amity": "local_amity_admin",
}


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def upload_resumes(
    api_url: str,
    organization_slug: str,
    local_clerk_user_id: str,
    uploaded_files: list[Any],
) -> requests.Response:
    files = [
        (
            "files",
            (
                uploaded_file.name,
                uploaded_file.getvalue(),
                uploaded_file.type or "application/pdf",
            ),
        )
        for uploaded_file in uploaded_files
    ]
    return requests.post(
        f"{api_url.rstrip('/')}/admin/resumes/bulk-upload",
        headers={
            "X-Local-Clerk-User-Id": local_clerk_user_id,
            "X-Organization-Slug": organization_slug,
        },
        files=files,
        timeout=300,
    )


def render_result(result: dict[str, Any]) -> None:
    st.success("Upload processed")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Files", result.get("total_files", 0))
    col2.metric("Parsed", result.get("parsed_count", 0))
    col3.metric("Invited", result.get("invited_count", 0))
    col4.metric("Failed", result.get("parse_failed_count", 0) + result.get("invite_failed_count", 0))

    st.caption(f"Batch ID: {result.get('batch_id', '')}")
    items = result.get("items") or []
    if items:
        st.dataframe(
            [
                {
                    "file": item.get("file_name"),
                    "email": item.get("extracted_email"),
                    "candidate": item.get("extracted_full_name"),
                    "parse": item.get("parse_status"),
                    "invite": item.get("invite_status"),
                    "error": item.get("parse_error_message") or item.get("invite_error_message"),
                }
                for item in items
            ],
            use_container_width=True,
        )

    with st.expander("Raw response"):
        st.json(result)


def main() -> None:
    load_dotenv()
    st.set_page_config(page_title="GrowQR Bulk Upload", layout="wide")
    st.title("Bulk Resume Upload")

    with st.sidebar:
        api_url = st.text_input(
            "API URL",
            value=os.getenv("ADMIN_API_URL", DEFAULT_API_URL),
        )
        organization_slug = st.selectbox("Organization", options=sorted(DEMO_ORG_ADMINS))
        default_admin = DEMO_ORG_ADMINS[organization_slug]
        local_clerk_user_id = st.text_input("Org admin", value=default_admin)

    uploaded_files = st.file_uploader(
        "PDF resumes",
        type=["pdf"],
        accept_multiple_files=True,
    )

    disabled = not uploaded_files or not local_clerk_user_id.strip() or not organization_slug.strip()
    if st.button("Upload", type="primary", disabled=disabled):
        with st.spinner("Processing resumes and sending invitations..."):
            try:
                response = upload_resumes(
                    api_url=api_url,
                    organization_slug=organization_slug,
                    local_clerk_user_id=local_clerk_user_id,
                    uploaded_files=uploaded_files,
                )
            except requests.RequestException as exc:
                st.error(f"Request failed: {exc}")
                return

        if response.ok:
            render_result(response.json())
        else:
            st.error(f"API returned {response.status_code}")
            try:
                st.json(response.json())
            except ValueError:
                st.code(response.text)


if __name__ == "__main__":
    main()

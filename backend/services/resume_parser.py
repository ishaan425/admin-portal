"""PDF resume extraction using OpenAI vision with a text fallback.

The parser is intentionally framework-free so it can be used by local scripts,
future API handlers, and background workers.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz
from openai import AsyncOpenAI
from pydantic import ValidationError

from schemas.resume_schema import ParsedResume
from services.settings import get_settings


logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5.4"
DEFAULT_DPI = 200
DEFAULT_IMAGE_DETAIL = "high"
DEFAULT_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024


RESUME_PARSE_SYSTEM_PROMPT = """
You are a production resume parsing engine. Return only valid JSON.

Extract all resume information completely. Do not summarize, omit bullets, or
merge separate jobs/projects unless the resume clearly presents them as one item.
Use layout cues: right-aligned dates belong to the nearest entry, bullets belong
to the entry above them, sidebars often contain contact information and skills.

Normalize dates as YYYY-MM when possible. If only a year is present, use YYYY-01.
If a date is present but ambiguous, preserve the original text in the matching
field and add a warning. Reconstruct obvious URLs, for example LinkedIn/username
as https://linkedin.com/in/username. Generate short unique 8-character IDs for
experience, education, certifications, and projects.

Return JSON that matches the provided response schema. Use empty strings, empty
arrays, false, or 0.0 for unknown values. Do not use null. The response must be
a single JSON object and nothing else.
""".strip()


@dataclass(frozen=True)
class ResumeParserConfig:
    api_key: str
    model: str = DEFAULT_MODEL
    dpi: int = DEFAULT_DPI
    image_detail: str = DEFAULT_IMAGE_DETAIL
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES
    page_concurrency: int = 4
    request_retries: int = 2


class ResumeParseError(RuntimeError):
    """Raised when a resume cannot be parsed into structured JSON."""


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def config_from_env() -> ResumeParserConfig:
    settings = get_settings()
    api_key = settings.openai_api_key.strip()
    if not api_key:
        raise ResumeParseError("OPENAI_API_KEY is required. Add it to .env.")

    return ResumeParserConfig(
        api_key=api_key,
        model=settings.openai_resume_parse_model.strip() or DEFAULT_MODEL,
        dpi=settings.resume_parse_dpi,
        image_detail=settings.resume_parse_image_detail.strip() or DEFAULT_IMAGE_DETAIL,
        max_file_size_bytes=settings.resume_parse_max_file_size_bytes,
        page_concurrency=settings.resume_parse_page_concurrency,
        request_retries=settings.resume_parse_request_retries,
    )


def validate_pdf_file(path: Path, max_file_size_bytes: int) -> None:
    if not path.exists():
        raise ResumeParseError(f"File does not exist: {path}")
    if not path.is_file():
        raise ResumeParseError(f"Not a file: {path}")
    if path.suffix.lower() != ".pdf":
        raise ResumeParseError(f"Only PDF files are supported: {path.name}")
    size = path.stat().st_size
    if size <= 0:
        raise ResumeParseError(f"PDF is empty: {path.name}")
    if size > max_file_size_bytes:
        raise ResumeParseError(
            f"PDF exceeds {max_file_size_bytes} bytes: {path.name} ({size} bytes)"
        )


def pdf_to_images(pdf_bytes: bytes, dpi: int = DEFAULT_DPI) -> list[str]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        images: list[str] = []
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            png_bytes = pix.tobytes("png")
            images.append(base64.b64encode(png_bytes).decode("utf-8"))
        return images
    finally:
        doc.close()


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return "\n\n".join(page.get_text("text") for page in doc)
    finally:
        doc.close()


async def parse_resume_file(path: Path, config: ResumeParserConfig | None = None) -> dict[str, Any]:
    config = config or config_from_env()
    validate_pdf_file(path, config.max_file_size_bytes)
    pdf_bytes = path.read_bytes()
    return await parse_resume(pdf_bytes, config=config, source_name=path.name)


async def parse_resume(
    pdf_bytes: bytes,
    config: ResumeParserConfig | None = None,
    source_name: str = "resume.pdf",
) -> dict[str, Any]:
    config = config or config_from_env()
    client = AsyncOpenAI(api_key=config.api_key)

    started_at = time.monotonic()
    try:
        page_images = await asyncio.to_thread(pdf_to_images, pdf_bytes, config.dpi)
        if page_images:
            parsed = await parse_resume_with_vision(page_images, client, config)
            parsed = _ensure_defaults(parsed)
            parsed["_parser"] = {
                "source_name": source_name,
                "path": "vision",
                "model": config.model,
                "page_count": len(page_images),
                "duration_ms": round((time.monotonic() - started_at) * 1000),
            }
            return parsed
    except Exception as exc:
        logger.warning("Vision parsing failed for %s; falling back to text: %s", source_name, exc)

    text = await asyncio.to_thread(extract_text_from_pdf, pdf_bytes)
    if not text.strip():
        raise ResumeParseError(f"Could not extract text from {source_name}.")

    parsed = await parse_resume_with_text(text, client, config)
    parsed = _ensure_defaults(parsed)
    parsed["_parser"] = {
        "source_name": source_name,
        "path": "text_fallback",
        "model": config.model,
        "page_count": 0,
        "duration_ms": round((time.monotonic() - started_at) * 1000),
    }
    return parsed


async def parse_resume_with_vision(
    page_images: list[str],
    client: AsyncOpenAI,
    config: ResumeParserConfig,
) -> dict[str, Any]:
    total = len(page_images)
    semaphore = asyncio.Semaphore(max(1, config.page_concurrency))

    async def run_page(img_b64: str, page_num: int) -> dict[str, Any]:
        async with semaphore:
            return await _parse_single_page(client, img_b64, page_num, total, config)

    if total == 1:
        return await run_page(page_images[0], 1)

    results = await asyncio.gather(
        *(run_page(img, index + 1) for index, img in enumerate(page_images))
    )
    non_empty_results = [result for result in results if not _is_effectively_empty(result)]
    return _merge_parsed_pages(non_empty_results or results)


async def parse_resume_with_text(
    text: str,
    client: AsyncOpenAI,
    config: ResumeParserConfig,
) -> dict[str, Any]:
    content = (
        "Parse this resume text into the required JSON schema. Preserve all details, "
        "bullets, dates, links, education, projects, certifications, and skills.\n\n"
        f"{text[:45000]}"
    )
    response = await _create_completion_with_retries(
        client,
        config,
        messages=[
            {"role": "system", "content": RESUME_PARSE_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        max_completion_tokens=8000,
    )
    return _json_from_response(response)


async def _parse_single_page(
    client: AsyncOpenAI,
    img_b64: str,
    page_num: int,
    total_pages: int,
    config: ResumeParserConfig,
) -> dict[str, Any]:
    context = (
        f"Parse page {page_num} of {total_pages} of this resume. "
        "Extract all information from this page completely. Return JSON only."
    )
    response = await _create_completion_with_retries(
        client,
        config,
        messages=[
            {"role": "system", "content": RESUME_PARSE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": context},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{img_b64}",
                            "detail": config.image_detail,
                        },
                    },
                ],
            },
        ],
        max_completion_tokens=8000,
    )
    return _json_from_response(response)


async def _create_completion_with_retries(
    client: AsyncOpenAI,
    config: ResumeParserConfig,
    messages: list[dict[str, Any]],
    max_completion_tokens: int,
) -> Any:
    last_exc: Exception | None = None
    for attempt in range(config.request_retries + 1):
        try:
            return await client.chat.completions.create(
                model=config.model,
                messages=messages,
                temperature=0.1,
                max_completion_tokens=max_completion_tokens,
                response_format=_resume_response_format(),
            )
        except Exception as exc:
            last_exc = exc
            if attempt >= config.request_retries:
                break
            await asyncio.sleep(1.5 * (attempt + 1))
    raise ResumeParseError(f"OpenAI request failed: {last_exc}") from last_exc


def _json_from_response(response: Any) -> dict[str, Any]:
    content = response.choices[0].message.content
    if not content:
        raise ResumeParseError("OpenAI returned an empty response.")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ResumeParseError(f"OpenAI returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ResumeParseError("OpenAI response JSON must be an object.")
    return _ensure_defaults(parsed)


def _resume_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "parsed_resume",
            "strict": False,
            "schema": ParsedResume.model_json_schema(),
        },
    }


def _merge_parsed_pages(pages: list[dict[str, Any]]) -> dict[str, Any]:
    if not pages:
        return _ensure_defaults({})

    merged = _ensure_defaults(pages[0])
    for page in pages[1:]:
        page = _ensure_defaults(page)
        _fill_missing_personal_info(merged["personal_info"], page["personal_info"])
        if not merged["summary"] and page["summary"]:
            merged["summary"] = page["summary"]

        _append_unique_objects(merged["experience"], page["experience"], ("company", "position"))
        _append_unique_objects(merged["education"], page["education"], ("institution", "degree"))
        _append_unique_objects(merged["certifications"], page["certifications"], ("name", "issuer"))
        _append_unique_objects(merged["projects"], page["projects"], ("name",))

        _append_unique_strings(merged["skills"]["technical"], page["skills"]["technical"])
        _append_unique_strings(merged["skills"]["soft"], page["skills"]["soft"])
        _append_unique_objects(merged["skills"]["languages"], page["skills"]["languages"], ("name",))

        merged["confidence"] = min(float(merged.get("confidence") or 0), float(page["confidence"] or 0))
        merged["warnings"].extend(page["warnings"])

    return _ensure_defaults(merged)


def _ensure_defaults(data: dict[str, Any]) -> dict[str, Any]:
    raw_data = dict(data or {})
    parser_metadata = {key: value for key, value in raw_data.items() if key.startswith("_")}

    try:
        normalized = ParsedResume.model_validate(raw_data).model_dump(mode="json")
    except ValidationError as exc:
        raise ResumeParseError(f"Resume JSON failed Pydantic validation: {exc}") from exc

    for key, value in parser_metadata.items():
        if key.startswith("_"):
            normalized[key] = value

    return normalized


def _fill_missing_personal_info(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if key == "other_links":
            _append_unique_strings(target.setdefault(key, []), _as_str_list(value))
        elif not target.get(key) and value:
            target[key] = value


def _append_unique_objects(
    target: list[dict[str, Any]],
    source: list[dict[str, Any]],
    keys: tuple[str, ...],
) -> None:
    seen = {_object_key(item, keys) for item in target}
    for item in source:
        key = _object_key(item, keys)
        if key and key not in seen:
            target.append(item)
            seen.add(key)


def _append_unique_strings(target: list[str], source: list[str]) -> None:
    seen = set(target)
    for item in source:
        if item and item not in seen:
            target.append(item)
            seen.add(item)


def _object_key(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    return "|".join(_as_str(item.get(key)).strip().lower() for key in keys).strip("|")


def _is_effectively_empty(data: dict[str, Any]) -> bool:
    data = _ensure_defaults(data)
    return not any(
        [
            data["personal_info"]["full_name"],
            data["personal_info"]["email"],
            data["experience"],
            data["education"],
            data["skills"]["technical"],
            data["certifications"],
            data["projects"],
        ]
    )


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str_list(value: Any) -> list[str]:
    return [_as_str(item) for item in _as_list(value) if _as_str(item)]

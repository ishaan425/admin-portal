"""Parse one or many PDF resumes into JSON.

Usage:
    python3 parse_bulk_resumes.py --input ./resumes --output ./parsed_resumes/results.json
    python3 parse_bulk_resumes.py --input ./one_resume.pdf --output ./parsed_resumes/results.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.resume_parser import ResumeParseError, config_from_env, parse_resume_file


logger = logging.getLogger(__name__)


def discover_pdfs(input_path: Path, recursive: bool) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    if not input_path.exists():
        raise ResumeParseError(f"Input path does not exist: {input_path}")
    if not input_path.is_dir():
        raise ResumeParseError(f"Input path must be a PDF file or directory: {input_path}")

    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(path for path in input_path.glob(pattern) if path.is_file())


async def parse_many(
    files: list[Path],
    concurrency: int,
    per_file_output_dir: Path | None,
) -> dict[str, Any]:
    config = config_from_env()
    semaphore = asyncio.Semaphore(max(1, concurrency))
    started_at = time.monotonic()

    if per_file_output_dir:
        per_file_output_dir.mkdir(parents=True, exist_ok=True)

    async def parse_one(path: Path) -> dict[str, Any]:
        async with semaphore:
            item_started_at = time.monotonic()
            logger.info("Parsing %s", path)
            try:
                parsed = await parse_resume_file(path, config=config)
                result = {
                    "file_name": path.name,
                    "file_path": str(path),
                    "status": "parsed",
                    "duration_ms": round((time.monotonic() - item_started_at) * 1000),
                    "parsed_resume": parsed,
                }
                if per_file_output_dir:
                    output_path = per_file_output_dir / f"{path.stem}.json"
                    output_path.write_text(
                        json.dumps(result, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    result["output_path"] = str(output_path)
                return result
            except Exception as exc:
                logger.exception("Failed to parse %s", path)
                return {
                    "file_name": path.name,
                    "file_path": str(path),
                    "status": "failed",
                    "duration_ms": round((time.monotonic() - item_started_at) * 1000),
                    "error": str(exc),
                }

    results = await asyncio.gather(*(parse_one(path) for path in files))
    parsed_count = sum(1 for item in results if item["status"] == "parsed")

    return {
        "run": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "input_count": len(files),
            "parsed_count": parsed_count,
            "failed_count": len(files) - parsed_count,
            "duration_ms": round((time.monotonic() - started_at) * 1000),
        },
        "resumes": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse PDF resumes into structured JSON.")
    parser.add_argument(
        "--input",
        required=True,
        help="Path to a PDF file or a directory containing PDF resumes.",
    )
    parser.add_argument(
        "--output",
        default="parsed_resumes/results.json",
        help="Combined JSON output path. Default: parsed_resumes/results.json",
    )
    parser.add_argument(
        "--per-file-output-dir",
        default="",
        help="Optional directory for one JSON file per resume.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=2,
        help="How many resumes to parse at once. Default: 2",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search input directory recursively for PDFs.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    return parser.parse_args()


async def main_async() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    input_path = Path(args.input).expanduser()
    output_path = Path(args.output).expanduser()
    per_file_output_dir = (
        Path(args.per_file_output_dir).expanduser() if args.per_file_output_dir else None
    )

    files = discover_pdfs(input_path, recursive=args.recursive)
    if not files:
        raise ResumeParseError(f"No PDF files found under {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = await parse_many(
        files=files,
        concurrency=args.concurrency,
        per_file_output_dir=per_file_output_dir,
    )
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info(
        "Wrote %s (%s parsed, %s failed)",
        output_path,
        result["run"]["parsed_count"],
        result["run"]["failed_count"],
    )
    return 0 if result["run"]["failed_count"] == 0 else 1


def main() -> int:
    try:
        return asyncio.run(main_async())
    except ResumeParseError as exc:
        logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(message)s")
        logger.error("%s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Apply local SQL files using the project database connection."""

from __future__ import annotations

import argparse
from pathlib import Path

from services.database import connect


def apply_sql_file(path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    with connect() as conn:
        with conn.transaction():
            for statement in sql.split(";"):
                cleaned = statement.strip()
                if cleaned and cleaned.lower() not in {"begin", "commit"}:
                    conn.execute(cleaned)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sql_files", nargs="+", type=Path)
    args = parser.parse_args()

    for sql_file in args.sql_files:
        apply_sql_file(sql_file)


if __name__ == "__main__":
    main()

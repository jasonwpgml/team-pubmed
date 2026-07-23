"""SQLite persistence and querying for PubMed records."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DB_PATH = Path(os.getenv("PUBMED_DB_PATH", Path(__file__).resolve().parents[1] / "pubmed.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pubmed_records (
    pmid TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    abstract TEXT NOT NULL DEFAULT '',
    journal TEXT NOT NULL DEFAULT '',
    pub_year INTEGER,
    authors TEXT NOT NULL DEFAULT ''
)
"""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_db() -> None:
    """Create the PubMed table and search indexes if they do not exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as connection:
        connection.execute(_SCHEMA)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_pubmed_records_year ON pubmed_records(pub_year)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_pubmed_records_journal ON pubmed_records(journal)"
        )


def upsert_papers(papers: list[dict]) -> tuple[int, int]:
    """Insert unseen PMIDs and return ``(new_count, skipped_count)``."""
    init_db()
    inserted = 0
    with _connect() as connection:
        for paper in papers:
            normalized = _normalize_paper(paper)
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO pubmed_records
                    (pmid, title, abstract, journal, pub_year, authors)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized["pmid"],
                    normalized["title"],
                    normalized["abstract"],
                    normalized["journal"],
                    normalized["pub_year"],
                    normalized["authors"],
                ),
            )
            inserted += cursor.rowcount
    return inserted, len(papers) - inserted


def search_papers(
    keyword: str = "",
    year_from: int | None = None,
    year_to: int | None = None,
    journal: str = "",
    limit: int = 100,
) -> list[dict]:
    """Return papers matching title/abstract, year, and journal filters."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    if year_from is not None and year_to is not None and year_from > year_to:
        raise ValueError("year_from must be less than or equal to year_to")

    init_db()
    conditions: list[str] = []
    params: list[Any] = []
    keyword = keyword.strip()
    journal = journal.strip()

    if keyword:
        conditions.append("(title LIKE ? COLLATE NOCASE OR abstract LIKE ? COLLATE NOCASE)")
        pattern = f"%{keyword}%"
        params.extend((pattern, pattern))
    if year_from is not None:
        conditions.append("pub_year >= ?")
        params.append(year_from)
    if year_to is not None:
        conditions.append("pub_year <= ?")
        params.append(year_to)
    if journal:
        conditions.append("journal = ? COLLATE NOCASE")
        params.append(journal)

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    query = (
        "SELECT pmid, title, abstract, journal, pub_year, authors "
        f"FROM pubmed_records{where} "
        "ORDER BY pub_year DESC, CAST(pmid AS INTEGER) DESC LIMIT ?"
    )
    with _connect() as connection:
        return [dict(row) for row in connection.execute(query, params).fetchall()]


def count_papers() -> int:
    init_db()
    with _connect() as connection:
        return int(connection.execute("SELECT COUNT(*) FROM pubmed_records").fetchone()[0])


def count_journals() -> int:
    init_db()
    with _connect() as connection:
        return int(
            connection.execute(
                "SELECT COUNT(DISTINCT journal) FROM pubmed_records WHERE journal <> ''"
            ).fetchone()[0]
        )


def _normalize_paper(paper: dict) -> dict[str, Any]:
    pmid = str(paper.get("pmid") or "").strip()
    if not pmid:
        raise ValueError("each paper must have a non-empty pmid")

    pub_year = paper.get("pub_year")
    if pub_year in (None, ""):
        pub_year = None
    elif isinstance(pub_year, bool):
        raise ValueError("pub_year must be an integer or None")
    else:
        try:
            pub_year = int(pub_year)
        except (TypeError, ValueError) as error:
            raise ValueError("pub_year must be an integer or None") from error

    return {
        "pmid": pmid,
        "title": str(paper.get("title") or "").strip(),
        "abstract": str(paper.get("abstract") or "").strip(),
        "journal": str(paper.get("journal") or "").strip(),
        "pub_year": pub_year,
        "authors": str(paper.get("authors") or "").strip(),
    }

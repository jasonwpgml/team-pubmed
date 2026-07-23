"""SQLite/PostgreSQL persistence and querying for PubMed records."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from core.database import adapt_query, connect, uses_postgres

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DB_PATH = Path(os.getenv("PUBMED_DB_PATH", Path(__file__).resolve().parents[1] / "pubmed.db"))

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    pmid TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    abstract TEXT NOT NULL DEFAULT '',
    journal TEXT NOT NULL DEFAULT '',
    pub_year INTEGER,
    authors TEXT NOT NULL DEFAULT '',
    collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

_POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    pmid TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    abstract TEXT NOT NULL DEFAULT '',
    journal TEXT NOT NULL DEFAULT '',
    pub_year INTEGER,
    authors TEXT NOT NULL DEFAULT '',
    collected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

_SQLITE_TREND_SCHEMA = """
CREATE TABLE IF NOT EXISTS collection_trend (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    keyword TEXT NOT NULL,
    year_from INTEGER NOT NULL,
    year_to INTEGER NOT NULL,
    papers_by_year TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

_POSTGRES_TREND_SCHEMA = """
CREATE TABLE IF NOT EXISTS collection_trend (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    keyword TEXT NOT NULL,
    year_from INTEGER NOT NULL,
    year_to INTEGER NOT NULL,
    papers_by_year TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

_SQLITE_COLLECTION_KEYWORD_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_collection_keywords (
    pmid TEXT NOT NULL,
    keyword TEXT NOT NULL COLLATE NOCASE,
    PRIMARY KEY (pmid, keyword),
    FOREIGN KEY (pmid) REFERENCES papers(pmid) ON DELETE CASCADE
)
"""

_POSTGRES_COLLECTION_KEYWORD_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_collection_keywords (
    pmid TEXT NOT NULL,
    keyword TEXT NOT NULL,
    PRIMARY KEY (pmid, keyword),
    FOREIGN KEY (pmid) REFERENCES papers(pmid) ON DELETE CASCADE
)
"""


def _connect():
    return connect(DATABASE_URL, DB_PATH)


def _query(query: str) -> str:
    return adapt_query(query, DATABASE_URL)


def init_db() -> None:
    """Create the PubMed table and search indexes if they do not exist."""
    with _connect() as connection:
        connection.execute(
            _POSTGRES_SCHEMA if uses_postgres(DATABASE_URL) else _SQLITE_SCHEMA
        )
        connection.execute(
            _POSTGRES_TREND_SCHEMA
            if uses_postgres(DATABASE_URL)
            else _SQLITE_TREND_SCHEMA
        )
        connection.execute(
            _POSTGRES_COLLECTION_KEYWORD_SCHEMA
            if uses_postgres(DATABASE_URL)
            else _SQLITE_COLLECTION_KEYWORD_SCHEMA
        )
        if not uses_postgres(DATABASE_URL):
            _migrate_legacy_records(connection)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(pub_year)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_papers_journal ON papers(journal)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_collection_keywords_keyword "
            "ON paper_collection_keywords(keyword)"
        )


def upsert_papers(
    papers: list[dict], collection_keyword: str = ""
) -> tuple[int, int]:
    """Insert unseen PMIDs, associate their collection keyword, and return counts."""
    init_db()
    inserted = 0
    collection_keyword = collection_keyword.strip()
    with _connect() as connection:
        for paper in papers:
            normalized = _normalize_paper(paper)
            cursor = connection.execute(
                _query(
                    """
                INSERT INTO papers
                    (pmid, title, abstract, journal, pub_year, authors)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (pmid) DO NOTHING
                """,
                ),
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
            if collection_keyword:
                # AIDEV-NOTE: Keep every PMID-to-query association; one paper may be collected by multiple searches.
                connection.execute(
                    _query(
                        """
                    INSERT INTO paper_collection_keywords (pmid, keyword)
                    VALUES (?, ?)
                    ON CONFLICT (pmid, keyword) DO NOTHING
                    """,
                    ),
                    (normalized["pmid"], collection_keyword),
                )
    return inserted, len(papers) - inserted


def search_papers(
    keyword: str = "",
    year_from: int | None = None,
    year_to: int | None = None,
    journal: str = "",
    limit: int = 100,
) -> list[dict]:
    """Return papers matching title, abstract, collection keyword, year, and journal."""
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
        insensitive_like = "ILIKE" if uses_postgres(DATABASE_URL) else "LIKE"
        no_case = "" if uses_postgres(DATABASE_URL) else " COLLATE NOCASE"
        conditions.append(
            "("
            f"title {insensitive_like} ?{no_case} OR "
            f"abstract {insensitive_like} ?{no_case} OR "
            "EXISTS ("
            "SELECT 1 FROM paper_collection_keywords AS collected "
            "WHERE collected.pmid = papers.pmid "
            f"AND collected.keyword {insensitive_like} ?{no_case}"
            ")"
            ")"
        )
        pattern = f"%{keyword}%"
        params.extend((pattern, pattern, pattern))
    if year_from is not None:
        conditions.append("pub_year >= ?")
        params.append(year_from)
    if year_to is not None:
        conditions.append("pub_year <= ?")
        params.append(year_to)
    if journal:
        if uses_postgres(DATABASE_URL):
            conditions.append("journal ILIKE ?")
        else:
            conditions.append("journal = ? COLLATE NOCASE")
        params.append(journal)

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    query = (
        "SELECT pmid, title, abstract, journal, pub_year, authors "
        f"FROM papers{where} "
        "ORDER BY pub_year DESC, CAST(pmid AS BIGINT) DESC LIMIT ?"
    )
    with _connect() as connection:
        return [
            dict(row)
            for row in connection.execute(_query(query), params).fetchall()
        ]


def count_papers() -> int:
    init_db()
    with _connect() as connection:
        row = connection.execute("SELECT COUNT(*) AS count FROM papers").fetchone()
        return int(row["count"])


def count_journals() -> int:
    init_db()
    with _connect() as connection:
        return int(
            connection.execute(
                "SELECT COUNT(DISTINCT journal) AS count "
                "FROM papers WHERE journal <> ''"
            ).fetchone()["count"]
        )


def clear_papers() -> int:
    """Delete every collected paper and return the number of removed records."""
    init_db()
    with _connect() as connection:
        connection.execute("DELETE FROM paper_collection_keywords")
        removed = connection.execute("DELETE FROM papers").rowcount
        connection.execute("DELETE FROM collection_trend")
        if not uses_postgres(DATABASE_URL):
            legacy_table = connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = 'pubmed_records'"
            ).fetchone()
            if legacy_table is not None:
                connection.execute("DELETE FROM pubmed_records")
    return int(removed)


def save_collection_trend(
    keyword: str, year_from: int, year_to: int, papers_by_year: dict[int, int]
) -> None:
    """Persist the latest PubMed annual-search trend for page refreshes."""
    init_db()
    with _connect() as connection:
        connection.execute(
            _query(
                """
            INSERT INTO collection_trend (id, keyword, year_from, year_to, papers_by_year)
            VALUES (1, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                keyword = excluded.keyword,
                year_from = excluded.year_from,
                year_to = excluded.year_to,
                papers_by_year = excluded.papers_by_year,
                updated_at = CURRENT_TIMESTAMP
            """,
            ),
            (keyword, year_from, year_to, json.dumps(papers_by_year)),
        )


def get_collection_trend() -> dict | None:
    """Return the latest persisted annual PubMed search trend, if available."""
    init_db()
    with _connect() as connection:
        row = connection.execute(
            "SELECT keyword, year_from, year_to, papers_by_year FROM collection_trend WHERE id = 1"
        ).fetchone()
    if row is None:
        return None
    return {
        "keyword": row["keyword"],
        "year_from": row["year_from"],
        "year_to": row["year_to"],
        "papers_by_year": json.loads(row["papers_by_year"]),
    }


def _migrate_legacy_records(connection: sqlite3.Connection) -> None:
    legacy_table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'pubmed_records'"
    ).fetchone()
    if legacy_table is None:
        return

    # AIDEV-NOTE: Keep the legacy table intact so upgrading the shared project never discards collected papers.
    connection.execute(
        """
        INSERT OR IGNORE INTO papers (pmid, title, abstract, journal, pub_year, authors)
        SELECT pmid, title, abstract, journal, pub_year, authors
        FROM pubmed_records
        """
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

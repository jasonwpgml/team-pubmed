import tempfile
import unittest
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from core import db


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(db, "DB_PATH", Path(self.temp_dir.name) / "test.db")
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_upsert_skips_duplicate_pmids_and_counts_distinct_journals(self):
        papers = [
            self.paper("1", "COVID vaccine", "Journal A", 2023),
            self.paper("2", "Cancer study", "Journal B", 2024),
        ]
        self.assertEqual(db.upsert_papers(papers), (2, 0))
        self.assertEqual(db.upsert_papers(papers), (0, 2))
        self.assertEqual(db.count_papers(), 2)
        self.assertEqual(db.count_journals(), 2)

    def test_search_combines_all_filters(self):
        db.upsert_papers(
            [
                self.paper("1", "COVID vaccine", "Journal A", 2023),
                self.paper("2", "COVID outcomes", "Journal B", 2024),
                self.paper("3", "Cancer study", "Journal A", 2024),
            ]
        )
        result = db.search_papers(
            keyword="covid", year_from=2023, year_to=2023, journal="journal a"
        )
        self.assertEqual([paper["pmid"] for paper in result], ["1"])

    def test_search_includes_blank_abstract_paper_collected_by_keyword(self):
        paper = self.paper("1", "A title without the query term", "Journal A", 2023)
        paper["abstract"] = ""
        db.upsert_papers([paper], collection_keyword="diabetes")

        self.assertEqual(
            [result["pmid"] for result in db.search_papers(keyword="diabetes")],
            ["1"],
        )
        self.assertEqual(db.search_papers(keyword="unrelated"), [])

    def test_duplicate_paper_keeps_every_collection_keyword(self):
        paper = self.paper("1", "Shared paper", "Journal A", 2023)
        db.upsert_papers([paper], collection_keyword="diabetes")
        self.assertEqual(
            db.upsert_papers([paper], collection_keyword="neuropathy"),
            (0, 1),
        )

        self.assertEqual(len(db.search_papers(keyword="diabetes")), 1)
        self.assertEqual(len(db.search_papers(keyword="neuropathy")), 1)

    def test_clear_papers_removes_all_collected_records(self):
        db.upsert_papers(
            [
                self.paper("1", "COVID vaccine", "Journal A", 2023),
                self.paper("2", "Cancer study", "Journal B", 2024),
            ]
        )

        self.assertEqual(db.clear_papers(), 2)
        self.assertEqual(db.count_papers(), 0)
        self.assertEqual(db.clear_papers(), 0)

    def test_clear_papers_prevents_legacy_records_from_being_migrated_back(self):
        with closing(sqlite3.connect(db.DB_PATH)) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE pubmed_records (
                        pmid TEXT PRIMARY KEY, title TEXT, abstract TEXT,
                        journal TEXT, pub_year INTEGER, authors TEXT
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO pubmed_records VALUES (?, ?, ?, ?, ?, ?)",
                    ("9", "Legacy paper", "Abstract", "Legacy Journal", 2022, "Jane Doe"),
                )

        self.assertEqual(db.count_papers(), 1)
        self.assertEqual(db.clear_papers(), 1)
        self.assertEqual(db.count_papers(), 0)

    def test_collection_trend_persists_and_is_cleared_with_papers(self):
        db.upsert_papers([self.paper("1", "COVID vaccine", "Journal A", 2023)])
        db.save_collection_trend("covid", 2022, 2023, {2022: 11, 2023: 17})

        self.assertEqual(
            db.get_collection_trend(),
            {
                "keyword": "covid",
                "year_from": 2022,
                "year_to": 2023,
                "papers_by_year": {"2022": 11, "2023": 17},
            },
        )

        db.clear_papers()
        self.assertIsNone(db.get_collection_trend())

    def test_init_db_uses_documented_schema(self):
        db.init_db()
        with closing(sqlite3.connect(db.DB_PATH)) as connection:
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(papers)").fetchall()
            }
        self.assertEqual(
            columns,
            {"pmid", "title", "abstract", "journal", "pub_year", "authors", "collected_at"},
        )

    def test_init_db_migrates_legacy_records(self):
        with closing(sqlite3.connect(db.DB_PATH)) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE pubmed_records (
                        pmid TEXT PRIMARY KEY, title TEXT, abstract TEXT,
                        journal TEXT, pub_year INTEGER, authors TEXT
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO pubmed_records VALUES (?, ?, ?, ?, ?, ?)",
                    ("9", "Legacy paper", "Abstract", "Legacy Journal", 2022, "Jane Doe"),
                )

        db.init_db()

        self.assertEqual(db.count_papers(), 1)
        self.assertEqual(db.search_papers()[0]["pmid"], "9")

    @staticmethod
    def paper(pmid, title, journal, pub_year):
        return {
            "pmid": pmid,
            "title": title,
            "abstract": f"Abstract for {title}",
            "journal": journal,
            "pub_year": pub_year,
            "authors": "Jane Doe",
        }


if __name__ == "__main__":
    unittest.main()

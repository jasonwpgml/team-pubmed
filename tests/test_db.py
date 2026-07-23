import tempfile
import unittest
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


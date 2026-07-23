import unittest

from core.analysis import papers_by_year, top_journals


class AnalysisTests(unittest.TestCase):
    def test_papers_by_year_ignores_missing_and_orders_years(self):
        papers = [
            {"pub_year": 2024},
            {"pub_year": "2023"},
            {"pub_year": 2024},
            {"pub_year": None},
        ]
        self.assertEqual(papers_by_year(papers), {2023: 1, 2024: 2})

    def test_top_journals_counts_non_empty_names_and_limits_results(self):
        papers = [
            {"journal": "Beta"},
            {"journal": "Alpha"},
            {"journal": "Beta"},
            {"journal": ""},
        ]
        self.assertEqual(top_journals(papers, 2), [("Beta", 2), ("Alpha", 1)])


if __name__ == "__main__":
    unittest.main()


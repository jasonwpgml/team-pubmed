import unittest
from unittest.mock import Mock, patch

from core.pubmed import EFETCH_URL, ESEARCH_URL, collect, count_by_year


SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>12345</PMID>
      <Article>
        <ArticleTitle>Vaccine <i>effectiveness</i> study</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Background text.</AbstractText>
          <AbstractText>Conclusion text.</AbstractText>
        </Abstract>
        <Journal>
          <JournalIssue><PubDate><Year>2026</Year></PubDate></JournalIssue>
          <Title>Example Journal</Title>
        </Journal>
        <ArticleDate DateType="Electronic">
          <Year>2025</Year><Month>12</Month><Day>27</Day>
        </ArticleDate>
        <AuthorList>
          <Author><LastName>Doe</LastName><ForeName>Jane</ForeName></Author>
          <Author><CollectiveName>Study Group</CollectiveName></Author>
        </AuthorList>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""


class PubMedTests(unittest.TestCase):
    @patch("core.pubmed.requests.get")
    def test_collect_searches_then_fetches_and_parses_required_fields(self, mock_get):
        search_response = Mock()
        search_response.json.return_value = {"esearchresult": {"idlist": ["12345"]}}
        fetch_response = Mock(content=SAMPLE_XML)
        mock_get.side_effect = [search_response, fetch_response]

        papers = collect("COVID-19 vaccine", 2022, 2025, 100)

        self.assertEqual(
            papers,
            [
                {
                    "pmid": "12345",
                    "title": "Vaccine effectiveness study",
                    "abstract": "BACKGROUND: Background text.\nConclusion text.",
                    "journal": "Example Journal",
                    "pub_year": 2025,
                    "authors": "Jane Doe, Study Group",
                }
            ],
        )
        self.assertEqual(mock_get.call_args_list[0].args[0], ESEARCH_URL)
        self.assertEqual(mock_get.call_args_list[1].args[0], EFETCH_URL)
        self.assertEqual(mock_get.call_args_list[0].kwargs["params"]["retmax"], 100)

    @patch("core.pubmed.requests.get")
    def test_collect_does_not_fetch_when_search_is_empty(self, mock_get):
        response = Mock()
        response.json.return_value = {"esearchresult": {"idlist": []}}
        mock_get.return_value = response
        self.assertEqual(collect("rare query", 2020, 2021, 10), [])
        mock_get.assert_called_once()

    def test_collect_validates_input_before_network_request(self):
        with self.assertRaises(ValueError):
            collect("", 2020, 2021, 10)
        with self.assertRaises(ValueError):
            collect("cancer", 2022, 2021, 10)
        with self.assertRaises(ValueError):
            collect("cancer", 2020, 2021, 101)

    @patch.dict("core.pubmed.os.environ", {"NCBI_API_KEY": "test-key"})
    @patch("core.pubmed.requests.get")
    def test_count_by_year_returns_complete_esearch_counts(self, mock_get):
        responses = []
        for count in (1200, 1350, 1425):
            response = Mock()
            response.json.return_value = {"esearchresult": {"count": str(count)}}
            responses.append(response)
        mock_get.side_effect = responses

        result = count_by_year("cancer", 2023, 2025)

        self.assertEqual(result, {2023: 1200, 2024: 1350, 2025: 1425})
        self.assertEqual(mock_get.call_count, 3)
        for year, call in zip(range(2023, 2026), mock_get.call_args_list):
            self.assertEqual(call.args[0], ESEARCH_URL)
            self.assertEqual(call.kwargs["params"]["retmax"], 0)
            self.assertEqual(call.kwargs["params"]["api_key"], "test-key")
            self.assertIn(f"{year}:{year}[pdat]", call.kwargs["params"]["term"])

    @patch("core.pubmed.requests.get")
    def test_count_by_year_validates_input_before_network_request(self, mock_get):
        with self.assertRaises(ValueError):
            count_by_year("", 2020, 2025)
        with self.assertRaises(ValueError):
            count_by_year("cancer", 2025, 2020)
        mock_get.assert_not_called()


if __name__ == "__main__":
    unittest.main()

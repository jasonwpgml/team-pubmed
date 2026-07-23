import unittest
from unittest.mock import Mock, patch

from core.pubmed import EFETCH_URL, ESEARCH_URL, collect


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
          <JournalIssue><PubDate><MedlineDate>2024 Jan-Feb</MedlineDate></PubDate></JournalIssue>
          <Title>Example Journal</Title>
        </Journal>
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
                    "pub_year": 2024,
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


if __name__ == "__main__":
    unittest.main()


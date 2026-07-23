"""PubMed ESearch/EFetch client."""

from __future__ import annotations

import os
import re
from typing import Any
from xml.etree import ElementTree

import requests

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
MAX_PAPERS = 100
REQUEST_TIMEOUT = 30


def collect(keyword: str, year_from: int, year_to: int, max_count: int) -> list[dict]:
    """Collect PubMed article metadata matching the supplied search conditions."""
    keyword = keyword.strip()
    _validate_search(keyword, year_from, year_to, max_count)

    common_params = _ncbi_identity_params()
    search_response = requests.get(
        ESEARCH_URL,
        params={
            "db": "pubmed",
            "term": f"{keyword} AND {year_from}:{year_to}[pdat]",
            "retmax": max_count,
            "retmode": "json",
            "sort": "pub date",
            **common_params,
        },
        timeout=REQUEST_TIMEOUT,
    )
    search_response.raise_for_status()
    pmids = search_response.json().get("esearchresult", {}).get("idlist", [])
    if not pmids:
        return []

    fetch_response = requests.get(
        EFETCH_URL,
        params={
            "db": "pubmed",
            "id": ",".join(str(pmid) for pmid in pmids),
            "retmode": "xml",
            **common_params,
        },
        timeout=REQUEST_TIMEOUT,
    )
    fetch_response.raise_for_status()
    return _parse_articles(fetch_response.content)


def _validate_search(keyword: str, year_from: int, year_to: int, max_count: int) -> None:
    if not keyword:
        raise ValueError("keyword must not be empty")
    if isinstance(year_from, bool) or not isinstance(year_from, int):
        raise ValueError("year_from must be an integer")
    if isinstance(year_to, bool) or not isinstance(year_to, int):
        raise ValueError("year_to must be an integer")
    if year_from > year_to:
        raise ValueError("year_from must be less than or equal to year_to")
    if isinstance(max_count, bool) or not isinstance(max_count, int):
        raise ValueError("max_count must be an integer")
    if not 1 <= max_count <= MAX_PAPERS:
        raise ValueError(f"max_count must be between 1 and {MAX_PAPERS}")


def _ncbi_identity_params() -> dict[str, str]:
    params = {"tool": "team-pubmed"}
    optional_values = {
        "api_key": os.getenv("NCBI_API_KEY", "").strip(),
        "email": os.getenv("NCBI_EMAIL", "").strip(),
    }
    params.update({key: value for key, value in optional_values.items() if value})
    return params


def _parse_articles(xml_content: bytes) -> list[dict]:
    root = ElementTree.fromstring(xml_content)
    papers: list[dict[str, Any]] = []

    for record in root.findall(".//PubmedArticle"):
        citation = record.find("MedlineCitation")
        article = citation.find("Article") if citation is not None else None
        if citation is None or article is None:
            continue

        pmid = _text(citation.find("PMID"))
        if not pmid:
            continue

        abstract_parts: list[str] = []
        for abstract in article.findall("./Abstract/AbstractText"):
            value = _text(abstract)
            if not value:
                continue
            label = (abstract.get("Label") or "").strip()
            abstract_parts.append(f"{label}: {value}" if label else value)

        papers.append(
            {
                "pmid": pmid,
                "title": _text(article.find("ArticleTitle")),
                "abstract": "\n".join(abstract_parts),
                "journal": _text(article.find("./Journal/Title")),
                "pub_year": _publication_year(article),
                "authors": _authors(article),
            }
        )

    return papers


def _text(element: ElementTree.Element | None) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def _publication_year(article: ElementTree.Element) -> int | None:
    pub_date = article.find("./Journal/JournalIssue/PubDate")
    if pub_date is not None:
        year = _text(pub_date.find("Year"))
        if year.isdigit():
            return int(year)

        medline_date = _text(pub_date.find("MedlineDate"))
        match = re.search(r"\b(?:18|19|20)\d{2}\b", medline_date)
        if match:
            return int(match.group())

    article_date_year = _text(article.find("./ArticleDate/Year"))
    return int(article_date_year) if article_date_year.isdigit() else None


def _authors(article: ElementTree.Element) -> str:
    names: list[str] = []
    for author in article.findall("./AuthorList/Author"):
        collective_name = _text(author.find("CollectiveName"))
        if collective_name:
            names.append(collective_name)
            continue

        last_name = _text(author.find("LastName"))
        fore_name = _text(author.find("ForeName"))
        name = " ".join(part for part in (fore_name, last_name) if part)
        if name:
            names.append(name)
    return ", ".join(names)


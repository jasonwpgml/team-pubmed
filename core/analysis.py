"""Deterministic aggregations for PubMed dashboard charts."""

from __future__ import annotations

from collections import Counter


def papers_by_year(papers: list[dict]) -> dict[int, int]:
    """Count papers by publication year, ordered from oldest to newest."""
    counts: Counter[int] = Counter()
    for paper in papers:
        year = paper.get("pub_year")
        if isinstance(year, bool):
            continue
        try:
            normalized_year = int(year)
        except (TypeError, ValueError):
            continue
        counts[normalized_year] += 1
    return dict(sorted(counts.items()))


def top_journals(papers: list[dict], n: int = 10) -> list[tuple[str, int]]:
    """Return the most frequent non-empty journals with stable tie ordering."""
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise ValueError("n must be a non-negative integer")

    counts = Counter(
        journal
        for paper in papers
        if (journal := str(paper.get("journal") or "").strip())
    )
    return sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))[:n]


from __future__ import annotations

from dataclasses import replace

import anime_catalog
import runtime


def _candidate(source_id: int, title: str = "SpongeBob SquarePants"):
    return anime_catalog.AnimeMetadata(
        title=title,
        source="tmdb",
        source_id=source_id,
    )


def test_query_variants_include_translation(monkeypatch):
    monkeypatch.setattr(runtime, "_translate_query_en", lambda value: "SpongeBob SquarePants")

    variants = runtime._query_variants("Bob Esponja Calça Quadrada")

    assert variants[0] == "Bob Esponja Calça Quadrada"
    assert "SpongeBob SquarePants" in variants
    assert "Bob Esponja" in variants


def test_tmdb_search_falls_back_to_translated_title(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(runtime, "_translate_query_en", lambda value: "SpongeBob SquarePants")

    def fake_search(search, kind, credential, limit=5):
        calls.append(search)
        if search == "SpongeBob SquarePants":
            return [_candidate(387)]
        return []

    monkeypatch.setattr(runtime, "_ORIGINAL_SEARCH_TMDB", fake_search)

    result = runtime._search_tmdb_resilient(
        "Bob Esponja Calça Quadrada",
        "desenho",
        "token",
        limit=5,
    )

    assert result == [_candidate(387)]
    assert calls[:2] == ["Bob Esponja Calça Quadrada", "SpongeBob SquarePants"]


def test_tmdb_search_deduplicates_results(monkeypatch):
    monkeypatch.setattr(runtime, "_translate_query_en", lambda value: "SpongeBob SquarePants")

    def fake_search(search, kind, credential, limit=5):
        if search == "Bob Esponja Calça Quadrada":
            return [_candidate(387, "Bob Esponja Calça Quadrada")]
        return [_candidate(387)]

    monkeypatch.setattr(runtime, "_ORIGINAL_SEARCH_TMDB", fake_search)

    result = runtime._search_tmdb_resilient(
        "Bob Esponja Calça Quadrada",
        "desenho",
        "token",
        limit=5,
    )

    assert len(result) == 1
    assert result[0].source_id == 387

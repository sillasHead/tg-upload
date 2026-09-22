from __future__ import annotations

from dataclasses import replace
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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

def test_runtime_does_not_add_work_hashtag_to_intro():
    previous_context = runtime.library_layout._CONTEXT
    runtime.library_layout._CONTEXT = runtime.library_layout.LibraryContext(
        kind="anime",
        search_tag="Parasyte",
        include_search_tag=True,
    )
    try:
        metadata = anime_catalog.AnimeMetadata(
            title="Parasyte - The Maxim",
            year=2014,
        )
        text = runtime.media_catalog.format_intro(
            metadata,
            "anime",
            max_length=850,
        )
        assert "#Parasyte" not in text
        assert "Parasyte - The Maxim" in text
    finally:
        runtime.library_layout._CONTEXT = previous_context



class RuntimePresentationTests(unittest.IsolatedAsyncioTestCase):
    async def test_work_hashtag_is_added_only_to_presentation_caption(self):
        previous_context = runtime.library_layout._CONTEXT
        previous_items = runtime.entrypoint.launcher._ACTIVE_ITEMS
        runtime.library_layout._CONTEXT = runtime.library_layout.LibraryContext(
            kind="desenho",
            search_tag="Bob_Esponja",
            include_search_tag=True,
        )
        runtime.entrypoint.launcher._ACTIVE_ITEMS = [SimpleNamespace()]
        client = SimpleNamespace()
        captured = {}

        async def send_file(entity, path, caption, reply_to=None, parse_mode=None):
            captured["caption"] = caption

        client.send_file = send_file
        destination = SimpleNamespace(entity="chat", topic_id=None)
        metadata = anime_catalog.AnimeMetadata(
            title="Bob Esponja",
            synopsis="Uma sinopse curta.",
        )

        try:
            with patch.object(
                runtime.entrypoint.launcher,
                "_quality_for_item",
                return_value="720p",
            ), patch.object(
                runtime.entrypoint.launcher,
                "_audio_labels_for_item",
                return_value=("und",),
            ), patch.object(
                runtime.entrypoint.media_catalog,
                "format_intro",
                return_value="📺 Bob Esponja\n🌐 SpongeBob SquarePants\n\n📅 Ano: 1999",
            ), patch.object(
                runtime.entrypoint,
                "_full_synopsis",
                return_value="Uma sinopse curta.",
            ), patch.object(
                runtime.entrypoint.media_catalog,
                "resolve_poster",
                return_value=(Path("poster.jpg"), None),
            ):
                await runtime.entrypoint._publish_intro(
                    client,
                    destination,
                    metadata,
                    Path("."),
                    "desenho",
                )
        finally:
            runtime.library_layout._CONTEXT = previous_context
            runtime.entrypoint.launcher._ACTIVE_ITEMS = previous_items

        caption = captured["caption"]
        self.assertIn("\n#Bob_Esponja\n\n📝 Sinopse:", caption)
        self.assertEqual(caption.count("#Bob_Esponja"), 1)

    def test_presentation_tag_is_not_used_for_movies(self):
        previous_context = runtime.library_layout._CONTEXT
        runtime.library_layout._CONTEXT = runtime.library_layout.LibraryContext(
            kind="filme",
            search_tag="Bob_Esponja",
            include_search_tag=True,
        )
        try:
            self.assertIsNone(runtime.entrypoint._presentation_search_tag("filme"))
        finally:
            runtime.library_layout._CONTEXT = previous_context

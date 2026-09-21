import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import anime_catalog
import catalog_enrichment


class CatalogEnrichmentTests(unittest.TestCase):
    def test_work_title_is_not_repeated_as_episode_title(self):
        metadata = anime_catalog.AnimeMetadata(title="Parasyte - The Maxim")
        self.assertEqual(
            catalog_enrichment._existing_episode_title(
                "Parasyte - The Maxim [1080p]",
                metadata,
            ),
            "",
        )

    def test_work_prefix_is_removed_when_real_episode_title_exists(self):
        metadata = anime_catalog.AnimeMetadata(title="Parasyte - The Maxim")
        self.assertEqual(
            catalog_enrichment._existing_episode_title(
                "Parasyte - The Maxim - Metamorphosis [1080p]",
                metadata,
            ),
            "Metamorphosis",
        )

    def test_generic_episode_name_defers_to_catalog(self):
        metadata = anime_catalog.AnimeMetadata(title="Parasyte - The Maxim")
        self.assertEqual(
            catalog_enrichment._existing_episode_title("Episode 01 [1080p]", metadata),
            "",
        )

    def test_jikan_episode_titles_are_mapped_to_s01_codes(self):
        payload = {
            "data": [
                {"mal_id": 1, "title": "Metamorphosis"},
                {"mal_id": 2, "title": "The Devil in the Flesh"},
            ],
            "pagination": {"has_next_page": False},
        }
        with patch("catalog_enrichment._request_json", return_value=payload) as request:
            titles = catalog_enrichment._jikan_episode_titles(22535)

        self.assertEqual(titles["S01E01"], "Metamorphosis")
        self.assertEqual(titles["S01E02"], "The Devil in the Flesh")
        self.assertNotIn("?page=1", request.call_args.args[0])

    def test_legacy_full_title_tag_is_migrated_to_short_tag(self):
        context = SimpleNamespace(
            root=Path("C:/Videos/Parasyte"),
            metadata=anime_catalog.AnimeMetadata(title="Parasyte - The Maxim"),
            search_tag="Parasyte_The_Maxim",
        )
        save = MagicMock()
        fake_layout = SimpleNamespace(
            _CONTEXT=context,
            _launcher=lambda: SimpleNamespace(
                _ACTIVE_ARGS=SimpleNamespace(search_tag=None)
            ),
            generate_search_tag=lambda value: "Parasyte",
            normalize_search_tag=lambda value: "Parasyte_The_Maxim",
            _save_library_profile=save,
        )

        previous = catalog_enrichment._LIBRARY_LAYOUT
        catalog_enrichment._LIBRARY_LAYOUT = fake_layout
        try:
            catalog_enrichment._migrate_legacy_search_tag()
        finally:
            catalog_enrichment._LIBRARY_LAYOUT = previous

        self.assertEqual(context.search_tag, "Parasyte")
        save.assert_called_once_with(context.root, "Parasyte")

    def test_document_video_can_receive_external_thumbnail_without_becoming_streamable(self):
        calls = []

        @contextmanager
        def fake_thumbnail(path, as_document):
            calls.append((Path(path), as_document))
            yield Path("thumb.jpg")

        previous = catalog_enrichment._ORIGINAL_VIDEO_THUMBNAIL
        catalog_enrichment._ORIGINAL_VIDEO_THUMBNAIL = fake_thumbnail
        try:
            with catalog_enrichment._video_thumbnail(Path("episode.mkv"), True) as thumb:
                self.assertEqual(thumb, Path("thumb.jpg"))
        finally:
            catalog_enrichment._ORIGINAL_VIDEO_THUMBNAIL = previous

        self.assertEqual(calls, [(Path("episode.mkv"), False)])

    def test_episode_cache_round_trip(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            catalog_enrichment._save_titles(
                root,
                "jikan",
                22535,
                {"S01E01": "Metamorphosis"},
            )
            loaded = catalog_enrichment._cached_titles(root, "jikan", 22535)

        self.assertEqual(loaded, {"S01E01": "Metamorphosis"})

    def test_smart_caption_prefers_official_ptbr_episode_title_over_english_filename(self):
        item = SimpleNamespace(
            path=Path("S01E01 - Bitter Chocolate [720p].mp4"),
            season=1,
            episode=1,
            code="S01E01",
            title="Bitter Chocolate [720p]",
        )
        context = SimpleNamespace(
            metadata=anime_catalog.AnimeMetadata(title="Oggy e as Baratas Tontas"),
            search_tag="Oggy",
            include_search_tag=True,
        )
        fake_layout = SimpleNamespace(
            _CONTEXT=context,
            _launcher=lambda: SimpleNamespace(_quality_for_item=lambda value: "720p"),
            _probe=lambda value: None,
            classify_release=lambda value: None,
            format_caption=lambda value, **kwargs: value.title,
        )
        previous_layout = catalog_enrichment._LIBRARY_LAYOUT
        previous_titles = catalog_enrichment._EPISODE_TITLES
        previous_localized = catalog_enrichment._EPISODE_TITLES_LOCALIZED
        catalog_enrichment._LIBRARY_LAYOUT = fake_layout
        catalog_enrichment._EPISODE_TITLES = {"S01E01": "Chocolate Amargo"}
        catalog_enrichment._EPISODE_TITLES_LOCALIZED = {"S01E01"}
        try:
            self.assertEqual(catalog_enrichment.smart_caption(item), "Chocolate Amargo")
        finally:
            catalog_enrichment._LIBRARY_LAYOUT = previous_layout
            catalog_enrichment._EPISODE_TITLES = previous_titles
            catalog_enrichment._EPISODE_TITLES_LOCALIZED = previous_localized

    def test_oggy_fandom_langlink_provides_ptbr_title(self):
        metadata = anime_catalog.AnimeMetadata(
            title="Oggy e as Baratas Tontas",
            source="tmdb",
            source_id=2777,
        )
        payload = {
            "query": {
                "pages": [
                    {
                        "langlinks": [
                            {
                                "lang": "pt-br",
                                "title": "Chocolate Amargo",
                            }
                        ]
                    }
                ]
            }
        }
        with patch("catalog_enrichment._request_json", return_value=payload) as request:
            title = catalog_enrichment._oggy_fandom_ptbr_title(
                metadata,
                "Bitter Chocolate",
            )
        self.assertEqual(title, "Chocolate Amargo")
        self.assertIn("langlinks", request.call_args.args[0])
        self.assertIn("pt-br", request.call_args.args[0])

    def test_oggy_ptbr_lookup_uses_french_langlink_when_numbers_differ(self):
        metadata = anime_catalog.AnimeMetadata(
            title="Oggy e as Baratas Tontas",
            source="tmdb",
            source_id=2777,
        )
        no_ptbr = {"query": {"pages": [{"langlinks": []}]}}
        french_link = {
            "query": {
                "pages": [
                    {
                        "langlinks": [
                            {"lang": "fr", "title": "Le Ticket De Loto"}
                        ]
                    }
                ]
            }
        }
        french_search = {
            "query": {
                "search": [
                    {
                        "title": "O Bilhete de Loteria",
                        "snippet": "Le Ticket De Loto no original em Francês",
                    }
                ]
            }
        }
        with patch(
            "catalog_enrichment._request_json",
            side_effect=[no_ptbr, french_link, {"query": {"search": []}}, french_search],
        ):
            title = catalog_enrichment._oggy_fandom_ptbr_title(
                metadata,
                "The Lottery Ticket",
            )
        self.assertEqual(title, "O Bilhete de Loteria")


    def test_oggy_ptbr_lookup_reads_french_title_from_rendered_page(self):
        metadata = anime_catalog.AnimeMetadata(
            title="Oggy e as Baratas Tontas",
            source="tmdb",
            source_id=2777,
        )
        no_langlinks = {"query": {"pages": [{"langlinks": []}]}}
        rendered_page = {
            "parse": {
                "text": (
                    "<table><tr><th>Language</th><th>Name</th></tr>"
                    "<tr><td>French</td><td>Le Ticket De Loto</td>"
                    "<td>Lottery Ticket</td></tr></table>"
                )
            }
        }
        no_english_search = {"query": {"search": []}}
        french_search = {
            "query": {
                "search": [
                    {
                        "title": "O Bilhete de Loteria",
                        "snippet": "Le Ticket De Loto no original em Francês",
                    }
                ]
            }
        }
        with patch(
            "catalog_enrichment._request_json",
            side_effect=[
                no_langlinks,
                no_langlinks,
                rendered_page,
                no_english_search,
                french_search,
            ],
        ):
            title = catalog_enrichment._oggy_fandom_ptbr_title(
                metadata,
                "The Lottery Ticket",
            )
        self.assertEqual(title, "O Bilhete de Loteria")

    def test_oggy_ptbr_search_verifies_full_page_when_snippet_omits_original(self):
        metadata = anime_catalog.AnimeMetadata(
            title="Oggy e as Baratas Tontas",
            source="tmdb",
            source_id=2777,
        )
        no_langlinks = {"query": {"pages": [{"langlinks": []}]}}
        rendered_without_french = {"parse": {"text": "<p>No language table.</p>"}}
        search_payload = {
            "query": {
                "search": [
                    {
                        "title": "O Bilhete de Loteria",
                        "snippet": "Oggy tenta ficar com o prêmio das baratas.",
                    }
                ]
            }
        }
        verify_payload = {
            "query": {
                "pages": [
                    {
                        "title": "O Bilhete de Loteria",
                        "extract": "Título original: The Lottery Ticket. Oggy e Jack...",
                    }
                ]
            }
        }
        with patch(
            "catalog_enrichment._request_json",
            side_effect=[
                no_langlinks,
                no_langlinks,
                rendered_without_french,
                search_payload,
                verify_payload,
            ],
        ):
            title = catalog_enrichment._oggy_fandom_ptbr_title(
                metadata,
                "The Lottery Ticket",
            )
        self.assertEqual(title, "O Bilhete de Loteria")

    def test_oggy_ptbr_search_fallback_handles_missing_langlink(self):
        metadata = anime_catalog.AnimeMetadata(
            title="Oggy e as Baratas Tontas",
            source="tmdb",
            source_id=2777,
        )
        langlinks_payload = {"query": {"pages": [{"langlinks": []}]}}
        search_payload = {
            "query": {
                "search": [
                    {
                        "title": "O Bilhete de Loteria",
                        "snippet": "Título original: The Lottery Ticket",
                    }
                ]
            }
        }
        rendered_without_french = {"parse": {"text": "<p>No language table.</p>"}}
        with patch(
            "catalog_enrichment._request_json",
            side_effect=[
                langlinks_payload,
                langlinks_payload,
                rendered_without_french,
                search_payload,
            ],
        ):
            title = catalog_enrichment._oggy_fandom_ptbr_title(
                metadata,
                "The Lottery Ticket",
            )
        self.assertEqual(title, "O Bilhete de Loteria")

    def test_oggy_ptbr_search_retries_without_quotes(self):
        metadata = anime_catalog.AnimeMetadata(
            title="Oggy e as Baratas Tontas",
            source="tmdb",
            source_id=2777,
        )
        no_langlinks = {"query": {"pages": [{"langlinks": []}]}}
        rendered_without_french = {"parse": {"text": "<p>No language table.</p>"}}
        no_exact_match = {"query": {"search": []}}
        broad_match = {
            "query": {
                "search": [
                    {
                        "title": "O Bilhete de Loteria",
                        "snippet": "Título original: The Lottery Ticket",
                    }
                ]
            }
        }
        with patch(
            "catalog_enrichment._request_json",
            side_effect=[
                no_langlinks,
                no_langlinks,
                rendered_without_french,
                no_exact_match,
                broad_match,
            ],
        ):
            title = catalog_enrichment._oggy_fandom_ptbr_title(
                metadata,
                "The Lottery Ticket",
            )
        self.assertEqual(title, "O Bilhete de Loteria")


    def test_oggy_uses_fast_english_only_tmdb_path(self):
        metadata = anime_catalog.AnimeMetadata(
            title="Oggy e as Baratas Tontas",
            source="tmdb",
            source_id=2777,
        )
        english = {
            "episodes": [
                {"episode_number": 1, "name": "Bitter Chocolate"},
                {"episode_number": 2, "name": "It's All Under Control"},
                {"episode_number": 3, "name": "The Lottery Ticket"},
            ]
        }

        old_entrypoint = catalog_enrichment._ENTRYPOINT
        catalog_enrichment._ENTRYPOINT = SimpleNamespace(
            _tmdb_credential=lambda config: "token"
        )
        try:
            with patch("catalog_enrichment.upload.load_json", return_value={}):
                with patch(
                    "catalog_enrichment.media_catalog._tmdb_json",
                    return_value=english,
                ) as tmdb:
                    with patch(
                        "catalog_enrichment._oggy_fandom_ptbr_title"
                    ) as fandom:
                        with patch(
                            "catalog_enrichment._tmdb_episode_ptbr_title"
                        ) as episode_ptbr:
                            titles, localized_codes = (
                                catalog_enrichment._tmdb_season_titles(
                                    metadata,
                                    {1},
                                )
                            )

            self.assertEqual(
                titles,
                {
                    "S01E01": "Bitter Chocolate",
                    "S01E02": "It's All Under Control",
                    "S01E03": "The Lottery Ticket",
                },
            )
            self.assertEqual(localized_codes, set())
            tmdb.assert_called_once_with(
                "/tv/2777/season/1",
                "token",
                {"language": "en-US"},
            )
            fandom.assert_not_called()
            episode_ptbr.assert_not_called()
        finally:
            catalog_enrichment._ENTRYPOINT = old_entrypoint

    def test_tmdb_fallback_english_is_not_marked_as_ptbr(self):
        metadata = anime_catalog.AnimeMetadata(
            title="Uma Série Qualquer",
            source="tmdb",
            source_id=2777,
        )
        localized = {
            "episodes": [
                {"episode_number": 1, "name": "Bitter Chocolate"},
            ]
        }
        english = {
            "episodes": [
                {"episode_number": 1, "name": "Bitter Chocolate"},
            ]
        }

        old_entrypoint = catalog_enrichment._ENTRYPOINT
        catalog_enrichment._ENTRYPOINT = SimpleNamespace(
            _tmdb_credential=lambda config: "token"
        )
        try:
            with patch("catalog_enrichment.upload.load_json", return_value={}):
                with patch(
                    "catalog_enrichment.media_catalog._tmdb_json",
                    side_effect=[localized, english, {"translations": []}],
                ):
                    titles, localized_codes = catalog_enrichment._tmdb_season_titles(
                        metadata,
                        {1},
                    )
            self.assertEqual(titles["S01E01"], "Bitter Chocolate")
            self.assertNotIn("S01E01", localized_codes)
        finally:
            catalog_enrichment._ENTRYPOINT = old_entrypoint

    def test_tmdb_explicit_ptbr_translation_is_preferred(self):
        metadata = anime_catalog.AnimeMetadata(
            title="Oggy e as Baratas Tontas",
            source="tmdb",
            source_id=2777,
        )
        localized = {
            "episodes": [
                {"episode_number": 1, "name": "Bitter Chocolate"},
            ]
        }
        english = {
            "episodes": [
                {"episode_number": 1, "name": "Bitter Chocolate"},
            ]
        }
        translations = {
            "translations": [
                {
                    "iso_639_1": "pt",
                    "iso_3166_1": "BR",
                    "data": {"name": "Chocolate Amargo"},
                }
            ]
        }

        old_entrypoint = catalog_enrichment._ENTRYPOINT
        catalog_enrichment._ENTRYPOINT = SimpleNamespace(
            _tmdb_credential=lambda config: "token"
        )
        try:
            with patch("catalog_enrichment.upload.load_json", return_value={}):
                with patch(
                    "catalog_enrichment.media_catalog._tmdb_json",
                    side_effect=[localized, english, translations],
                ):
                    titles, localized_codes = catalog_enrichment._tmdb_season_titles(
                        metadata,
                        {1},
                    )
            self.assertEqual(titles["S01E01"], "Chocolate Amargo")
            self.assertIn("S01E01", localized_codes)
        finally:
            catalog_enrichment._ENTRYPOINT = old_entrypoint

    def test_active_season_poster_uses_tmdb_season_artwork(self):
        import entrypoint

        metadata = anime_catalog.AnimeMetadata(
            title="Oggy e as Baratas Tontas",
            source="tmdb",
            source_id=2777,
            poster="https://image.tmdb.org/t/p/w780/show.jpg",
        )
        previous_items = entrypoint.launcher._ACTIVE_ITEMS
        entrypoint.launcher._ACTIVE_ITEMS = [
            SimpleNamespace(season=1),
            SimpleNamespace(season=1),
        ]
        try:
            with patch("entrypoint.upload.load_json", return_value={}):
                with patch("entrypoint._tmdb_credential", return_value="token"):
                    with patch(
                        "entrypoint.media_catalog._tmdb_json",
                        return_value={"poster_path": "/season1.jpg"},
                    ):
                        updated = entrypoint._metadata_with_active_season_poster(
                            metadata,
                            "desenho",
                        )
            self.assertEqual(
                updated.poster,
                f"{entrypoint.media_catalog.TMDB_IMAGE_BASE}/season1.jpg",
            )
        finally:
            entrypoint.launcher._ACTIVE_ITEMS = previous_items

    def test_catalog_fixes_marks_tmdb_ptbr_titles_as_localized(self):
        import catalog_fixes

        metadata = anime_catalog.AnimeMetadata(
            title="Oggy e as Baratas Tontas",
            source="tmdb",
            source_id=123,
        )
        context = SimpleNamespace(
            root=Path("C:/Videos/Oggy e as Baratas Tontas"),
            kind="desenho",
            metadata=metadata,
        )
        fake_layout = SimpleNamespace(_CONTEXT=context)
        fake_enrichment = SimpleNamespace(
            _active_seasons=lambda: {1},
            _CONTEXT_KEY=None,
            _EPISODE_TITLES={},
            _EPISODE_TITLES_LOCALIZED=set(),
            _cached_titles=lambda *args: {"S01E01": "Bitter Chocolate"},
            _tmdb_season_titles=lambda *args: (
                {"S01E01": "Chocolate Amargo"},
                {"S01E01"},
            ),
            _save_titles=lambda *args: None,
        )

        old_layout = catalog_fixes._LIBRARY_LAYOUT
        old_enrichment = catalog_fixes._CATALOG_ENRICHMENT
        catalog_fixes._LIBRARY_LAYOUT = fake_layout
        catalog_fixes._CATALOG_ENRICHMENT = fake_enrichment
        try:
            catalog_fixes._load_episode_titles()
            self.assertEqual(
                fake_enrichment._EPISODE_TITLES["S01E01"],
                "Chocolate Amargo",
            )
            self.assertIn(
                "S01E01",
                fake_enrichment._EPISODE_TITLES_LOCALIZED,
            )
        finally:
            catalog_fixes._LIBRARY_LAYOUT = old_layout
            catalog_fixes._CATALOG_ENRICHMENT = old_enrichment


if __name__ == "__main__":
    unittest.main()

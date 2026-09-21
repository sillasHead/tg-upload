import unittest

import anime_catalog
import catalog_fixes
import library_layout


class CatalogFixesTests(unittest.TestCase):
    def setUp(self):
        catalog_fixes._LIBRARY_LAYOUT = library_layout

    def test_anilist_stylized_parasyte_title_gets_short_tag(self):
        self.assertEqual(
            catalog_fixes.generate_search_tag("Parasyte -the maxim-"),
            "Parasyte",
        )
        self.assertEqual(
            catalog_fixes.generate_search_tag("Parasyte - The Maxim"),
            "Parasyte",
        )

    def test_normal_hyphenated_word_is_not_split(self):
        self.assertEqual(
            catalog_fixes.generate_search_tag("Spider-Man"),
            "Spider_Man",
        )

    def test_display_title_removes_decorative_trailing_dash(self):
        self.assertEqual(
            catalog_fixes._display_title("Parasyte -the maxim-"),
            "Parasyte - the maxim",
        )

    def test_catalog_header_does_not_repeat_search_tag(self):
        previous_original = catalog_fixes._ORIGINAL_SEASON_HEADER
        previous_context = library_layout._CONTEXT
        catalog_fixes._ORIGINAL_SEASON_HEADER = library_layout.season_header_text
        library_layout._CONTEXT = library_layout.LibraryContext(
            kind="desenho",
            metadata=anime_catalog.AnimeMetadata(title="Oggy e as Baratas Tontas"),
            search_tag="Oggy_E_As_Baratas_Tontas",
            include_search_tag=True,
        )
        try:
            header = catalog_fixes.season_header_text(
                "Oggy e as Baratas Tontas",
                1,
            )
            self.assertEqual(
                header,
                "📺 OGGY E AS BARATAS TONTAS — TEMPORADA 1",
            )
            self.assertNotIn("#Oggy", header)
        finally:
            catalog_fixes._ORIGINAL_SEASON_HEADER = previous_original
            library_layout._CONTEXT = previous_context

    def test_single_anime_season_can_be_remapped(self):
        titles = {"S01E01": "Episode One", "S01E02": "Episode Two"}
        self.assertEqual(
            catalog_fixes._remap_single_anime_season(titles, {2}),
            {"S02E01": "Episode One", "S02E02": "Episode Two"},
        )

    def test_tmdb_candidate_score_prefers_matching_title_and_year(self):
        wanted = anime_catalog.AnimeMetadata(
            title="Parasyte -the maxim-",
            year=2014,
        )
        correct = anime_catalog.AnimeMetadata(
            title="Parasyte - The Maxim",
            year=2014,
            source="tmdb",
            source_id=61459,
        )
        wrong = anime_catalog.AnimeMetadata(
            title="Parasite",
            year=2019,
            source="tmdb",
            source_id=496243,
        )
        self.assertGreater(
            catalog_fixes._candidate_score(correct, wanted),
            catalog_fixes._candidate_score(wrong, wanted),
        )


if __name__ == "__main__":
    unittest.main()

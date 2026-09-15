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

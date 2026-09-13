import tempfile
import unittest
from pathlib import Path

import anime_catalog


class AnimeCatalogTests(unittest.TestCase):
    def test_library_root_skips_generic_media_and_season_dirs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "Parasyte - The Maxim"
            target = root / "mkv" / "Season 01"
            target.mkdir(parents=True)
            self.assertEqual(anime_catalog.library_root(target), root.resolve())

    def test_guess_search_term_removes_release_noise(self):
        root = Path("C:/Videos/parasyte-final")
        self.assertEqual(anime_catalog.guess_search_term(root), "parasyte")

    def test_metadata_round_trip(self):
        anime = anime_catalog.AnimeMetadata(
            title="Parasyte - The Maxim",
            original_title="寄生獣 セイの格率",
            year=2014,
            episodes=24,
            status="FINISHED",
            genres=("Action", "Horror", "Sci-Fi"),
            synopsis="Uma sinopse.",
            poster="poster.jpg",
            source="anilist",
            source_id=20623,
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = anime_catalog.save_metadata(root, anime)
            self.assertTrue(path.exists())
            loaded = anime_catalog.load_metadata(root)
        self.assertEqual(loaded, anime)

    def test_anilist_payload_is_normalized(self):
        anime = anime_catalog._metadata_from_anilist(
            {
                "id": 20623,
                "title": {
                    "english": "Parasyte - The Maxim",
                    "romaji": "Kiseijuu: Sei no Kakuritsu",
                    "native": "寄生獣 セイの格率",
                },
                "description": "A <b>story</b><br>with parasites.",
                "startDate": {"year": 2014},
                "episodes": 24,
                "status": "FINISHED",
                "genres": ["Action", "Horror", "Sci-Fi"],
                "coverImage": {"extraLarge": "https://example.test/poster.jpg"},
            }
        )
        self.assertEqual(anime.title, "Parasyte - The Maxim")
        self.assertEqual(anime.year, 2014)
        self.assertEqual(anime.episodes, 24)
        self.assertEqual(anime.synopsis, "A story\nwith parasites.")
        self.assertEqual(anime.source_url, "https://anilist.co/anime/20623")

    def test_intro_is_localized_and_includes_file_details(self):
        anime = anime_catalog.AnimeMetadata(
            title="Parasyte - The Maxim",
            original_title="寄生獣 セイの格率",
            year=2014,
            episodes=24,
            status="FINISHED",
            genres=("Action", "Horror", "Sci-Fi"),
            synopsis="Sinopse curta.",
        )
        text = anime_catalog.format_intro(
            anime,
            quality="1080p",
            audio_labels=("Português", "Japonês"),
        )
        self.assertIn("Status: Finalizado", text)
        self.assertIn("Ação • Terror • Ficção científica", text)
        self.assertIn("Áudio: Português • Japonês", text)
        self.assertIn("Qualidade: 1080p", text)
        self.assertIn("Sinopse curta.", text)

    def test_intro_respects_caption_limit(self):
        anime = anime_catalog.AnimeMetadata(
            title="Anime",
            synopsis="palavra " * 1000,
        )
        text = anime_catalog.format_intro(anime, max_length=1000)
        self.assertLessEqual(len(text), 1001)
        self.assertTrue(text.endswith("…"))

    def test_language_display(self):
        self.assertEqual(anime_catalog.language_display("por"), "Português")
        self.assertEqual(anime_catalog.language_display("jpn"), "Japonês")
        self.assertEqual(anime_catalog.language_display(None, "Commentary"), "Commentary")


if __name__ == "__main__":
    unittest.main()

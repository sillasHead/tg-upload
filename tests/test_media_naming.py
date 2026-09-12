import unittest
from pathlib import Path

import launcher


def parasyte(name: str) -> Path:
    return Path("Parasyte - The Maxim") / name


class MediaNamingTests(unittest.TestCase):
    def test_episode_code_at_end_becomes_clean_caption(self):
        item = launcher._smart_parse_media(parasyte("Parasyte - The Maxim - S01E06.mkv"))
        self.assertEqual(item.code, "S01E06")
        self.assertEqual(item.season, 1)
        self.assertEqual(item.episode, 6)
        self.assertEqual(item.title, "")
        self.assertEqual(launcher._smart_caption(item), "#S01E06")

    def test_episode_code_at_start_preserves_separator_and_quality(self):
        path = Path("Bob Esponja Calça Quadrada") / "S01E02 - Bolhas de sabão _ Calça rasgada [720p].mp4"
        item = launcher._smart_parse_media(path)
        self.assertEqual(item.code, "S01E02")
        self.assertEqual(item.title, "Bolhas de sabão _ Calça rasgada [720p]")
        self.assertEqual(
            launcher._smart_caption(item),
            "#S01E02 - Bolhas de sabão _ Calça rasgada [720p]",
        )

    def test_plus_from_video_dl_and_quality_are_preserved(self):
        path = Path("Bob Esponja Calça Quadrada") / "S01E02 - Bolhas de sabão + Calça rasgada [720p].mp4"
        item = launcher._smart_parse_media(path)
        self.assertEqual(item.code, "S01E02")
        self.assertEqual(item.title, "Bolhas de sabão + Calça rasgada [720p]")
        self.assertEqual(
            launcher._smart_caption(item),
            "#S01E02 - Bolhas de sabão + Calça rasgada [720p]",
        )

    def test_quality_only_caption_is_compact(self):
        item = launcher._smart_parse_media(parasyte("Parasyte - The Maxim - S01E01 [1080p].mkv"))
        self.assertEqual(item.title, "[1080p]")
        self.assertEqual(launcher._smart_caption(item), "#S01E01 [1080p]")

    def test_episode_code_in_middle_removes_redundant_series_prefix(self):
        item = launcher._smart_parse_media(
            parasyte("Parasyte - The Maxim - S01E06 - Metamorphosis.mkv")
        )
        self.assertEqual(item.code, "S01E06")
        self.assertEqual(item.title, "Metamorphosis")
        self.assertEqual(launcher._smart_caption(item), "#S01E06 - Metamorphosis")

    def test_season_folder_uses_parent_series_as_library(self):
        path = Path("Parasyte - The Maxim") / "Season 01" / "Parasyte - The Maxim - S01E07.mkv"
        item = launcher._smart_parse_media(path)
        self.assertEqual(item.title, "")
        self.assertEqual(launcher._smart_caption(item), "#S01E07")

    def test_unrelated_title_is_not_removed(self):
        path = Path("Anime") / "S01E03 - A chegada.mkv"
        item = launcher._smart_parse_media(path)
        self.assertEqual(item.title, "A chegada")
        self.assertEqual(launcher._smart_caption(item), "#S01E03 - A chegada")


if __name__ == "__main__":
    unittest.main()

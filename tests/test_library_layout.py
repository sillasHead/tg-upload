import unittest
from pathlib import Path

import library_layout
import media_compat
import upload


class LibraryLayoutTests(unittest.TestCase):
    def _probe(self, audios=(), subtitles=()):
        return media_compat.MediaProbe(
            format_name="matroska",
            video=None,
            audios=tuple(audios),
            subtitles=tuple(subtitles),
            attachments=(),
        )

    def _stream(self, index, codec_type, language=None, title=None):
        return media_compat.StreamInfo(
            index=index,
            codec_type=codec_type,
            codec_name="aac" if codec_type == "audio" else "ass",
            language=language,
            title=title,
        )

    def test_short_search_tag_keeps_searchable_words(self):
        self.assertEqual(
            library_layout.generate_search_tag("Attack on Titan"),
            "Attack_On_Titan",
        )
        self.assertEqual(
            library_layout.generate_search_tag("Parasyte - The Maxim"),
            "Parasyte",
        )
        self.assertEqual(
            library_layout.generate_search_tag("Frieren: Beyond Journey's End"),
            "Frieren",
        )

    def test_long_search_tag_is_compact(self):
        self.assertEqual(
            library_layout.generate_search_tag(
                "The 100 Girlfriends Who Really, Really, Really, Really, Really Love You"
            ),
            "100_Girlfriends",
        )

    def test_release_classification(self):
        pt = self._stream(1, "audio", "por")
        jpn = self._stream(2, "audio", "jpn")
        eng = self._stream(3, "audio", "eng")
        pt_sub = self._stream(4, "subtitle", "por")

        self.assertEqual(library_layout.classify_release(self._probe((pt,))), "Dublado")
        self.assertEqual(library_layout.classify_release(self._probe((pt, jpn))), "Dual Áudio")
        self.assertEqual(
            library_layout.classify_release(self._probe((pt, jpn, eng))),
            "Multi Áudio",
        )
        self.assertEqual(
            library_layout.classify_release(self._probe((jpn,), (pt_sub,))),
            "Legendado",
        )
        self.assertIsNone(library_layout.classify_release(self._probe((jpn,))))

    def test_episode_caption_is_compact_and_searchable(self):
        item = upload.MediaItem(
            path=Path("S01E21 - Metamorfose [1080p].mkv"),
            season=1,
            episode=21,
            code="S01E21",
            title="Metamorfose [1080p]",
        )
        caption = library_layout.format_caption(
            item,
            quality="1080p",
            release="Multi Áudio",
            search_tag="Parasyte",
        )
        self.assertEqual(
            caption,
            "#S01E21 - Metamorfose [1080p • Multi Áudio]\n#Parasyte",
        )

    def test_episode_without_title_does_not_create_dangling_separator(self):
        item = upload.MediaItem(
            path=Path("S01E01 [1080p].mkv"),
            season=1,
            episode=1,
            code="S01E01",
            title="[1080p]",
        )
        caption = library_layout.format_caption(
            item,
            quality="1080p",
            release="Dublado",
            search_tag="Parasyte",
        )
        self.assertEqual(caption, "#S01E01 [1080p • Dublado]\n#Parasyte")


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import anime_catalog
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

    def test_episode_thumbnail_prefers_matching_season_poster(self):
        path = Path("C:/Videos/Oggy/S02E03.mp4")
        metadata = anime_catalog.AnimeMetadata(
            title="Oggy e as Baratas Tontas",
            source="tmdb",
            source_id=2777,
            poster="https://image.tmdb.org/t/p/w500/show.jpg",
        )
        previous_context = library_layout._CONTEXT
        previous_launcher = library_layout._LAUNCHER
        library_layout._CONTEXT = library_layout.LibraryContext(
            root=Path("C:/Videos/Oggy"),
            kind="desenho",
            metadata=metadata,
        )
        library_layout._LAUNCHER = SimpleNamespace(
            _ACTIVE_ITEMS=[SimpleNamespace(path=path, season=2)]
        )
        try:
            with patch(
                "library_layout.season_poster_url",
                return_value="https://image.tmdb.org/t/p/w500/season2.jpg",
            ) as season_poster:
                with patch(
                    "library_layout._materialize_poster",
                    return_value=Path("cached-season.jpg"),
                ) as materialize:
                    result = library_layout.poster_source(path)

            self.assertEqual(result, Path("cached-season.jpg"))
            season_poster.assert_called_once_with(metadata, 2)
            materialize.assert_called_once_with(
                "https://image.tmdb.org/t/p/w500/season2.jpg",
                Path("C:/Videos/Oggy"),
            )
        finally:
            library_layout._CONTEXT = previous_context
            library_layout._LAUNCHER = previous_launcher

    def test_season_poster_url_is_cached_per_season(self):
        metadata = anime_catalog.AnimeMetadata(
            title="Oggy e as Baratas Tontas",
            source="tmdb",
            source_id=2777,
        )
        previous_entrypoint = library_layout._ENTRYPOINT
        library_layout._ENTRYPOINT = SimpleNamespace(
            _tmdb_credential=lambda config: "token"
        )
        library_layout._SEASON_POSTER_CACHE.clear()
        try:
            with patch("library_layout.upload.load_json", return_value={}):
                with patch(
                    "library_layout.media_catalog._tmdb_json",
                    return_value={"poster_path": "/season1.jpg"},
                ) as tmdb:
                    first = library_layout.season_poster_url(metadata, 1)
                    second = library_layout.season_poster_url(metadata, 1)

            expected = f"{library_layout.media_catalog.TMDB_IMAGE_BASE}/season1.jpg"
            self.assertEqual(first, expected)
            self.assertEqual(second, expected)
            tmdb.assert_called_once()
        finally:
            library_layout._SEASON_POSTER_CACHE.clear()
            library_layout._ENTRYPOINT = previous_entrypoint

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

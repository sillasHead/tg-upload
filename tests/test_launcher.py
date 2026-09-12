import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from telethon import types

import launcher


class LauncherTests(unittest.TestCase):
    def test_channel_label_channel(self):
        dialog = SimpleNamespace(
            name="Anime",
            id=-100123,
            entity=SimpleNamespace(broadcast=True),
        )
        self.assertEqual(launcher._channel_label(dialog), "Anime  [canal]  -100123")

    def test_channel_label_group(self):
        dialog = SimpleNamespace(
            name="Biblioteca",
            id=-100456,
            entity=SimpleNamespace(broadcast=False),
        )
        self.assertEqual(launcher._channel_label(dialog), "Biblioteca  [grupo]  -100456")

    def test_streaming_flag_depends_on_container(self):
        self.assertTrue(launcher._supports_streaming(Path("episode.mp4"), False))
        self.assertTrue(launcher._supports_streaming(Path("episode.m4v"), False))
        self.assertTrue(launcher._supports_streaming(Path("episode.mkv"), False))
        self.assertFalse(launcher._supports_streaming(Path("episode.avi"), False))
        self.assertFalse(launcher._supports_streaming(Path("episode.mp4"), True))

    def test_mkv_uses_ffprobe_metadata_and_streaming_flag(self):
        initial = [types.DocumentAttributeFilename("episode.mkv")]
        with (
            patch.object(
                launcher.upload.utils,
                "get_attributes",
                return_value=(initial, "video/x-matroska"),
            ),
            patch.object(
                launcher,
                "_ffprobe_video",
                return_value={"width": 1920, "height": 1072, "duration": 1380},
            ),
        ):
            attributes, mime_type, supports_streaming = launcher._media_attributes(
                Path("episode.mkv"), False
            )

        video = next(
            attribute
            for attribute in attributes
            if isinstance(attribute, types.DocumentAttributeVideo)
        )
        self.assertEqual(mime_type, "video/x-matroska")
        self.assertTrue(supports_streaming)
        self.assertTrue(video.supports_streaming)
        self.assertEqual(video.w, 1920)
        self.assertEqual(video.h, 1072)
        self.assertEqual(video.duration, 1380)

    def test_audio_languages_parser_accepts_string_and_list(self):
        self.assertEqual(launcher._parse_audio_languages("por,jpn"), ("por", "jpn"))
        self.assertEqual(launcher._parse_audio_languages(["POR", " jpn "]), ("por", "jpn"))
        self.assertEqual(launcher._parse_audio_languages(None), ())


if __name__ == "__main__":
    unittest.main()

import asyncio
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telethon import types

import anime_catalog
import entrypoint
import launcher
import runtime  # aplica a política usada pelo executável instalado
import upload


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
        self.assertFalse(launcher._supports_streaming(Path("episode.mkv"), False))
        self.assertFalse(launcher._supports_streaming(Path("episode.avi"), False))
        self.assertFalse(launcher._supports_streaming(Path("episode.mp4"), True))

        with patch.object(launcher, "_ACTIVE_PLAYBACK_FIX", "auto"):
            self.assertTrue(launcher._supports_streaming(Path("episode.mkv"), False))

    def test_archive_upload_forces_document(self):
        item = SimpleNamespace(path=Path("Pernalonga.part1.rar"))
        original_send = AsyncMock()

        with patch.object(entrypoint, "_ORIGINAL_SEND_MEDIA", original_send):
            asyncio.run(
                entrypoint._send_media(
                    "client",
                    "entity",
                    item,
                    False,
                    123,
                )
            )

        original_send.assert_awaited_once_with(
            "client",
            "entity",
            item,
            True,
            123,
        )

    def test_collect_media_accepts_archives_and_sorts_multipart_naturally(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in (
                "Pernalonga.part10.rar",
                "Pernalonga.part2.rar",
                "Pernalonga.part1.rar",
                "ignorar.exe",
            ):
                (root / name).write_bytes(b"x")

            items = upload.collect_media(root, recursive=False)

        self.assertEqual(
            [item.path.name for item in items],
            [
                "Pernalonga.part1.rar",
                "Pernalonga.part2.rar",
                "Pernalonga.part10.rar",
            ],
        )

    def test_archive_extensions_are_supported_documents(self):
        self.assertTrue(upload.is_archive_path(Path("colecao.rar")))
        self.assertTrue(upload.is_archive_path(Path("colecao.zip")))
        self.assertTrue(upload.is_archive_path(Path("colecao.7z")))
        self.assertFalse(upload.is_archive_path(Path("episodio.mkv")))

    def test_mkv_default_send_forces_document(self):
        item = SimpleNamespace(path=Path("episode.mkv"))
        original_send = AsyncMock()

        with patch.object(entrypoint, "_ORIGINAL_SEND_MEDIA", original_send):
            asyncio.run(
                entrypoint._send_media(
                    "client",
                    "entity",
                    item,
                    False,
                    123,
                )
            )

        original_send.assert_awaited_once_with(
            "client",
            "entity",
            item,
            True,
            123,
        )

    def test_mkv_playback_fix_receives_explicit_video_attributes_and_streaming(self):
        initial = [types.DocumentAttributeFilename("episode.mkv")]
        with (
            patch.object(launcher, "_ACTIVE_PLAYBACK_FIX", "auto"),
            patch.object(
                launcher.upload.utils,
                "get_attributes",
                return_value=(initial, "video/x-matroska"),
            ),
            patch(
                "telegram_video._probe_video",
                return_value={
                    "width": 1920,
                    "height": 1080,
                    "duration": 1380.5,
                    "codec": "hevc",
                },
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
        self.assertEqual(video.h, 1080)
        self.assertAlmostEqual(float(video.duration), 1380.5)

    def test_audio_languages_parser_accepts_string_and_list(self):
        self.assertEqual(launcher._parse_audio_languages("por,jpn"), ("por", "jpn"))
        self.assertEqual(launcher._parse_audio_languages(["POR", " jpn "]), ("por", "jpn"))
        self.assertEqual(launcher._parse_audio_languages(None), ())

    def test_anime_candidate_choice_keeps_metadata_outside_choice_value(self):
        candidate = anime_catalog.AnimeMetadata(
            title="Parasyte - The Maxim",
            year=2014,
            episodes=24,
        )

        choices, by_value = launcher._anime_candidate_choices([candidate])
        serialized_choice = asdict(choices[0])

        self.assertEqual(serialized_choice["value"], "candidate:0")
        self.assertIsInstance(serialized_choice["value"], str)
        self.assertIs(by_value["candidate:0"], candidate)


if __name__ == "__main__":
    unittest.main()

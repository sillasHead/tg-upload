import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import channel_clone


class _AsyncMessages:
    def __init__(self, messages):
        self._messages = messages

    def __aiter__(self):
        self._iter = iter(self._messages)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class ChannelCloneTests(unittest.TestCase):
    def test_classify_marker(self):
        self.assertEqual(channel_clone.classify_marker("VERSÃO ORIGINAL EM INGLÊS"), "original")
        self.assertEqual(channel_clone.classify_marker("EPISÓDIOS LEGENDADOS"), "legendado")
        self.assertEqual(channel_clone.classify_marker("DUBLADO PT-BR"), "dublado")
        self.assertIsNone(channel_clone.classify_marker("Temporada 1"))

    def test_marker_priority_keeps_legendado_when_pt_br_is_mentioned(self):
        self.assertEqual(
            channel_clone.classify_marker("Legendado em PT-BR"),
            "legendado",
        )

    def test_inspect_source_routes_media_by_latest_marker(self):
        messages = [
            SimpleNamespace(id=1, message="ORIGINAL / ENGLISH", file=None, document=None),
            SimpleNamespace(
                id=2,
                message="",
                file=SimpleNamespace(name="S01E01.mkv"),
                document=object(),
                media=object(),
            ),
            SimpleNamespace(id=3, message="LEGENDADO PT-BR", file=None, document=None),
            SimpleNamespace(
                id=4,
                message="",
                file=SimpleNamespace(name="S01E01-sub.mkv"),
                document=object(),
                media=object(),
            ),
            SimpleNamespace(id=5, message="DUBLADO PT-BR", file=None, document=None),
            SimpleNamespace(
                id=6,
                message="",
                file=SimpleNamespace(name="S01E01-dub.mkv"),
                document=object(),
                media=object(),
            ),
        ]
        client = SimpleNamespace(
            iter_messages=lambda source, reverse=True: _AsyncMessages(messages)
        )
        source = SimpleNamespace(title="Looney Tunes")

        with (
            patch("channel_clone.utils.get_peer_id", return_value=-100123),
            patch("channel_clone.upload.channel_display_name", return_value="Looney Tunes"),
        ):
            plan = asyncio.run(channel_clone.inspect_source(client, source))

        self.assertEqual(
            [(entry.filename, entry.section) for entry in plan.media_entries],
            [
                ("S01E01.mkv", "original"),
                ("S01E01-sub.mkv", "legendado"),
                ("S01E01-dub.mkv", "dublado"),
            ],
        )
        self.assertEqual(
            plan.counts(),
            {
                "original": 1,
                "legendado": 1,
                "dublado": 1,
                "nao-classificado": 0,
            },
        )

    def test_copy_media_uses_existing_telegram_media(self):
        media = object()
        message = SimpleNamespace(id=7, message="legenda", media=media)
        entry = channel_clone.CloneEntry(
            message=message,
            section="original",
            filename="S01E01.mkv",
        )
        destination = SimpleNamespace(entity="destino", topic_id=42)
        client = SimpleNamespace(send_file=AsyncMock())

        asyncio.run(channel_clone._copy_media(client, destination, entry))

        client.send_file.assert_awaited_once_with(
            "destino",
            media,
            caption="legenda",
            reply_to=42,
        )


if __name__ == "__main__":
    unittest.main()

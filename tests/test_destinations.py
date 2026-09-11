import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import upload


class FakeForumClient:
    async def __call__(self, request):
        return SimpleNamespace(
            topics=[
                SimpleNamespace(id=11, title="Animes"),
                SimpleNamespace(id=22, title="Desenhos"),
                SimpleNamespace(id=33, title="Filmes"),
            ]
        )


class DestinationTests(unittest.TestCase):
    def test_normalize_destination(self):
        self.assertEqual(upload.normalize_destination_name(" One-Piece "), "one-piece")
        with self.assertRaises(ValueError):
            upload.normalize_destination_name("anime grande")

    def test_topic_aware_state_key_preserves_legacy_without_topic(self):
        item = upload.MediaItem(Path("S01E02 - Teste.mp4"), 1, 2, "S01E02", "Teste")
        self.assertEqual(upload.upload_key(-1001, None, "Teste", item), "-1001|Teste|S01E02")
        self.assertEqual(upload.upload_key(-1001, 11, "Teste", item), "-1001|topic:11|Teste|S01E02")

    def test_resolve_topic_by_name(self):
        entity = SimpleNamespace(forum=True)
        topic_id, topic_name = asyncio.run(upload.resolve_topic(FakeForumClient(), entity, "Animes"))
        self.assertEqual(topic_id, 11)
        self.assertEqual(topic_name, "Animes")

    def test_resolve_general_without_topic_id(self):
        entity = SimpleNamespace(forum=True)
        topic_id, topic_name = asyncio.run(upload.resolve_topic(FakeForumClient(), entity, "Geral"))
        self.assertIsNone(topic_id)
        self.assertEqual(topic_name, "Geral")


if __name__ == "__main__":
    unittest.main()

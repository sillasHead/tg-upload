import unittest
from types import SimpleNamespace

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


if __name__ == "__main__":
    unittest.main()

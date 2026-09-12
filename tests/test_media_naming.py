from pathlib import Path

import upload


def test_episode_code_at_end_is_removed_from_title():
    item = upload.parse_media(Path("Parasyte - The Maxim - S01E06.mkv"))
    assert item.code == "S01E06"
    assert item.season == 1
    assert item.episode == 6
    assert item.title == "Parasyte - The Maxim"


def test_episode_code_at_start_keeps_episode_title():
    item = upload.parse_media(Path("S01E02 - Bolhas de sabão _ Calça rasgada [720p].mp4"))
    assert item.code == "S01E02"
    assert item.title == "Bolhas de sabão + Calça rasgada"


def test_episode_code_in_middle_preserves_both_sides():
    item = upload.parse_media(Path("Parasyte - The Maxim - S01E06 - Metamorphosis.mkv"))
    assert item.code == "S01E06"
    assert item.title == "Parasyte - The Maxim - Metamorphosis"


def test_caption_omits_redundant_library_title():
    item = upload.parse_media(Path("Parasyte - The Maxim - S01E06.mkv"))
    assert item.caption_for("Parasyte - The Maxim") == "#S01E06"


def test_caption_removes_library_prefix_when_episode_has_title():
    item = upload.parse_media(Path("Parasyte - The Maxim - S01E06 - Metamorphosis.mkv"))
    assert item.caption_for("Parasyte - The Maxim") == "#S01E06 - Metamorphosis"


def test_caption_keeps_real_episode_title():
    item = upload.parse_media(Path("S01E02 - Bolhas de sabão _ Calça rasgada [720p].mp4"))
    assert item.caption_for("Bob Esponja Calça Quadrada") == "#S01E02 - Bolhas de sabão + Calça rasgada"

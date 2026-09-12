from pathlib import Path

import launcher


def parasyte(name: str) -> Path:
    return Path("Parasyte - The Maxim") / name


def test_episode_code_at_end_becomes_clean_caption():
    item = launcher._smart_parse_media(parasyte("Parasyte - The Maxim - S01E06.mkv"))
    assert item.code == "S01E06"
    assert item.season == 1
    assert item.episode == 6
    assert item.title == ""
    assert launcher._smart_caption(item) == "#S01E06"


def test_episode_code_at_start_preserves_existing_separator():
    path = Path("Bob Esponja Calça Quadrada") / "S01E02 - Bolhas de sabão _ Calça rasgada [720p].mp4"
    item = launcher._smart_parse_media(path)
    assert item.code == "S01E02"
    assert item.title == "Bolhas de sabão _ Calça rasgada"
    assert launcher._smart_caption(item) == "#S01E02 - Bolhas de sabão _ Calça rasgada"


def test_plus_from_video_dl_is_preserved():
    path = Path("Bob Esponja Calça Quadrada") / "S01E02 - Bolhas de sabão + Calça rasgada [720p].mp4"
    item = launcher._smart_parse_media(path)
    assert item.code == "S01E02"
    assert item.title == "Bolhas de sabão + Calça rasgada"
    assert launcher._smart_caption(item) == "#S01E02 - Bolhas de sabão + Calça rasgada"


def test_episode_code_in_middle_removes_redundant_series_prefix():
    item = launcher._smart_parse_media(
        parasyte("Parasyte - The Maxim - S01E06 - Metamorphosis.mkv")
    )
    assert item.code == "S01E06"
    assert item.title == "Metamorphosis"
    assert launcher._smart_caption(item) == "#S01E06 - Metamorphosis"


def test_season_folder_uses_parent_series_as_library():
    path = Path("Parasyte - The Maxim") / "Season 01" / "Parasyte - The Maxim - S01E07.mkv"
    item = launcher._smart_parse_media(path)
    assert item.title == ""
    assert launcher._smart_caption(item) == "#S01E07"


def test_unrelated_title_is_not_removed():
    path = Path("Anime") / "S01E03 - A chegada.mkv"
    item = launcher._smart_parse_media(path)
    assert item.title == "A chegada"
    assert launcher._smart_caption(item) == "#S01E03 - A chegada"

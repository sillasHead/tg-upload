from __future__ import annotations

import re
from pathlib import Path

from InquirerPy import inquirer
from InquirerPy.base.control import Choice

import upload


SEASON_DIR_RE = re.compile(r"(?i)^season\s+0*(\d+)$")


def _channel_label(dialog) -> str:
    entity = dialog.entity
    kind = "canal" if getattr(entity, "broadcast", False) else "grupo"
    return f"{dialog.name}  [{kind}]  {dialog.id}"


def _normalize_name(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[._\-–—:|]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _library_from_path(path: Path) -> str | None:
    parent = path.parent
    if not parent.name:
        return None
    if SEASON_DIR_RE.match(parent.name) and parent.parent.name:
        return parent.parent.name
    return parent.name


def _clean_episode_title(stem: str, match: re.Match[str] | None) -> str:
    title = stem
    if match:
        before = stem[: match.start()].strip()
        after = stem[match.end() :].strip()
        if before and after:
            title = f"{before} - {after}"
        else:
            title = before or after

    title = upload.QUALITY_RE.sub("", title)
    title = re.sub(r"\s*[-–—:|]+\s*$", "", title)
    title = re.sub(r"^[\s._+\-–—:|]+", "", title)
    title = re.sub(r"\s+", " ", title).strip(" ._-+")
    return title


def _strip_redundant_library_prefix(title: str, library: str | None) -> str:
    if not title or not library:
        return title

    if _normalize_name(title) == _normalize_name(library):
        return ""

    pattern = re.compile(
        rf"^\s*{re.escape(library)}\s*[-–—:|]+\s*",
        re.IGNORECASE,
    )
    return pattern.sub("", title, count=1).strip()


def _smart_parse_media(path: Path) -> upload.MediaItem:
    stem = path.stem
    match = upload.EPISODE_RE.search(stem)
    if not match:
        title = _clean_episode_title(stem, None) or stem
        return upload.MediaItem(path=path, season=None, episode=None, code=None, title=title)

    season = int(match.group("season"))
    episode = int(match.group("episode"))
    code = f"S{season:02d}E{episode:02d}"

    title = _clean_episode_title(stem, match)
    title = _strip_redundant_library_prefix(title, _library_from_path(path))

    return upload.MediaItem(
        path=path,
        season=season,
        episode=episode,
        code=code,
        title=title,
    )


def _smart_caption(item: upload.MediaItem) -> str:
    if item.code and item.title:
        return f"#{item.code} - {item.title}"
    if item.code:
        return f"#{item.code}"
    return item.title or item.path.stem


async def prompt_channel(client):
    dialogs = []
    async for dialog in client.iter_dialogs():
        if dialog.is_channel:
            dialogs.append(dialog)

    if not dialogs:
        raise RuntimeError("Nenhum canal/grupo do Telegram foi encontrado nessa conta.")

    choices = [Choice(value=dialog.entity, name=_channel_label(dialog)) for dialog in dialogs]
    print("\nDigite para pesquisar. Use ↑/↓ para navegar e Enter para selecionar.")
    return await inquirer.fuzzy(
        message="Canal de destino:",
        choices=choices,
        max_height="70%",
        border=True,
        info=True,
        match_exact=False,
    ).execute_async()


async def prompt_topic(client, entity):
    if not getattr(entity, "forum", False):
        return None, None

    topics = await upload.get_forum_topics(client, entity)
    choices = [Choice(value=(None, "Geral"), name="Geral")]
    choices.extend(
        Choice(
            value=(int(topic.id), upload.topic_display_name(topic)),
            name=f"{upload.topic_display_name(topic)}  [ID {topic.id}]",
        )
        for topic in topics
    )

    print("\nDigite para pesquisar. Use ↑/↓ para navegar e Enter para selecionar.")
    return await inquirer.fuzzy(
        message="Tópico de destino:",
        choices=choices,
        max_height="70%",
        border=True,
        info=True,
        match_exact=False,
    ).execute_async()


def main() -> int:
    upload.prompt_channel = prompt_channel
    upload.prompt_topic = prompt_topic
    upload.parse_media = _smart_parse_media
    upload.MediaItem.caption = property(_smart_caption)
    return upload.main()


if __name__ == "__main__":
    raise SystemExit(main())

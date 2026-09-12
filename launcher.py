from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

from InquirerPy import inquirer
from InquirerPy.base.control import Choice

import fast_upload
import upload


SEASON_DIR_RE = re.compile(r"(?i)^season\s+0*(\d+)$")
QUALITY_ONLY_RE = re.compile(r"(?i)^\[(?:\d{3,4}p|4k|8k)\]$")
DEFAULT_UPLOAD_WORKERS = 4
_ACTIVE_UPLOAD_WORKERS = DEFAULT_UPLOAD_WORKERS
_ORIGINAL_BUILD_PARSER = upload.build_parser
_ORIGINAL_RUN = upload.run


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
        if QUALITY_ONLY_RE.fullmatch(item.title):
            return f"#{item.code} {item.title}"
        return f"#{item.code} - {item.title}"
    if item.code:
        return f"#{item.code}"
    return item.title or item.path.stem


def _resolve_upload_workers(args) -> int:
    requested = getattr(args, "upload_workers", None)
    if requested is None:
        env_value = os.getenv("TG_UPLOAD_WORKERS")
        if env_value:
            requested = env_value
        else:
            config = upload.load_json(upload.CONFIG_PATH, {})
            requested = config.get("upload_workers", DEFAULT_UPLOAD_WORKERS)
    return fast_upload.validate_workers(int(requested))


def _build_parser():
    parser = _ORIGINAL_BUILD_PARSER()
    parser.add_argument(
        "--upload-workers",
        type=int,
        default=None,
        metavar="N",
        help="Uploads paralelos por arquivo (1-8, padrão: 4; 1 usa o modo compatível).",
    )
    return parser


async def _run(args) -> int:
    global _ACTIVE_UPLOAD_WORKERS
    _ACTIVE_UPLOAD_WORKERS = _resolve_upload_workers(args)
    return await _ORIGINAL_RUN(args)


async def _send_compatible(client, entity, item, as_document: bool, topic_id: int | None, reporter) -> None:
    await client.send_file(
        entity,
        str(item.path),
        caption=item.caption,
        force_document=as_document,
        supports_streaming=not as_document,
        reply_to=topic_id,
        progress_callback=reporter,
    )


async def _send_fast(client, entity, item, as_document: bool, topic_id: int | None, reporter) -> None:
    uploaded_file = await fast_upload.upload_file_parallel(
        client,
        item.path,
        workers=_ACTIVE_UPLOAD_WORKERS,
        progress_callback=reporter,
    )
    print()

    attributes, mime_type = upload.utils.get_attributes(
        str(item.path),
        force_document=as_document,
        supports_streaming=not as_document,
    )
    await client.send_file(
        entity,
        uploaded_file,
        caption=item.caption,
        force_document=as_document,
        supports_streaming=not as_document,
        attributes=attributes,
        mime_type=mime_type,
        reply_to=topic_id,
    )


async def _send_media(client, entity, item, as_document: bool, topic_id: int | None = None) -> None:
    label = item.code or item.path.name
    use_fast = _ACTIVE_UPLOAD_WORKERS > 1

    for attempt in range(2):
        reporter = fast_upload.ProgressReporter(label)
        try:
            if use_fast:
                try:
                    await _send_fast(client, entity, item, as_document, topic_id, reporter)
                    return
                except upload.FloodWaitError:
                    print()
                    raise
                except Exception as exc:
                    print()
                    print(
                        f"Upload rápido falhou ({exc.__class__.__name__}: {exc}). "
                        "Tentando modo compatível..."
                    )
                    use_fast = False

            await _send_compatible(client, entity, item, as_document, topic_id, reporter)
            print()
            return
        except upload.FloodWaitError as exc:
            if attempt == 1:
                raise
            wait = int(exc.seconds) + 1
            print(f"\nTelegram pediu espera de {wait}s. Aguardando e reduzindo para o modo compatível...")
            await asyncio.sleep(wait)
            use_fast = False


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
    upload.build_parser = _build_parser
    upload.run = _run
    upload.send_media = _send_media
    return upload.main()


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from telethon import types

import anime_catalog
import fast_upload
import media_compat
import upload


SEASON_DIR_RE = re.compile(r"(?i)^(?:(?:season|temporada)\s*|s)0*(\d+)$")
ANIME_RELEASE_EPISODE_RE = re.compile(
    r"(?i)(?:^|\s[-–—:]\s)(?:ep(?:isode)?\.?\s*)?0*(?P<episode>\d{1,3})"
    r"(?=\s*(?:\[[^\]]+\]\s*)*$)"
)
QUALITY_ONLY_RE = re.compile(r"(?i)^\[(?:\d{3,4}p|4k|8k)\]$")
QUALITY_RE = re.compile(r"(?i)\[(\d{3,4}p|4k|8k)\]")
STREAMABLE_EXTENSIONS = {".mp4", ".m4v", ".mov", ".mkv"}
DEFAULT_UPLOAD_WORKERS = 4
DEFAULT_PLAYBACK_FIX = "auto"
DEFAULT_ANIME_INFO = "auto"
INTRO_STATE_PATH = upload.APP_DIR / "intros.json"
_ACTIVE_UPLOAD_WORKERS = DEFAULT_UPLOAD_WORKERS
_ACTIVE_PLAYBACK_FIX = DEFAULT_PLAYBACK_FIX
_ACTIVE_AUDIO_LANGUAGES: tuple[str, ...] = ()
_ACTIVE_ANIME_INFO = DEFAULT_ANIME_INFO
_ACTIVE_ARGS = None
_ACTIVE_ITEMS: list[upload.MediaItem] = []
_ORIGINAL_BUILD_PARSER = upload.build_parser
_ORIGINAL_RUN = upload.run
_ORIGINAL_CHOOSE_DESTINATION = upload.choose_destination


def _channel_label(dialog) -> str:
    entity = dialog.entity
    kind = "canal" if getattr(entity, "broadcast", False) else "grupo"
    return f"{dialog.name}  [{kind}]  {dialog.id}"


def _normalize_name(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[._\-–—:|]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _season_from_path(path: Path) -> int | None:
    parent = path.parent
    if not parent.name:
        return None
    match = SEASON_DIR_RE.fullmatch(parent.name)
    if not match:
        return None
    return int(match.group(1))


def _library_from_path(path: Path) -> str | None:
    parent = path.parent
    if not parent.name:
        return None
    if SEASON_DIR_RE.fullmatch(parent.name) and parent.parent.name:
        return parent.parent.name
    return parent.name


def _trim_episode_separator(value: str) -> str:
    value = re.sub(r"^[\s._+\-–—:|]+", "", value)
    value = re.sub(r"[\s._+\-–—:|]+$", "", value)
    return value.strip()


def _strip_outer_release_tags(value: str) -> str:
    value = re.sub(r"^(?:\[[^\]]+\]\s*)+", "", value)
    value = re.sub(r"(?:\s*\[[^\]]+\])+$", "", value)
    return value.strip()


def _clean_episode_title(stem: str, match: re.Match[str] | None) -> str:
    title = stem
    if match:
        before = _strip_outer_release_tags(
            _trim_episode_separator(stem[: match.start()])
        )
        after = _strip_outer_release_tags(
            _trim_episode_separator(stem[match.end() :])
        )
        if before and after:
            title = f"{before} - {after}"
        else:
            title = before or after

    title = re.sub(r"\s+", " ", title).strip()
    return _strip_outer_release_tags(title)


def _strip_redundant_library_prefix(title: str, library: str | None) -> str:
    if not title or not library:
        return title

    if _normalize_name(title) == _normalize_name(library):
        return ""

    pattern = re.compile(
        rf"^\s*{re.escape(library)}\s*[-–—:|]+\s*",
        re.IGNORECASE,
    )
    return _trim_episode_separator(pattern.sub("", title, count=1))


def _smart_parse_media(path: Path) -> upload.MediaItem:
    stem = path.stem
    match = upload.EPISODE_RE.search(stem)
    if match:
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

    season = _season_from_path(path)
    release_match = ANIME_RELEASE_EPISODE_RE.search(stem) if season is not None else None
    if release_match:
        episode = int(release_match.group("episode"))
        code = f"S{season:02d}E{episode:02d}"
        title = _clean_episode_title(stem, release_match)
        title = _strip_redundant_library_prefix(title, _library_from_path(path))
        return upload.MediaItem(
            path=path,
            season=season,
            episode=episode,
            code=code,
            title=title,
        )

    title = _clean_episode_title(stem, None) or stem
    return upload.MediaItem(path=path, season=None, episode=None, code=None, title=title)


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


def _resolve_playback_fix(args) -> str:
    requested = getattr(args, "playback_fix", None)
    if requested is None:
        requested = os.getenv("TG_PLAYBACK_FIX")
    if requested is None:
        config = upload.load_json(upload.CONFIG_PATH, {})
        requested = config.get("playback_fix", DEFAULT_PLAYBACK_FIX)

    value = str(requested).strip().casefold()
    if value not in {"auto", "off"}:
        raise ValueError("playback_fix inválido. Use 'auto' ou 'off'.")
    return value


def _resolve_anime_info(args) -> str:
    requested = getattr(args, "anime_info", None)
    if requested is None:
        requested = os.getenv("TG_ANIME_INFO")
    if requested is None:
        config = upload.load_json(upload.CONFIG_PATH, {})
        requested = config.get("anime_info", DEFAULT_ANIME_INFO)

    value = str(requested).strip().casefold()
    if value not in {"auto", "off", "refresh"}:
        raise ValueError("anime_info inválido. Use 'auto', 'refresh' ou 'off'.")
    return value


def _parse_audio_languages(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        parts = [str(item) for item in value]
    else:
        parts = str(value).split(",")
    return tuple(part.strip().casefold() for part in parts if part.strip())


def _resolve_audio_languages(args) -> tuple[str, ...]:
    requested = getattr(args, "audio_languages", None)
    if requested is None:
        requested = os.getenv("TG_AUDIO_LANGUAGES")
    if requested is None:
        config = upload.load_json(upload.CONFIG_PATH, {})
        requested = config.get("audio_languages")
    return _parse_audio_languages(requested)


def _build_parser():
    parser = _ORIGINAL_BUILD_PARSER()
    parser.add_argument(
        "--upload-workers",
        type=int,
        default=None,
        metavar="N",
        help="Uploads paralelos por arquivo (1-8, padrão: 4; 1 usa o modo compatível).",
    )
    parser.add_argument(
        "--playback-fix",
        choices=("auto", "off"),
        default=None,
        help=(
            "Compatibilidade automática de MKV para o player do Telegram "
            "(padrão: auto; use off para enviar o arquivo original sem ajustes)."
        ),
    )
    parser.add_argument(
        "--audio-languages",
        default=None,
        metavar="LANGS",
        help=(
            "Prioridade das faixas de áudio quando um MKV tem mais de duas, "
            "ex.: por,jpn. Sem opção, preserva a faixa padrão e depois a ordem original."
        ),
    )
    parser.add_argument(
        "--anime-info",
        choices=("auto", "refresh", "off"),
        default=None,
        help=(
            "Apresentação automática do anime: auto usa cache/AniList, refresh escolhe "
            "novamente e off desativa."
        ),
    )
    parser.add_argument(
        "--anime-query",
        default=None,
        metavar="NOME",
        help="Termo inicial para pesquisar o anime no AniList.",
    )
    parser.add_argument(
        "--force-info",
        action="store_true",
        help="Publica novamente a apresentação do anime mesmo se ela já foi registrada.",
    )
    return parser


async def _run(args) -> int:
    global _ACTIVE_UPLOAD_WORKERS, _ACTIVE_PLAYBACK_FIX, _ACTIVE_AUDIO_LANGUAGES
    global _ACTIVE_ANIME_INFO, _ACTIVE_ARGS, _ACTIVE_ITEMS
    _ACTIVE_UPLOAD_WORKERS = _resolve_upload_workers(args)
    _ACTIVE_PLAYBACK_FIX = _resolve_playback_fix(args)
    _ACTIVE_AUDIO_LANGUAGES = _resolve_audio_languages(args)
    _ACTIVE_ANIME_INFO = _resolve_anime_info(args)
    _ACTIVE_ARGS = args

    try:
        target = Path(args.path).expanduser().resolve()
        _ACTIVE_ITEMS = upload.collect_media(target, recursive=not args.no_recursive)
    except Exception:
        _ACTIVE_ITEMS = []

    return await _ORIGINAL_RUN(args)


def _supports_streaming(path: Path, as_document: bool) -> bool:
    if as_document:
        return False
    return path.suffix.lower() in STREAMABLE_EXTENSIONS


def _ffprobe_video(path: Path) -> dict[str, int] | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None

    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,duration:format=duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )
        payload = json.loads(result.stdout or "{}")
        streams = payload.get("streams") or []
        if not streams:
            return None

        stream = streams[0]
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
        duration_raw = stream.get("duration") or (payload.get("format") or {}).get("duration") or 0
        duration = max(0, int(round(float(duration_raw))))
        if width <= 0 or height <= 0:
            return None
        return {"width": width, "height": height, "duration": duration}
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _media_attributes(path: Path, as_document: bool):
    supports_streaming = _supports_streaming(path, as_document)
    attributes, mime_type = upload.utils.get_attributes(
        str(path),
        force_document=as_document,
        supports_streaming=supports_streaming,
    )

    if as_document:
        return attributes, mime_type, supports_streaming

    metadata = _ffprobe_video(path)
    if metadata:
        attributes = [
            attribute
            for attribute in attributes
            if not isinstance(attribute, types.DocumentAttributeVideo)
        ]
        attributes.append(
            types.DocumentAttributeVideo(
                duration=metadata["duration"],
                w=metadata["width"],
                h=metadata["height"],
                round_message=False,
                supports_streaming=supports_streaming,
            )
        )

    return attributes, mime_type, supports_streaming


def _replacement_item(item: upload.MediaItem, path: Path) -> upload.MediaItem:
    return upload.MediaItem(
        path=path,
        season=item.season,
        episode=item.episode,
        code=item.code,
        title=item.title,
    )


def _prepare_playable_item(
    item: upload.MediaItem,
    as_document: bool,
) -> tuple[upload.MediaItem, media_compat.PreparedMedia | None]:
    if (
        as_document
        or _ACTIVE_PLAYBACK_FIX == "off"
        or item.path.suffix.casefold() != ".mkv"
    ):
        return item, None

    try:
        plan = media_compat.analyze_for_telegram(
            item.path,
            preferred_languages=_ACTIVE_AUDIO_LANGUAGES,
        )
    except RuntimeError as exc:
        print(f"Compatibilidade Telegram: análise ignorada ({exc})")
        return item, None

    if plan is None or not plan.needs_conversion:
        return item, None

    for line in media_compat.describe_plan(plan):
        print(line)

    prepared = media_compat.prepare_for_telegram(plan)
    return _replacement_item(item, prepared.path), prepared


def _is_anime_destination(destination: upload.Destination) -> bool:
    alias = (destination.alias or "").strip().casefold()
    topic = (destination.topic_name or "").strip().casefold()
    return alias in {"anime", "animes"} or "anime" in topic


def _intro_key(destination: upload.Destination, root: Path) -> str:
    scope = upload.destination_scope(destination.channel_id, destination.topic_id)
    return f"{scope}|anime:{root.name.casefold()}"


def _quality_for_item(item: upload.MediaItem | None) -> str | None:
    if item is None:
        return None
    match = QUALITY_RE.search(item.path.stem)
    if match:
        return match.group(1).upper() if match.group(1).casefold() in {"4k", "8k"} else match.group(1)
    metadata = _ffprobe_video(item.path)
    if metadata and metadata.get("height"):
        return f"{metadata['height']}p"
    return None


def _audio_labels_for_item(item: upload.MediaItem | None) -> tuple[str, ...]:
    if item is None:
        return ()
    try:
        probe = media_compat.probe_media(item.path)
    except RuntimeError:
        return ()

    audios = probe.audios
    if (
        item.path.suffix.casefold() == ".mkv"
        and _ACTIVE_PLAYBACK_FIX != "off"
        and not bool(getattr(_ACTIVE_ARGS, "document", False))
    ):
        plan = media_compat.build_plan(item.path, probe, _ACTIVE_AUDIO_LANGUAGES)
        audios = plan.selected_audios

    labels: list[str] = []
    for audio in audios:
        label = anime_catalog.language_display(audio.language, audio.title)
        if label and label not in labels:
            labels.append(label)
    return tuple(labels)


def _optional_int(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _anime_candidate_choices(
    candidates: list[anime_catalog.AnimeMetadata],
) -> tuple[list[Choice], dict[str, anime_catalog.AnimeMetadata]]:
    choices: list[Choice] = []
    by_value: dict[str, anime_catalog.AnimeMetadata] = {}
    for index, candidate in enumerate(candidates):
        value = f"candidate:{index}"
        choices.append(Choice(value=value, name=candidate.label))
        by_value[value] = candidate
    return choices, by_value


async def _manual_anime_metadata(
    base: anime_catalog.AnimeMetadata | None = None,
) -> anime_catalog.AnimeMetadata | None:
    defaults = base or anime_catalog.AnimeMetadata(title="")

    title = await inquirer.text(
        message="Título:",
        default=defaults.title,
        validate=lambda value: bool(str(value).strip()),
        invalid_message="O título não pode ficar vazio.",
    ).execute_async()
    original = await inquirer.text(
        message="Título original (opcional):",
        default=defaults.original_title or "",
    ).execute_async()
    year = await inquirer.text(
        message="Ano (opcional):",
        default=str(defaults.year or ""),
    ).execute_async()
    episodes = await inquirer.text(
        message="Episódios (opcional):",
        default=str(defaults.episodes or ""),
    ).execute_async()
    status = await inquirer.text(
        message="Status (opcional):",
        default=anime_catalog.status_display(defaults.status) or "",
    ).execute_async()
    genres = await inquirer.text(
        message="Gêneros separados por vírgula (opcional):",
        default=", ".join(defaults.genres),
    ).execute_async()
    synopsis = await inquirer.text(
        message="Sinopse (opcional):",
        default=defaults.synopsis or "",
    ).execute_async()
    poster = await inquirer.text(
        message="Poster: URL ou caminho local (opcional):",
        default=defaults.poster or "",
    ).execute_async()

    return anime_catalog.AnimeMetadata(
        title=str(title).strip(),
        original_title=str(original).strip() or None,
        year=_optional_int(str(year)),
        episodes=_optional_int(str(episodes)),
        status=str(status).strip() or None,
        genres=tuple(part.strip() for part in str(genres).split(",") if part.strip()),
        synopsis=str(synopsis).strip() or None,
        poster=str(poster).strip() or None,
        source="manual" if base is None else f"{base.source}+manual",
        source_id=base.source_id if base else None,
        source_url=base.source_url if base else None,
    )


async def _choose_anime_metadata(
    root: Path,
    initial_query: str,
) -> anime_catalog.AnimeMetadata | None:
    search_term = initial_query

    while True:
        print(f"\nBuscando anime: {search_term}")
        try:
            candidates = anime_catalog.search_anilist(search_term, limit=5)
        except anime_catalog.CatalogError as exc:
            print(f"Catálogo indisponível: {exc}")
            candidates = []

        choices, candidate_by_value = _anime_candidate_choices(candidates)
        choices.extend(
            [
                Choice(value="__search__", name="🔎  Pesquisar outro nome"),
                Choice(value="__manual__", name="✍️  Preencher manualmente"),
                Choice(value="__skip__", name="⏭️  Pular apresentação desta vez"),
            ]
        )

        if not candidates:
            print("Nenhum resultado utilizável foi encontrado. Você pode pesquisar outro nome, preencher manualmente ou pular.")

        selected = await inquirer.select(
            message="Qual anime é este?",
            choices=choices,
            border=True,
            max_height="70%",
        ).execute_async()

        if selected == "__skip__":
            return None
        if selected == "__search__":
            new_term = await inquirer.text(
                message="Pesquisar por:",
                default=search_term,
                validate=lambda value: bool(str(value).strip()),
            ).execute_async()
            search_term = str(new_term).strip()
            continue
        if selected == "__manual__":
            return await _manual_anime_metadata()

        candidate = candidate_by_value.get(str(selected))
        if candidate is None:
            raise RuntimeError(f"Seleção de anime inválida: {selected!r}")

        print("\nPrévia:")
        print(anime_catalog.format_intro(candidate, max_length=850))
        action = await inquirer.select(
            message="O que fazer com estes dados?",
            choices=[
                Choice(value="use", name="✅  Usar estes dados"),
                Choice(value="edit", name="✏️  Usar e editar antes de salvar"),
                Choice(value="back", name="↩️  Voltar aos resultados"),
                Choice(value="search", name="🔎  Pesquisar outro nome"),
                Choice(value="skip", name="⏭️  Pular apresentação desta vez"),
            ],
            border=True,
        ).execute_async()
        if action == "use":
            return candidate
        if action == "edit":
            return await _manual_anime_metadata(candidate)
        if action == "back":
            continue
        if action == "search":
            new_term = await inquirer.text(
                message="Pesquisar por:",
                default=search_term,
                validate=lambda value: bool(str(value).strip()),
            ).execute_async()
            search_term = str(new_term).strip()
            continue
        return None


async def _resolve_anime_metadata(root: Path) -> anime_catalog.AnimeMetadata | None:
    if _ACTIVE_ANIME_INFO != "refresh":
        cached = anime_catalog.load_metadata(root)
        if cached is not None:
            return cached

    if not sys.stdin.isatty():
        print(
            "Apresentação do anime: não há tg-upload.json e o terminal não é interativo; "
            "pulando catálogo."
        )
        return None

    initial_query = (
        str(getattr(_ACTIVE_ARGS, "anime_query", "") or "").strip()
        or anime_catalog.guess_search_term(root)
    )
    anime = await _choose_anime_metadata(root, initial_query)
    if anime is None:
        return None

    try:
        path = anime_catalog.save_metadata(root, anime)
        print(f"Metadata salva em: {path}")
    except OSError as exc:
        print(f"Aviso: não foi possível salvar tg-upload.json ({exc}).")
    return anime


async def _publish_anime_intro(
    client,
    destination: upload.Destination,
    anime: anime_catalog.AnimeMetadata,
    root: Path,
) -> None:
    first_item = _ACTIVE_ITEMS[0] if _ACTIVE_ITEMS else None
    caption = anime_catalog.format_intro(
        anime,
        quality=_quality_for_item(first_item),
        audio_labels=_audio_labels_for_item(first_item),
    )
    poster, tempdir = anime_catalog.resolve_poster(anime, root)

    try:
        if poster is not None:
            try:
                await client.send_file(
                    destination.entity,
                    str(poster),
                    caption=caption,
                    reply_to=destination.topic_id,
                    parse_mode=None,
                )
                return
            except Exception as exc:
                print(f"Poster não pôde ser enviado ({exc}); enviando apresentação em texto.")

        await client.send_message(
            destination.entity,
            caption,
            reply_to=destination.topic_id,
            parse_mode=None,
        )
    finally:
        if tempdir is not None:
            tempdir.cleanup()


async def _maybe_publish_anime_intro(client, destination: upload.Destination) -> None:
    if _ACTIVE_ARGS is None or _ACTIVE_ANIME_INFO == "off":
        return

    target = Path(_ACTIVE_ARGS.path).expanduser().resolve()
    root = anime_catalog.library_root(target)
    cached = anime_catalog.load_metadata(root)

    if _ACTIVE_ANIME_INFO == "auto" and not _is_anime_destination(destination) and cached is None:
        return

    state = upload.load_json(INTRO_STATE_PATH, {"sent": {}})
    sent_state = state.setdefault("sent", {})
    key = _intro_key(destination, root)
    already_sent = key in sent_state
    force_info = bool(getattr(_ACTIVE_ARGS, "force_info", False))

    if already_sent and not force_info and _ACTIVE_ANIME_INFO == "auto":
        return

    anime = await _resolve_anime_metadata(root)
    if anime is None:
        return

    if already_sent and not force_info:
        print(
            "Apresentação já publicada para este destino. Metadata foi atualizada; "
            "use --force-info para publicar novamente."
        )
        return

    print(f"Publicando apresentação: {anime.title}")
    await _publish_anime_intro(client, destination, anime, root)
    sent_state[key] = {
        "sent_at": int(time.time()),
        "title": anime.title,
        "metadata": str(anime_catalog.metadata_path(root)),
    }
    upload.save_json(INTRO_STATE_PATH, state)


async def _choose_destination_with_intro(
    client,
    config,
    alias: str | None,
    requested_channel: str | None,
    requested_topic: str | None,
):
    destination = await _ORIGINAL_CHOOSE_DESTINATION(
        client,
        config,
        alias,
        requested_channel,
        requested_topic,
    )
    await _maybe_publish_anime_intro(client, destination)
    return destination


async def _send_compatible(client, entity, item, as_document: bool, topic_id: int | None, reporter) -> None:
    attributes, mime_type, supports_streaming = _media_attributes(item.path, as_document)
    await client.send_file(
        entity,
        str(item.path),
        caption=item.caption,
        force_document=as_document,
        supports_streaming=supports_streaming,
        attributes=attributes,
        mime_type=mime_type,
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

    attributes, mime_type, supports_streaming = _media_attributes(item.path, as_document)
    await client.send_file(
        entity,
        uploaded_file,
        caption=item.caption,
        force_document=as_document,
        supports_streaming=supports_streaming,
        attributes=attributes,
        mime_type=mime_type,
        reply_to=topic_id,
    )


async def _send_media(client, entity, item, as_document: bool, topic_id: int | None = None) -> None:
    send_item, prepared = _prepare_playable_item(item, as_document)
    label = item.code or item.path.name
    use_fast = _ACTIVE_UPLOAD_WORKERS > 1

    try:
        for attempt in range(2):
            reporter = fast_upload.ProgressReporter(label)
            try:
                if use_fast:
                    try:
                        await _send_fast(client, entity, send_item, as_document, topic_id, reporter)
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

                await _send_compatible(client, entity, send_item, as_document, topic_id, reporter)
                print()
                return
            except upload.FloodWaitError as exc:
                if attempt == 1:
                    raise
                wait = int(exc.seconds) + 1
                print(f"\nTelegram pediu espera de {wait}s. Aguardando e reduzindo para o modo compatível...")
                await asyncio.sleep(wait)
                use_fast = False
    finally:
        if prepared is not None:
            prepared.cleanup()


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
    upload.choose_destination = _choose_destination_with_intro
    upload.send_media = _send_media
    return upload.main()


if __name__ == "__main__":
    raise SystemExit(main())
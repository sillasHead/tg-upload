from __future__ import annotations

import getpass
import os
import sys
import unicodedata
from pathlib import Path

from InquirerPy import inquirer
from InquirerPy.base.control import Choice

import anime_catalog
import launcher
import media_catalog
import upload


# Política padrão de formatos:
# - MP4/M4V/MOV: vídeo reproduzível/streamable quando o Telegram suportar.
# - MKV: preserva o arquivo original e envia como documento.
# O antigo playback-fix continua disponível apenas quando solicitado explicitamente.
launcher.DEFAULT_PLAYBACK_FIX = "off"
launcher._ACTIVE_PLAYBACK_FIX = "off"
launcher.STREAMABLE_EXTENSIONS = {".mp4", ".m4v", ".mov"}

_ORIGINAL_BUILD_PARSER = launcher._build_parser
_ORIGINAL_SEND_MEDIA = launcher._send_media
_ORIGINAL_SHOW_CONFIG = upload.show_config


def _normalize(value: str | None) -> str:
    text = str(value or "").strip().casefold()
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _content_kind(destination: upload.Destination) -> str | None:
    haystack = " ".join(
        part
        for part in (
            _normalize(destination.alias),
            _normalize(destination.topic_name),
        )
        if part
    )
    if not haystack:
        return None

    if "anime" in haystack:
        return "anime"
    if any(token in haystack for token in ("desenho", "cartoon", "animacao", "animation")):
        return "desenho"
    if any(token in haystack for token in ("filme", "movie", "cinema")):
        return "filme"
    if any(token in haystack for token in ("serie", "series", "tv")):
        return "serie"
    return None


def _build_parser():
    parser = _ORIGINAL_BUILD_PARSER()

    for action in parser._actions:
        dest = getattr(action, "dest", None)
        if dest == "playback_fix":
            action.help = (
                "Ajuste experimental de MKV para tentar reprodução inline "
                "(padrão: off; use auto somente quando quiser testar a conversão automática)."
            )
        elif dest == "audio_languages":
            action.help = (
                "Prioridade das faixas de áudio usada somente com --playback-fix auto, "
                "ex.: por,jpn."
            )
        elif dest == "anime_info":
            action.help = (
                "Apresentação automática da mídia: auto usa cache/catálogo, refresh escolhe "
                "novamente e off desativa."
            )
            if "--media-info" not in action.option_strings:
                action.option_strings.append("--media-info")
                parser._option_string_actions["--media-info"] = action
        elif dest == "anime_query":
            action.help = "Termo inicial para pesquisar a mídia no catálogo."
            if "--media-query" not in action.option_strings:
                action.option_strings.append("--media-query")
                parser._option_string_actions["--media-query"] = action

    return parser


def _supports_streaming(path: Path, as_document: bool) -> bool:
    if as_document:
        return False

    suffix = Path(path).suffix.casefold()
    if suffix == ".mkv":
        # Mantém compatibilidade com o modo experimental antigo quando ele for
        # solicitado explicitamente. No fluxo padrão MKV é documento.
        return launcher._ACTIVE_PLAYBACK_FIX == "auto"

    return suffix in launcher.STREAMABLE_EXTENSIONS


async def _send_media(
    client,
    entity,
    item,
    as_document: bool,
    topic_id: int | None = None,
) -> None:
    suffix = item.path.suffix.casefold()
    effective_document = as_document or (
        suffix == ".mkv" and launcher._ACTIVE_PLAYBACK_FIX == "off"
    )
    await _ORIGINAL_SEND_MEDIA(
        client,
        entity,
        item,
        effective_document,
        topic_id,
    )


def _tmdb_credential(config: dict) -> str | None:
    return (
        os.getenv("TMDB_TOKEN")
        or os.getenv("TMDB_API_KEY")
        or config.get("tmdb_token")
        or config.get("tmdb_api_key")
    )


def _ensure_tmdb_credential() -> str | None:
    config = upload.load_json(upload.CONFIG_PATH, {})
    credential = _tmdb_credential(config)
    if credential:
        return str(credential).strip()

    if not sys.stdin.isatty():
        return None

    print(
        "\nTMDB é usado para filmes, séries e desenhos. "
        "A credencial fica somente no seu computador."
    )
    print(
        "Crie um API Read Access Token ou API key em "
        "https://www.themoviedb.org/settings/api"
    )
    credential = getpass.getpass(
        "TMDB API Read Access Token/API key (Enter para pular): "
    ).strip()
    if not credential:
        return None

    config["tmdb_token"] = credential
    upload.save_json(upload.CONFIG_PATH, config)
    print("TMDB configurado.")
    return credential


def _show_config() -> int:
    code = _ORIGINAL_SHOW_CONFIG()
    config = upload.load_json(upload.CONFIG_PATH, {})
    configured = bool(_tmdb_credential(config))
    print(f"TMDB:      {'configurado' if configured else 'não configurado'}")
    return code


def _metadata_root(target: Path) -> Path:
    if target.is_file():
        return target.parent
    return anime_catalog.library_root(target)


def _search_term(target: Path, root: Path, kind: str) -> str:
    requested = str(
        getattr(launcher._ACTIVE_ARGS, "anime_query", "") or ""
    ).strip()
    if requested:
        return requested

    if kind == "filme" and target.is_file():
        item = launcher._ACTIVE_ITEMS[0] if launcher._ACTIVE_ITEMS else None
        if item is not None and item.title:
            return item.title
        return anime_catalog.guess_search_term(Path(target.stem))

    return anime_catalog.guess_search_term(root)


def _cache_key(target: Path, kind: str) -> str | None:
    if kind == "filme" and target.is_file():
        return target.name.casefold()
    return None


def _state_key(
    destination: upload.Destination,
    root: Path,
    kind: str,
    target: Path,
) -> str:
    scope = upload.destination_scope(destination.channel_id, destination.topic_id)
    if kind == "filme" and target.is_file():
        return f"{scope}|{kind}:{target.stem.casefold()}"
    return f"{scope}|{kind}:{root.name.casefold()}"


def _candidate_choices(
    candidates: list[anime_catalog.AnimeMetadata],
) -> tuple[list[Choice], dict[str, anime_catalog.AnimeMetadata]]:
    choices: list[Choice] = []
    by_value: dict[str, anime_catalog.AnimeMetadata] = {}
    for index, candidate in enumerate(candidates):
        value = f"candidate:{index}"
        choices.append(Choice(value=value, name=candidate.label))
        by_value[value] = candidate
    return choices, by_value


async def _manual_metadata(
    base: anime_catalog.AnimeMetadata | None = None,
) -> anime_catalog.AnimeMetadata | None:
    return await launcher._manual_anime_metadata(base)


async def _choose_metadata(
    root: Path,
    target: Path,
    kind: str,
    initial_query: str,
    tmdb_credential: str | None,
) -> anime_catalog.AnimeMetadata | None:
    search_term = initial_query

    while True:
        print(f"\nBuscando {media_catalog.kind_label(kind)}: {search_term}")
        try:
            candidates = media_catalog.search_catalog(
                search_term,
                kind,
                tmdb_credential=tmdb_credential,
                limit=5,
            )
        except media_catalog.MissingTmdbCredential as exc:
            print(str(exc))
            return None
        except (media_catalog.CatalogError, anime_catalog.CatalogError) as exc:
            print(f"Catálogo indisponível: {exc}")
            candidates = []

        choices, candidate_by_value = _candidate_choices(candidates)
        choices.extend(
            [
                Choice(value="__search__", name="🔎  Pesquisar outro nome"),
                Choice(value="__manual__", name="✍️  Preencher manualmente"),
                Choice(value="__skip__", name="⏭️  Pular apresentação desta vez"),
            ]
        )

        if not candidates:
            print(
                "Nenhum resultado utilizável foi encontrado. "
                "Você pode pesquisar outro nome, preencher manualmente ou pular."
            )

        selected = await inquirer.select(
            message=f"Qual {media_catalog.kind_label(kind)} é este?",
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
            return await _manual_metadata()

        candidate = candidate_by_value.get(str(selected))
        if candidate is None:
            raise RuntimeError(f"Seleção inválida: {selected!r}")

        try:
            candidate = media_catalog.enrich_metadata(
                candidate,
                kind,
                tmdb_credential=tmdb_credential,
            )
        except (media_catalog.CatalogError, anime_catalog.CatalogError) as exc:
            print(f"Não foi possível carregar os detalhes ({exc}); usando o resultado da busca.")

        print("\nPrévia:")
        print(
            media_catalog.format_intro(
                candidate,
                kind,
                max_length=850,
            )
        )
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
            return await _manual_metadata(candidate)
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


async def _resolve_metadata(
    root: Path,
    target: Path,
    kind: str,
) -> anime_catalog.AnimeMetadata | None:
    if launcher._ACTIVE_ANIME_INFO != "refresh":
        cached = media_catalog.load_metadata(root, kind, cache_key=_cache_key(target, kind))
        if cached is not None:
            return cached

    if not sys.stdin.isatty():
        print(
            "Apresentação: não há metadata em cache e o terminal não é interativo; "
            "pulando catálogo."
        )
        return None

    credential = None
    if kind != "anime":
        credential = _ensure_tmdb_credential()
        if not credential:
            print(
                "Apresentação ignorada: TMDB não foi configurado. "
                "Use tg-upload set-tmdb-token ou defina TMDB_TOKEN."
            )
            return None

    metadata = await _choose_metadata(
        root,
        target,
        kind,
        _search_term(target, root, kind),
        credential,
    )
    if metadata is None:
        return None

    try:
        path = media_catalog.save_metadata(root, kind, metadata, cache_key=_cache_key(target, kind))
        print(f"Metadata salva em: {path}")
    except OSError as exc:
        print(f"Aviso: não foi possível salvar tg-upload.json ({exc}).")
    return metadata


async def _publish_intro(
    client,
    destination: upload.Destination,
    metadata: anime_catalog.AnimeMetadata,
    root: Path,
    kind: str,
) -> None:
    first_item = launcher._ACTIVE_ITEMS[0] if launcher._ACTIVE_ITEMS else None
    caption = media_catalog.format_intro(
        metadata,
        kind,
        quality=launcher._quality_for_item(first_item),
        audio_labels=launcher._audio_labels_for_item(first_item),
    )
    poster, tempdir = media_catalog.resolve_poster(metadata, root)

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
                print(
                    f"Poster não pôde ser enviado ({exc}); "
                    "enviando apresentação em texto."
                )

        await client.send_message(
            destination.entity,
            caption,
            reply_to=destination.topic_id,
            parse_mode=None,
        )
    finally:
        if tempdir is not None:
            tempdir.cleanup()


async def _maybe_publish_media_intro(
    client,
    destination: upload.Destination,
) -> None:
    if launcher._ACTIVE_ARGS is None or launcher._ACTIVE_ANIME_INFO == "off":
        return

    kind = _content_kind(destination)
    if kind is None:
        return

    target = Path(launcher._ACTIVE_ARGS.path).expanduser().resolve()
    root = _metadata_root(target)
    cached = media_catalog.load_metadata(root, kind, cache_key=_cache_key(target, kind))

    state = upload.load_json(launcher.INTRO_STATE_PATH, {"sent": {}})
    sent_state = state.setdefault("sent", {})
    key = _state_key(destination, root, kind, target)
    already_sent = key in sent_state
    force_info = bool(getattr(launcher._ACTIVE_ARGS, "force_info", False))

    if already_sent and not force_info and launcher._ACTIVE_ANIME_INFO == "auto":
        return

    metadata = await _resolve_metadata(root, target, kind)
    if metadata is None:
        return

    if already_sent and not force_info:
        print(
            "Apresentação já publicada para este destino. Metadata foi atualizada; "
            "use --force-info para publicar novamente."
        )
        return

    print(f"Publicando apresentação: {metadata.title}")
    await _publish_intro(client, destination, metadata, root, kind)
    sent_state[key] = {
        "sent_at": int(__import__("time").time()),
        "title": metadata.title,
        "kind": kind,
        "metadata": str(media_catalog.metadata_path(root)),
    }
    upload.save_json(launcher.INTRO_STATE_PATH, state)


def _set_tmdb_token() -> int:
    config = upload.load_json(upload.CONFIG_PATH, {})
    token = (
        sys.argv[2].strip()
        if len(sys.argv) >= 3
        else getpass.getpass("TMDB API Read Access Token/API key: ").strip()
    )
    if not token:
        print("Credencial vazia.", file=sys.stderr)
        return 2
    config["tmdb_token"] = token
    upload.save_json(upload.CONFIG_PATH, config)
    print("TMDB configurado. A credencial ficou salva apenas no computador.")
    return 0


def _remove_tmdb_token() -> int:
    config = upload.load_json(upload.CONFIG_PATH, {})
    config.pop("tmdb_token", None)
    config.pop("tmdb_api_key", None)
    upload.save_json(upload.CONFIG_PATH, config)
    print("Credencial do TMDB removida da configuração local.")
    return 0


def _catalog_special_command() -> int | None:
    if len(sys.argv) < 2:
        return None
    command = sys.argv[1].casefold()
    if command == "set-tmdb-token":
        if len(sys.argv) > 3:
            print("Uso: tg-upload set-tmdb-token [TOKEN]", file=sys.stderr)
            return 2
        return _set_tmdb_token()
    if command == "remove-tmdb-token":
        if len(sys.argv) != 2:
            print("Uso: tg-upload remove-tmdb-token", file=sys.stderr)
            return 2
        return _remove_tmdb_token()
    return None


launcher._build_parser = _build_parser
launcher._supports_streaming = _supports_streaming
launcher._send_media = _send_media
launcher._maybe_publish_anime_intro = _maybe_publish_media_intro
upload.show_config = _show_config


if __name__ == "__main__":
    special = _catalog_special_command()
    if special is not None:
        raise SystemExit(special)
    raise SystemExit(launcher.main())

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anime_catalog
import media_catalog
import media_compat
import upload


PORTUGUESE_CODES = {"por", "pt", "pt-br", "pt_br", "pob"}
QUALITY_RE = re.compile(r"(?i)\[(\d{3,4}p|4k|8k)\]")
TRAILING_QUALITY_RE = re.compile(r"(?i)\s*\[(?:\d{3,4}p|4k|8k)\]\s*$")
TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_]{0,63}$")
SUBTITLE_SEPARATOR_RE = re.compile(r"\s+(?:-|–|—)\s+|:\s+")
LONG_TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "in",
    "of",
    "on",
    "or",
    "really",
    "that",
    "the",
    "this",
    "to",
    "very",
    "who",
    "with",
}


@dataclass
class LibraryContext:
    root: Path | None = None
    kind: str | None = None
    destination: upload.Destination | None = None
    metadata: anime_catalog.AnimeMetadata | None = None
    search_tag: str | None = None
    include_search_tag: bool = False


_ENTRYPOINT = None
_LAUNCHER = None
_CONTEXT = LibraryContext()
_ORIGINAL_SMART_CAPTION = None
_ORIGINAL_BUILD_PARSER = None
_ORIGINAL_MAYBE_PUBLISH = None
_ORIGINAL_RUN = None
_PROBE_CACHE: dict[tuple[str, int, int], media_compat.MediaProbe] = {}


def _launcher():
    if _LAUNCHER is None:
        raise RuntimeError("library_layout.install() precisa ser chamado antes do uso.")
    return _LAUNCHER


def _entrypoint():
    if _ENTRYPOINT is None:
        raise RuntimeError("library_layout.install() precisa ser chamado antes do uso.")
    return _ENTRYPOINT


def _ascii_words(value: str) -> list[str]:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.findall(r"[A-Za-z0-9]+", text)


def _tag_word(value: str) -> str:
    if not value or value.isdigit():
        return value
    if len(value) > 1 and value.isupper():
        return value
    return value[:1].upper() + value[1:]


def normalize_search_tag(value: str) -> str:
    raw = str(value or "").strip().lstrip("#")
    words = _ascii_words(raw.replace("_", " "))
    tag = "_".join(words)
    if not tag or not TAG_RE.fullmatch(tag):
        raise ValueError(
            "Tag de busca inválida. Use letras, números e _; exemplo: Attack_On_Titan."
        )
    return tag


def generate_search_tag(title: str) -> str:
    """Gera uma tag curta, estável e pesquisável para a obra."""
    text = str(title or "").strip()
    if not text:
        return "Media"

    primary = SUBTITLE_SEPARATOR_RE.split(text, maxsplit=1)[0].strip()
    primary_words = _ascii_words(primary)
    pretty_primary = "_".join(_tag_word(word) for word in primary_words)

    if primary != text and primary_words and len(pretty_primary) <= 32:
        return normalize_search_tag(pretty_primary)

    words = _ascii_words(text)
    if not words:
        return "Media"

    pretty_full = "_".join(_tag_word(word) for word in words)
    if len(pretty_full) <= 32 and len(words) <= 5:
        return normalize_search_tag(pretty_full)

    meaningful = [word for word in words if word.casefold() not in LONG_TITLE_STOPWORDS]
    chosen = (meaningful or words)[:2]
    return normalize_search_tag("_".join(_tag_word(word) for word in chosen))


def _metadata_payload(root: Path) -> dict[str, Any]:
    path = media_catalog.metadata_path(root)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_library_profile(root: Path, search_tag: str) -> None:
    path = media_catalog.metadata_path(root)
    payload = _metadata_payload(root)
    profile = payload.get("library")
    if not isinstance(profile, dict):
        profile = {}
    profile["search_tag"] = search_tag
    payload["library"] = profile
    payload["version"] = max(2, int(payload.get("version") or 1))

    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _saved_search_tag(root: Path) -> str | None:
    profile = _metadata_payload(root).get("library")
    if not isinstance(profile, dict):
        return None
    value = profile.get("search_tag")
    if not value:
        return None
    try:
        return normalize_search_tag(str(value))
    except ValueError:
        return None


def _infer_metadata(root: Path, target: Path) -> tuple[str | None, anime_catalog.AnimeMetadata | None]:
    payload = _metadata_payload(root)

    anime_raw = payload.get("anime")
    if isinstance(anime_raw, dict):
        try:
            return "anime", anime_catalog.AnimeMetadata.from_dict(anime_raw)
        except ValueError:
            pass

    catalog = payload.get(media_catalog.SOURCE_KEY)
    if isinstance(catalog, dict):
        kind = str(catalog.get("kind") or "").strip() or None
        raw = catalog.get("metadata")
        if kind and isinstance(raw, dict):
            try:
                return kind, anime_catalog.AnimeMetadata.from_dict(raw)
            except ValueError:
                pass

    if target.is_file():
        items = payload.get(media_catalog.ITEMS_KEY)
        entry = items.get(target.name.casefold()) if isinstance(items, dict) else None
        if isinstance(entry, dict):
            kind = str(entry.get("kind") or "").strip() or None
            raw = entry.get("metadata")
            if kind and isinstance(raw, dict):
                try:
                    return kind, anime_catalog.AnimeMetadata.from_dict(raw)
                except ValueError:
                    pass

    return None, None


def _load_metadata(root: Path, target: Path, kind: str | None):
    entrypoint = _entrypoint()
    if kind:
        try:
            return media_catalog.load_metadata(
                root,
                kind,
                cache_key=entrypoint._cache_key(target, kind),
            )
        except Exception:
            pass
    _, metadata = _infer_metadata(root, target)
    return metadata


def _is_collection_destination(destination: upload.Destination, kind: str | None) -> bool:
    if kind not in {"anime", "desenho", "serie"}:
        return False
    return _entrypoint()._content_kind(destination) == kind


def _prime_context(destination: upload.Destination) -> None:
    global _CONTEXT
    launcher = _launcher()
    args = getattr(launcher, "_ACTIVE_ARGS", None)
    if args is None or not getattr(args, "path", None):
        _CONTEXT = LibraryContext(destination=destination)
        return

    target = Path(args.path).expanduser().resolve()
    root = _entrypoint()._metadata_root(target)
    kind = _entrypoint()._content_kind(destination)
    if kind is None:
        inferred_kind, inferred_metadata = _infer_metadata(root, target)
        kind = inferred_kind
    else:
        inferred_metadata = None

    metadata = _load_metadata(root, target, kind) or inferred_metadata
    explicit = str(getattr(args, "search_tag", "") or "").strip()
    saved = _saved_search_tag(root)

    tag = None
    persist_tag = False
    if kind in {"anime", "desenho", "serie"}:
        if explicit:
            tag = normalize_search_tag(explicit)
            persist_tag = True
        elif saved:
            tag = saved
        elif metadata is not None:
            # Só salva a sugestão automática após o catálogo confirmar a obra.
            # Evita perpetuar uma tag baseada em pasta como "parasyte-dub".
            tag = generate_search_tag(metadata.title)
            persist_tag = True
        else:
            tag = generate_search_tag(root.name)

        if persist_tag and tag and tag != saved:
            try:
                _save_library_profile(root, tag)
                print(f"Tag de busca: #{tag}")
            except OSError as exc:
                print(f"Aviso: não foi possível salvar a tag de busca ({exc}).")

    _CONTEXT = LibraryContext(
        root=root,
        kind=kind,
        destination=destination,
        metadata=metadata,
        search_tag=tag,
        include_search_tag=_is_collection_destination(destination, kind),
    )


def _language_is_portuguese(code: str | None, title: str | None = None) -> bool:
    value = str(code or "").strip().casefold()
    if value in PORTUGUESE_CODES or value.startswith("pt"):
        return True
    text = unicodedata.normalize("NFKD", str(title or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return any(token in text for token in ("portugues", "brazilian portuguese", "pt-br"))


def classify_release(probe: media_compat.MediaProbe) -> str | None:
    audios = tuple(probe.audios)
    has_pt_audio = any(_language_is_portuguese(a.language, a.title) for a in audios)
    has_pt_subtitle = any(_language_is_portuguese(s.language, s.title) for s in probe.subtitles)

    if has_pt_audio:
        if len(audios) >= 3:
            return "Multi Áudio"
        if len(audios) == 2:
            return "Dual Áudio"
        return "Dublado"

    if has_pt_subtitle:
        return "Legendado"
    return None


def _probe(item: upload.MediaItem) -> media_compat.MediaProbe | None:
    try:
        stat = item.path.stat()
        key = (str(item.path.resolve()), stat.st_size, stat.st_mtime_ns)
    except OSError:
        return None
    if key in _PROBE_CACHE:
        return _PROBE_CACHE[key]
    try:
        result = media_compat.probe_media(item.path)
    except RuntimeError:
        return None
    _PROBE_CACHE[key] = result
    return result


def format_caption(
    item: upload.MediaItem,
    *,
    quality: str | None,
    release: str | None,
    search_tag: str | None = None,
) -> str:
    if not item.code:
        if _ORIGINAL_SMART_CAPTION is not None:
            return _ORIGINAL_SMART_CAPTION(item)
        return item.title or item.path.stem

    title = TRAILING_QUALITY_RE.sub("", item.title or "").strip()
    line = f"#{item.code}"
    if title:
        line += f" - {title}"

    details = [value for value in (quality, release) if value]
    if details:
        line += " [" + " • ".join(details) + "]"

    if search_tag:
        line += f"\n#{search_tag}"
    return line


def smart_caption(item: upload.MediaItem) -> str:
    launcher = _launcher()
    quality = launcher._quality_for_item(item)
    probe = _probe(item)
    release = classify_release(probe) if probe is not None else None
    tag = _CONTEXT.search_tag if _CONTEXT.include_search_tag else None
    return format_caption(item, quality=quality, release=release, search_tag=tag)


def season_header_text(library: str, season: int) -> str:
    if _CONTEXT.include_search_tag and _CONTEXT.search_tag:
        title = (
            _CONTEXT.metadata.title
            if _CONTEXT.metadata is not None and _CONTEXT.metadata.title
            else library
        )
        return f"📺 {title.upper()} — TEMPORADA {season}\n#{_CONTEXT.search_tag}"
    return f"📺 #S{season:02d} — TEMPORADA {season}"


def _poster_cache_path(poster: str) -> Path:
    parsed = urllib.parse.urlparse(poster)
    suffix = Path(parsed.path).suffix.casefold()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    digest = hashlib.sha256(poster.encode("utf-8")).hexdigest()[:24]
    return upload.APP_DIR / "poster-cache" / f"{digest}{suffix}"


def poster_source(path: Path) -> Path | None:
    metadata = _CONTEXT.metadata
    root = _CONTEXT.root
    if metadata is None or root is None or not metadata.poster:
        return None

    poster = metadata.poster.strip()
    parsed = urllib.parse.urlparse(poster)
    if parsed.scheme in {"http", "https"}:
        target = _poster_cache_path(poster)
        if target.is_file() and target.stat().st_size > 0:
            return target
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            request = urllib.request.Request(poster, headers={"User-Agent": "tg-upload/1.0"})
            temp = target.with_suffix(target.suffix + ".tmp")
            with urllib.request.urlopen(request, timeout=20) as response, temp.open("wb") as handle:
                handle.write(response.read())
            if temp.stat().st_size <= 0:
                temp.unlink(missing_ok=True)
                return None
            temp.replace(target)
            return target
        except Exception:
            return None

    candidate = Path(poster).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate if candidate.is_file() else None


def _build_parser():
    parser = _ORIGINAL_BUILD_PARSER()
    if "--search-tag" not in parser._option_string_actions:
        parser.add_argument(
            "--search-tag",
            default=None,
            metavar="TAG",
            help=(
                "Tag canônica da obra no tópico geral, ex.: Attack_On_Titan. "
                "É salva em tg-upload.json e reutilizada nos próximos envios."
            ),
        )
    for action in parser._actions:
        if getattr(action, "dest", None) == "upload_workers":
            action.help = "Uploads concorrentes por arquivo (1-8, padrão: 8)."
    return parser


async def _maybe_publish_with_context(client, destination: upload.Destination) -> None:
    _prime_context(destination)
    await _ORIGINAL_MAYBE_PUBLISH(client, destination)
    _prime_context(destination)


async def _run_with_layout(args) -> int:
    target = Path(args.path).expanduser().resolve()
    items = upload.collect_media(target, recursive=not args.no_recursive)
    if not items:
        print("Nenhum vídeo encontrado.")
        return 1

    if args.dry_run:
        upload.print_plan(items)
        print(f"\nTotal: {len(items)} arquivo(s). Nada foi enviado.")
        return 0

    upload.APP_DIR.mkdir(parents=True, exist_ok=True)
    config: dict[str, Any] = upload.load_json(upload.CONFIG_PATH, {})
    state: dict[str, Any] = upload.load_json(upload.STATE_PATH, {"uploads": {}, "headers": {}})
    state.setdefault("uploads", {})
    state.setdefault("headers", {})

    api_id, api_hash = upload.get_api_credentials(config)
    library = args.library or upload.infer_library_name(target)

    client = upload.TelegramClient(str(upload.SESSION_BASE), api_id, api_hash)
    await client.start()

    try:
        destination = await upload.choose_destination(client, config, args.to, args.channel, args.topic)
        entity = destination.entity
        channel_id = destination.channel_id
        topic_id = destination.topic_id
        print(f"\nDestino: {destination.display_name}")
        if destination.alias:
            print(f"Atalho: {destination.alias}")
        print(f"Biblioteca: {library}")
        if _CONTEXT.search_tag and _CONTEXT.include_search_tag:
            print(f"Busca: #{_CONTEXT.search_tag}")
        print(f"Arquivos encontrados: {len(items)}")

        named_items = [item for item in items if item.code]
        if named_items:
            print("\nNomes no Telegram:")
            for item in named_items:
                presentation = str(item.caption or "").strip().splitlines()[0].strip()
                suffix = item.path.suffix
                if suffix and presentation and not presentation.casefold().endswith(suffix.casefold()):
                    presentation += suffix
                print(f"  {presentation or item.path.name}")
        print()

        sent = skipped = failed = 0
        announced_this_run: set[int] = set()

        for item in items:
            key = upload.upload_key(channel_id, topic_id, library, item)
            if not args.force and key in state["uploads"]:
                print(f"Pulado: {item.path.name}")
                skipped += 1
                continue

            if (
                item.season is not None
                and not args.no_season_header
                and item.season not in announced_this_run
            ):
                hkey = upload.header_key(channel_id, topic_id, library, item.season)
                if args.force_header or hkey not in state["headers"]:
                    text = season_header_text(library, item.season)
                    await client.send_message(entity, text, reply_to=topic_id)
                    state["headers"][hkey] = {
                        "sent_at": int(time.time()),
                        "text": text,
                    }
                    upload.save_json(upload.STATE_PATH, state)
                announced_this_run.add(item.season)

            print(f"Enviando: {item.path.name}")
            presentation = str(item.caption or "").strip().splitlines()[0].strip()
            if item.code and presentation:
                suffix = item.path.suffix
                if suffix and not presentation.casefold().endswith(suffix.casefold()):
                    presentation += suffix
                print(f"Nome Telegram: {presentation}")
            try:
                await upload.send_media(
                    client,
                    entity,
                    item,
                    as_document=args.document,
                    topic_id=topic_id,
                )
            except Exception as exc:
                failed += 1
                print(f"Falhou: {item.path.name}\n  {exc}", file=sys.stderr)
                if args.stop_on_error:
                    raise
                continue

            stat = item.path.stat()
            state["uploads"][key] = {
                "file": item.path.name,
                "size": stat.st_size,
                "sent_at": int(time.time()),
                "caption": item.caption,
            }
            upload.save_json(upload.STATE_PATH, state)
            sent += 1

            if args.delay > 0:
                await asyncio.sleep(args.delay)

        print("\nResumo:")
        print(f"  Enviados: {sent}")
        print(f"  Pulados:  {skipped}")
        print(f"  Falharam: {failed}")
        return 0 if failed == 0 else 2
    finally:
        await client.disconnect()


def install(entrypoint_module) -> None:
    global _ENTRYPOINT, _LAUNCHER
    global _ORIGINAL_SMART_CAPTION, _ORIGINAL_BUILD_PARSER, _ORIGINAL_MAYBE_PUBLISH, _ORIGINAL_RUN

    _ENTRYPOINT = entrypoint_module
    _LAUNCHER = entrypoint_module.launcher
    launcher = _LAUNCHER

    _ORIGINAL_SMART_CAPTION = launcher._smart_caption
    _ORIGINAL_BUILD_PARSER = launcher._build_parser
    _ORIGINAL_MAYBE_PUBLISH = launcher._maybe_publish_anime_intro
    _ORIGINAL_RUN = launcher._ORIGINAL_RUN

    launcher._smart_caption = smart_caption
    launcher._build_parser = _build_parser
    launcher._maybe_publish_anime_intro = _maybe_publish_with_context
    launcher._ORIGINAL_RUN = _run_with_layout

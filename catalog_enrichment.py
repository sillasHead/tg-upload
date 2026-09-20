from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import anime_catalog
import media_catalog
import upload


JIKAN_API = "https://api.jikan.moe/v4"
VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".mkv"}
GENERIC_EPISODE_RE = re.compile(
    r"(?i)^(?:episode|epis[oó]dio|ep)\s*[#._ -]*0*(\d+)$"
)
TRAILING_QUALITY_RE = re.compile(r"(?i)\s*\[(?:\d{3,4}p|4k|8k)\]\s*$")
SEPARATOR_PREFIX_RE = r"\s*(?:-|–|—|:|\|)\s*"

_ENTRYPOINT = None
_LIBRARY_LAYOUT = None
_TELEGRAM_VIDEO = None
_ORIGINAL_PRIME_CONTEXT = None
_ORIGINAL_VIDEO_THUMBNAIL = None
_EPISODE_TITLES: dict[str, str] = {}
_EPISODE_TITLES_LOCALIZED: set[str] = set()
_CONTEXT_KEY: tuple[Any, ...] | None = None
_WARNED: set[str] = set()


def _warn_once(key: str, message: str) -> None:
    if key in _WARNED:
        return
    _WARNED.add(key)
    print(message)


def _payload(root: Path) -> dict[str, Any]:
    path = media_catalog.metadata_path(root)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _profile(root: Path) -> dict[str, Any]:
    value = _payload(root).get("library")
    return value if isinstance(value, dict) else {}


def _save_profile(root: Path, updates: dict[str, Any]) -> None:
    path = media_catalog.metadata_path(root)
    payload = _payload(root)
    profile = payload.get("library")
    if not isinstance(profile, dict):
        profile = {}
    profile.update(updates)
    payload["library"] = profile
    try:
        version = int(payload.get("version") or 1)
    except (TypeError, ValueError):
        version = 1
    payload["version"] = max(3, version)

    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _request_json(
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    attempts: int = 3,
) -> Any:
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "tg-upload/1.0",
    }
    if headers:
        request_headers.update(headers)

    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        request = urllib.request.Request(
            url,
            data=data,
            headers=request_headers,
            method="POST" if data is not None else "GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            retryable = exc.code == 429 or 500 <= exc.code <= 599
            if not retryable or attempt + 1 >= attempts:
                break
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                delay = float(retry_after) if retry_after else 1.0 + attempt
            except (TypeError, ValueError):
                delay = 1.0 + attempt
            time.sleep(min(max(delay, 0.5), 4.0))
        except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt + 1 >= attempts:
                break
            time.sleep(0.75 + attempt)

    raise RuntimeError(f"falha ao consultar catálogo de episódios: {last_error}")


def _resolve_anilist_mal_id(metadata: anime_catalog.AnimeMetadata) -> int | None:
    if metadata.source != "anilist" or metadata.source_id is None:
        return None

    query = """
    query ($id: Int!) {
      Media(id: $id, type: ANIME) { idMal }
    }
    """
    body = json.dumps(
        {"query": query, "variables": {"id": int(metadata.source_id)}}
    ).encode("utf-8")
    payload = _request_json(
        anime_catalog.ANILIST_ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json"},
        attempts=2,
    )
    raw = (((payload or {}).get("data") or {}).get("Media") or {}).get("idMal")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _useful_episode_name(value: Any, number: int) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    folded = unicodedata.normalize("NFKD", text.casefold())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = re.sub(r"\s+", " ", folded).strip()
    if folded in {"tba", "tbd", "n/a", "unknown"}:
        return None
    match = GENERIC_EPISODE_RE.fullmatch(folded)
    if match and int(match.group(1)) == int(number):
        return None
    return text


def _jikan_episode_titles(mal_id: int) -> dict[str, str]:
    titles: dict[str, str] = {}
    page = 1
    while page <= 50:
        base = f"{JIKAN_API}/anime/{int(mal_id)}/episodes"
        url = base if page == 1 else f"{base}?{urllib.parse.urlencode({'page': page})}"
        payload = _request_json(url, attempts=3)
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            break

        for entry in data:
            if not isinstance(entry, dict):
                continue
            try:
                number = int(entry.get("mal_id"))
            except (TypeError, ValueError):
                continue
            title = _useful_episode_name(
                entry.get("title") or entry.get("title_romanji") or entry.get("title_japanese"),
                number,
            )
            if title:
                titles[f"S01E{number:02d}"] = title

        pagination = payload.get("pagination") if isinstance(payload, dict) else None
        has_next = bool(pagination.get("has_next_page")) if isinstance(pagination, dict) else False
        if not has_next:
            break
        page += 1

    return titles


def _oggy_fandom_ptbr_title(
    metadata: anime_catalog.AnimeMetadata,
    original_title: str | None,
    aliases: tuple[str, ...] = (),
) -> str | None:
    """Resolve a Brazilian Portuguese Oggy title without machine translation.

    Oggy's Brazilian wiki often stores the original French episode title, while
    TMDB/files commonly use the English title. Try both forms so the lookup is
    not dependent on one catalog's naming convention.
    """
    candidates: list[str] = []
    for value in (original_title, *aliases):
        value = str(value or "").strip()
        if value and value.casefold() not in {item.casefold() for item in candidates}:
            candidates.append(value)
    if not candidates:
        return None

    series_names = {
        _normalized(metadata.title),
        _normalized(metadata.original_title or ""),
    }
    if not any("oggy" in value for value in series_names if value):
        return None

    for original in candidates:
        # 1) Explicit interlanguage mapping from the English/French page.
        params = urllib.parse.urlencode(
            {
                "action": "query",
                "prop": "langlinks",
                "titles": original,
                "lllang": "pt-br",
                "format": "json",
                "formatversion": 2,
                "redirects": 1,
            }
        )
        url = f"https://oggyandthecockroaches.fandom.com/api.php?{params}"
        try:
            payload = _request_json(url, attempts=2)
        except RuntimeError:
            payload = None

        query = payload.get("query") if isinstance(payload, dict) else None
        pages = query.get("pages") if isinstance(query, dict) else None
        if isinstance(pages, list) and pages:
            links = pages[0].get("langlinks") if isinstance(pages[0], dict) else None
            if isinstance(links, list):
                for link in links:
                    if not isinstance(link, dict):
                        continue
                    if str(link.get("lang") or "").casefold() not in {"pt-br", "pt_br"}:
                        continue
                    title = str(link.get("title") or link.get("*") or "").strip()
                    if title:
                        return title

        # 2) Search the Brazilian wiki using either the English or French title.
        search_params = urllib.parse.urlencode(
            {
                "action": "query",
                "list": "search",
                "srsearch": f'"{original}"',
                "srwhat": "text",
                "srlimit": 5,
                "format": "json",
                "formatversion": 2,
            }
        )
        search_url = (
            "https://oggy-e-as-baratas-tontas.fandom.com/pt-br/api.php?"
            + search_params
        )
        try:
            search_payload = _request_json(search_url, attempts=2)
        except RuntimeError:
            continue

        search_query = (
            search_payload.get("query")
            if isinstance(search_payload, dict)
            else None
        )
        results = (
            search_query.get("search")
            if isinstance(search_query, dict)
            else None
        )
        if not isinstance(results, list):
            continue

        wanted = _normalized(original)
        for result in results:
            if not isinstance(result, dict):
                continue
            title = str(result.get("title") or "").strip()
            snippet = re.sub(r"<[^>]+>", " ", str(result.get("snippet") or ""))
            if not title:
                continue
            haystack = _normalized(f"{title} {snippet}")
            if wanted and wanted in haystack:
                return title
    return None


def _tmdb_episode_ptbr_title(
    metadata: anime_catalog.AnimeMetadata,
    season: int,
    episode: int,
    credential: str,
) -> str | None:
    """Return only an explicit Brazilian Portuguese episode translation.

    TMDB may return the original/English title even when language=pt-BR if no
    Brazilian Portuguese translation exists. The translations endpoint lets us
    distinguish a real pt-BR title from that fallback.
    """
    try:
        payload = media_catalog._tmdb_json(
            f"/tv/{int(metadata.source_id)}/season/{season}/episode/{episode}/translations",
            credential,
            {},
        )
    except Exception:
        return None

    translations = payload.get("translations") if isinstance(payload, dict) else None
    if not isinstance(translations, list):
        return None

    for entry in translations:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("iso_639_1") or "").casefold() != "pt":
            continue
        if str(entry.get("iso_3166_1") or "").casefold() != "br":
            continue
        data = entry.get("data")
        if not isinstance(data, dict):
            continue
        title = _useful_episode_name(data.get("name"), episode)
        if title:
            return title
    return None


def _tmdb_season_titles(
    metadata: anime_catalog.AnimeMetadata,
    seasons: set[int],
) -> tuple[dict[str, str], set[str]]:
    if _ENTRYPOINT is None or metadata.source != "tmdb" or metadata.source_id is None:
        return {}, set()

    config = upload.load_json(upload.CONFIG_PATH, {})
    credential = _ENTRYPOINT._tmdb_credential(config)
    if not credential:
        return {}, set()

    titles: dict[str, str] = {}
    localized_codes: set[str] = set()

    for season in sorted(value for value in seasons if value >= 0):
        try:
            localized = media_catalog._tmdb_json(
                f"/tv/{int(metadata.source_id)}/season/{season}",
                credential,
                {"language": "pt-BR"},
            )
            english = media_catalog._tmdb_json(
                f"/tv/{int(metadata.source_id)}/season/{season}",
                credential,
                {"language": "en-US"},
            )
            french = media_catalog._tmdb_json(
                f"/tv/{int(metadata.source_id)}/season/{season}",
                credential,
                {"language": "fr-FR"},
            )
        except Exception:
            continue

        localized_entries = localized.get("episodes") if isinstance(localized, dict) else None
        english_entries = english.get("episodes") if isinstance(english, dict) else None
        french_entries = french.get("episodes") if isinstance(french, dict) else None
        if not isinstance(localized_entries, list):
            continue
        if not isinstance(english_entries, list):
            english_entries = []

        english_by_number: dict[int, str] = {}
        for entry in english_entries:
            if not isinstance(entry, dict):
                continue
            try:
                number = int(entry.get("episode_number"))
            except (TypeError, ValueError):
                continue
            title = _useful_episode_name(entry.get("name"), number)
            if title:
                english_by_number[number] = title

        french_by_number: dict[int, str] = {}
        if isinstance(french_entries, list):
            for entry in french_entries:
                if not isinstance(entry, dict):
                    continue
                try:
                    number = int(entry.get("episode_number"))
                except (TypeError, ValueError):
                    continue
                title = _useful_episode_name(entry.get("name"), number)
                if title:
                    french_by_number[number] = title

        seen_numbers: set[int] = set()
        for entry in localized_entries:
            if not isinstance(entry, dict):
                continue
            try:
                number = int(entry.get("episode_number"))
            except (TypeError, ValueError):
                continue

            seen_numbers.add(number)
            localized_title = _useful_episode_name(entry.get("name"), number)
            english_title = english_by_number.get(number)
            explicit_ptbr = None

            # If pt-BR differs from en-US, TMDB clearly localized the title.
            if localized_title and (
                not english_title
                or _normalized(localized_title) != _normalized(english_title)
            ):
                explicit_ptbr = localized_title
            elif localized_title:
                # Same text can be TMDB's fallback. Verify whether an explicit
                # pt-BR translation actually exists before marking it localized.
                explicit_ptbr = _tmdb_episode_ptbr_title(
                    metadata,
                    season,
                    number,
                    credential,
                )

            if not explicit_ptbr and english_title:
                french_title = french_by_number.get(number)
                aliases = (french_title,) if french_title else ()
                explicit_ptbr = _oggy_fandom_ptbr_title(
                    metadata,
                    english_title,
                    aliases=aliases,
                )

            code = f"S{season:02d}E{number:02d}"
            if explicit_ptbr:
                titles[code] = explicit_ptbr
                localized_codes.add(code)
            elif english_title:
                titles[code] = english_title
            elif localized_title:
                titles[code] = localized_title

        # Preserve English fallback entries that are absent from the localized
        # payload entirely.
        for number, english_title in english_by_number.items():
            if number in seen_numbers:
                continue
            titles[f"S{season:02d}E{number:02d}"] = english_title

    return titles, localized_codes


def _cached_titles(root: Path, provider: str, catalog_id: int) -> dict[str, str]:
    raw = _profile(root).get("episode_titles")
    if not isinstance(raw, dict):
        return {}
    if str(raw.get("provider") or "") != provider:
        return {}
    if str(raw.get("catalog_id") or "") != str(int(catalog_id)):
        return {}
    values = raw.get("titles")
    if not isinstance(values, dict):
        return {}
    return {
        str(code): str(title).strip()
        for code, title in values.items()
        if str(code).strip() and str(title).strip()
    }


def _save_titles(
    root: Path,
    provider: str,
    catalog_id: int,
    titles: dict[str, str],
) -> None:
    _save_profile(
        root,
        {
            "episode_titles": {
                "provider": provider,
                "catalog_id": int(catalog_id),
                "titles": dict(sorted(titles.items())),
                "updated_at": int(time.time()),
            }
        },
    )


def _active_seasons() -> set[int]:
    if _LIBRARY_LAYOUT is None:
        return {1}
    launcher = _LIBRARY_LAYOUT._launcher()
    seasons = {
        int(item.season)
        for item in getattr(launcher, "_ACTIVE_ITEMS", [])
        if getattr(item, "season", None) is not None
    }
    return seasons or {1}


def _load_episode_titles() -> None:
    global _EPISODE_TITLES, _EPISODE_TITLES_LOCALIZED, _CONTEXT_KEY
    if _LIBRARY_LAYOUT is None:
        return

    context = _LIBRARY_LAYOUT._CONTEXT
    root = context.root
    metadata = context.metadata
    if root is None or metadata is None or context.kind not in {"anime", "desenho", "serie"}:
        _EPISODE_TITLES = {}
        _EPISODE_TITLES_LOCALIZED = set()
        _CONTEXT_KEY = None
        return

    key = (
        str(root),
        context.kind,
        metadata.source,
        metadata.source_id,
        tuple(sorted(_active_seasons())),
    )
    if key == _CONTEXT_KEY:
        return
    _CONTEXT_KEY = key
    _EPISODE_TITLES = {}
    _EPISODE_TITLES_LOCALIZED = set()

    if context.kind == "anime" and metadata.source == "anilist":
        profile = _profile(root)
        raw_mal = profile.get("mal_id")
        try:
            mal_id = int(raw_mal) if raw_mal is not None else None
        except (TypeError, ValueError):
            mal_id = None

        if mal_id is None:
            try:
                mal_id = _resolve_anilist_mal_id(metadata)
            except RuntimeError as exc:
                _warn_once("anilist-mal", f"Aviso: nomes dos episódios indisponíveis ({exc}).")
                return
            if mal_id is not None:
                try:
                    _save_profile(root, {"mal_id": mal_id})
                except OSError:
                    pass

        if mal_id is None:
            return

        cached = _cached_titles(root, "jikan", mal_id)
        if cached:
            _EPISODE_TITLES = cached
            return

        try:
            titles = _jikan_episode_titles(mal_id)
        except RuntimeError as exc:
            _warn_once("jikan", f"Aviso: nomes dos episódios indisponíveis ({exc}).")
            return
        if titles:
            _EPISODE_TITLES = titles
            try:
                _save_titles(root, "jikan", mal_id, titles)
            except OSError:
                pass
            print(f"Títulos de episódios: {len(titles)} carregados do catálogo.")
        return

    if context.kind in {"desenho", "serie"} and metadata.source == "tmdb" and metadata.source_id is not None:
        catalog_id = int(metadata.source_id)
        cached = _cached_titles(root, "tmdb", catalog_id)
        seasons = _active_seasons()
        required_prefixes = {f"S{season:02d}E" for season in seasons}
        cached_prefixes = {
            prefix
            for prefix in required_prefixes
            if any(code.startswith(prefix) for code in cached)
        }
        # Old caches did not record which titles actually came from pt-BR.
        # Refresh active seasons so localized TMDB titles can replace English/file names.
        if cached_prefixes == required_prefixes:
            missing_seasons = set(seasons)
        else:
            missing_seasons = {
                season
                for season in seasons
                if f"S{season:02d}E" not in cached_prefixes
            }

        fetched, localized_codes = _tmdb_season_titles(metadata, missing_seasons)
        merged = {**cached, **fetched}
        _EPISODE_TITLES = merged
        _EPISODE_TITLES_LOCALIZED = localized_codes
        if fetched:
            try:
                _save_titles(root, "tmdb", catalog_id, merged)
            except OSError:
                pass
            print(f"Títulos de episódios: {len(merged)} carregados do catálogo.")


def _normalized(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _existing_episode_title(
    value: str | None,
    metadata: anime_catalog.AnimeMetadata | None,
) -> str:
    title = TRAILING_QUALITY_RE.sub("", str(value or "")).strip()
    if not title:
        return ""

    candidates = []
    if metadata is not None:
        candidates.extend([metadata.title, metadata.original_title])

    normalized_title = _normalized(title)
    for candidate in candidates:
        candidate = str(candidate or "").strip()
        if not candidate:
            continue
        if normalized_title == _normalized(candidate):
            return ""
        match = re.match(
            rf"^\s*{re.escape(candidate)}{SEPARATOR_PREFIX_RE}(.+?)\s*$",
            title,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()

    generic = GENERIC_EPISODE_RE.fullmatch(_normalized(title))
    if generic:
        return ""
    return title


def _looks_like_series_title(
    value: str | None,
    metadata: anime_catalog.AnimeMetadata | None,
    season: int | None,
) -> bool:
    """Retorna True quando o 'título do episódio' é só obra + número da temporada."""
    if metadata is None:
        return False

    title = _normalized(value)
    if not title:
        return False

    season_number = int(season) if season is not None else None
    for candidate in (metadata.title, metadata.original_title):
        base = _normalized(candidate)
        if not base:
            continue

        variants = {base}
        if season_number is not None:
            variants.update(
                {
                    f"{base} {season_number}",
                    f"{base} season {season_number}",
                    f"{base} temporada {season_number}",
                    f"{base} s{season_number}",
                    f"{base} s{season_number:02d}",
                }
            )

        if title in variants:
            return True

    return False


def _migrate_legacy_search_tag() -> None:
    if _LIBRARY_LAYOUT is None:
        return
    context = _LIBRARY_LAYOUT._CONTEXT
    if context.root is None or context.metadata is None or not context.search_tag:
        return

    launcher = _LIBRARY_LAYOUT._launcher()
    args = getattr(launcher, "_ACTIVE_ARGS", None)
    if str(getattr(args, "search_tag", "") or "").strip():
        return

    canonical = _LIBRARY_LAYOUT.generate_search_tag(context.metadata.title)
    if canonical == context.search_tag:
        return
    try:
        full_title_tag = _LIBRARY_LAYOUT.normalize_search_tag(context.metadata.title)
    except ValueError:
        return
    if context.search_tag != full_title_tag:
        return

    try:
        _LIBRARY_LAYOUT._save_library_profile(context.root, canonical)
    except OSError:
        return
    context.search_tag = canonical
    print(f"Tag de busca ajustada: #{canonical}")


def _prime_context(destination) -> None:
    if _ORIGINAL_PRIME_CONTEXT is None:
        return
    _ORIGINAL_PRIME_CONTEXT(destination)
    _migrate_legacy_search_tag()
    _load_episode_titles()


def smart_caption(item: upload.MediaItem) -> str:
    if _LIBRARY_LAYOUT is None:
        return item.title or item.path.stem

    launcher = _LIBRARY_LAYOUT._launcher()
    context = _LIBRARY_LAYOUT._CONTEXT
    quality = launcher._quality_for_item(item)
    probe = _LIBRARY_LAYOUT._probe(item)
    release = _LIBRARY_LAYOUT.classify_release(probe) if probe is not None else None
    tag = context.search_tag if context.include_search_tag else None

    title = _existing_episode_title(item.title, context.metadata)
    if item.code and _looks_like_series_title(title, context.metadata, item.season):
        title = ""

    # For TV/cartoon libraries, an official pt-BR TMDB episode title wins over
    # the filename's English title. If TMDB has no pt-BR title, preserve the
    # existing filename title; only then fall back to the catalog (usually en-US).
    localized_title = _EPISODE_TITLES.get(item.code, "") if item.code in _EPISODE_TITLES_LOCALIZED else ""
    if item.code and localized_title:
        title = localized_title
    elif item.code and not title:
        title = _EPISODE_TITLES.get(item.code, "")

    display_item = upload.MediaItem(
        path=item.path,
        season=item.season,
        episode=item.episode,
        code=item.code,
        title=title,
    )
    return _LIBRARY_LAYOUT.format_caption(
        display_item,
        quality=quality,
        release=release,
        search_tag=tag,
    )


@contextmanager
def _video_thumbnail(path: Path, as_document: bool) -> Iterator[Path | None]:
    if _ORIGINAL_VIDEO_THUMBNAIL is None:
        yield None
        return

    # Thumbnail é metadata externa do documento: não altera um único byte do MKV.
    # Para mídia enviada como documento, reaproveita o mesmo gerador de capa/frame,
    # mas mantém force_document=True e supports_streaming=False no envio real.
    use_visual_source = as_document and Path(path).suffix.casefold() in VIDEO_EXTENSIONS
    with _ORIGINAL_VIDEO_THUMBNAIL(path, False if use_visual_source else as_document) as thumb:
        yield thumb


def install(entrypoint_module, telegram_video_module, library_layout_module) -> None:
    global _ENTRYPOINT, _LIBRARY_LAYOUT, _TELEGRAM_VIDEO
    global _ORIGINAL_PRIME_CONTEXT, _ORIGINAL_VIDEO_THUMBNAIL

    _ENTRYPOINT = entrypoint_module
    _LIBRARY_LAYOUT = library_layout_module
    _TELEGRAM_VIDEO = telegram_video_module

    _ORIGINAL_PRIME_CONTEXT = library_layout_module._prime_context
    _ORIGINAL_VIDEO_THUMBNAIL = telegram_video_module._video_thumbnail

    library_layout_module._prime_context = _prime_context
    library_layout_module.smart_caption = smart_caption
    entrypoint_module.launcher._smart_caption = smart_caption
    telegram_video_module._video_thumbnail = _video_thumbnail

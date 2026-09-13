from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import replace
from pathlib import Path
from typing import Any

import anime_catalog


TMDB_API = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

KIND_LABELS = {
    "anime": "anime",
    "desenho": "desenho",
    "serie": "série",
    "filme": "filme",
}

STATUS_PT = {
    "RETURNING SERIES": "Em exibição",
    "PLANNED": "Planejado",
    "IN PRODUCTION": "Em produção",
    "ENDED": "Finalizado",
    "CANCELED": "Cancelado",
    "CANCELLED": "Cancelado",
    "PILOT": "Piloto",
    "RELEASED": "Lançado",
    "POST PRODUCTION": "Pós-produção",
    "RUMORED": "Rumor",
}

GENRE_PT = {
    **anime_catalog.GENRE_PT,
    "Animation": "Animação",
    "Family": "Família",
    "Kids": "Infantil",
    "Science Fiction": "Ficção científica",
    "Science-Fiction": "Ficção científica",
    "War": "Guerra",
    "History": "História",
    "Crime": "Crime",
    "Documentary": "Documentário",
    "Reality": "Reality show",
    "Talk": "Talk show",
    "News": "Notícias",
    "Western": "Faroeste",
    "Action & Adventure": "Ação e aventura",
    "Sci-Fi & Fantasy": "Ficção científica e fantasia",
    "War & Politics": "Guerra e política",
}

SOURCE_KEY = "catalog"
ITEMS_KEY = "catalog_items"


class CatalogError(RuntimeError):
    pass


class MissingTmdbCredential(CatalogError):
    pass


def kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind, kind)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_html(value: str | None) -> str | None:
    if not value:
        return None
    text = html.unescape(str(value))
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip() or None


def _year_from_date(value: Any) -> int | None:
    text = str(value or "").strip()
    match = re.match(r"^(\d{4})", text)
    return int(match.group(1)) if match else None


def _translate_if_needed(text: str | None) -> str | None:
    clean = _clean_html(text)
    if not clean:
        return None
    return anime_catalog.translate_synopsis_pt(clean)


def _request_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 15,
) -> Any:
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "tg-upload/1.0",
    }
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise CatalogError(f"Catálogo respondeu HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise CatalogError(f"Não foi possível acessar o catálogo: {exc.reason}") from exc
    except (OSError, TimeoutError, json.JSONDecodeError) as exc:
        raise CatalogError(f"Falha ao consultar o catálogo: {exc}") from exc


def _tmdb_auth(credential: str) -> tuple[dict[str, str], dict[str, str]]:
    value = str(credential or "").strip()
    if not value:
        raise MissingTmdbCredential("TMDB não configurado.")
    if value.startswith("eyJ") or len(value) > 64:
        return {"Authorization": f"Bearer {value}"}, {}
    return {}, {"api_key": value}


def _tmdb_json(
    path: str,
    credential: str,
    params: dict[str, Any] | None = None,
) -> Any:
    headers, auth_params = _tmdb_auth(credential)
    query: dict[str, Any] = {}
    query.update(auth_params)
    if params:
        query.update(params)
    suffix = "?" + urllib.parse.urlencode(query) if query else ""
    try:
        return _request_json(f"{TMDB_API}{path}{suffix}", headers=headers)
    except CatalogError as exc:
        if "HTTP 401" in str(exc):
            raise MissingTmdbCredential(
                "TMDB recusou a credencial. Confira o API Read Access Token/API key."
            ) from exc
        raise


def _tmdb_candidate(item: dict[str, Any], kind: str) -> anime_catalog.AnimeMetadata:
    is_movie = kind == "filme"
    title = item.get("title") if is_movie else item.get("name")
    original = item.get("original_title") if is_movie else item.get("original_name")
    date = item.get("release_date") if is_movie else item.get("first_air_date")
    source_id = item.get("id")
    poster_path = item.get("poster_path")
    poster = f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else None
    source_url = (
        f"https://www.themoviedb.org/movie/{source_id}"
        if is_movie
        else f"https://www.themoviedb.org/tv/{source_id}"
    ) if source_id else None

    return anime_catalog.AnimeMetadata(
        title=str(title or original or "Mídia").strip(),
        original_title=_optional_text(original) if original != title else None,
        year=_year_from_date(date),
        synopsis=_optional_text(item.get("overview")),
        poster=poster,
        source="tmdb",
        source_id=int(source_id) if source_id is not None else None,
        source_url=source_url,
    )


def search_tmdb(
    search: str,
    kind: str,
    credential: str,
    limit: int = 5,
) -> list[anime_catalog.AnimeMetadata]:
    if kind not in {"desenho", "serie", "filme"}:
        raise CatalogError(f"Tipo TMDB inválido: {kind}")

    endpoint = "/search/movie" if kind == "filme" else "/search/tv"
    payload = _tmdb_json(
        endpoint,
        credential,
        {
            "query": search,
            "language": "pt-BR",
            "include_adult": "false",
            "page": 1,
        },
    )
    results = [item for item in (payload.get("results") or []) if isinstance(item, dict)]

    if kind == "desenho":
        # Animation = genre id 16 no TMDB. Mantém todos os resultados, mas
        # prioriza animações para reduzir falsos positivos.
        results.sort(key=lambda item: 16 not in (item.get("genre_ids") or []))

    return [_tmdb_candidate(item, kind) for item in results[: max(1, min(limit, 10))]]


def enrich_tmdb(
    metadata: anime_catalog.AnimeMetadata,
    kind: str,
    credential: str,
) -> anime_catalog.AnimeMetadata:
    if metadata.source != "tmdb" or metadata.source_id is None:
        return metadata

    is_movie = kind == "filme"
    endpoint = f"/movie/{metadata.source_id}" if is_movie else f"/tv/{metadata.source_id}"
    details = _tmdb_json(endpoint, credential, {"language": "pt-BR"})

    title = details.get("title") if is_movie else details.get("name")
    original = details.get("original_title") if is_movie else details.get("original_name")
    date = details.get("release_date") if is_movie else details.get("first_air_date")
    genres = tuple(
        str(entry.get("name")).strip()
        for entry in (details.get("genres") or [])
        if isinstance(entry, dict) and entry.get("name")
    )
    episodes = None if is_movie else details.get("number_of_episodes")
    overview = _optional_text(details.get("overview"))

    if not overview:
        english = _tmdb_json(endpoint, credential, {"language": "en-US"})
        overview = _translate_if_needed(english.get("overview"))

    poster_path = details.get("poster_path")
    poster = f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else metadata.poster

    return replace(
        metadata,
        title=str(title or metadata.title).strip(),
        original_title=_optional_text(original) if original and original != title else None,
        year=_year_from_date(date) or metadata.year,
        episodes=int(episodes) if episodes else None,
        status=_optional_text(details.get("status")),
        genres=genres,
        synopsis=overview or metadata.synopsis,
        poster=poster,
    )


def search_catalog(
    search: str,
    kind: str,
    *,
    tmdb_credential: str | None = None,
    limit: int = 5,
) -> list[anime_catalog.AnimeMetadata]:
    if kind == "anime":
        return anime_catalog.search_anilist(search, limit=limit)
    if kind in {"desenho", "serie", "filme"}:
        return search_tmdb(search, kind, tmdb_credential or "", limit=limit)
    raise CatalogError(f"Tipo de mídia não suportado: {kind}")


def enrich_metadata(
    metadata: anime_catalog.AnimeMetadata,
    kind: str,
    *,
    tmdb_credential: str | None = None,
) -> anime_catalog.AnimeMetadata:
    if kind == "anime":
        return anime_catalog.localize_anime(metadata)
    if metadata.source == "tmdb":
        return enrich_tmdb(metadata, kind, tmdb_credential or "")
    return metadata


def metadata_path(root: Path) -> Path:
    return anime_catalog.metadata_path(root)


def load_metadata(
    root: Path,
    kind: str,
    *,
    cache_key: str | None = None,
) -> anime_catalog.AnimeMetadata | None:
    if kind == "anime" and cache_key is None:
        return anime_catalog.load_metadata(root)

    path = metadata_path(root)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None

        if cache_key:
            items = payload.get(ITEMS_KEY)
            catalog = items.get(cache_key) if isinstance(items, dict) else None
        else:
            catalog = payload.get(SOURCE_KEY)

        if not isinstance(catalog, dict) or catalog.get("kind") != kind:
            return None
        raw = catalog.get("metadata")
        if not isinstance(raw, dict):
            return None
        return anime_catalog.AnimeMetadata.from_dict(raw)
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return None


def save_metadata(
    root: Path,
    kind: str,
    metadata: anime_catalog.AnimeMetadata,
    *,
    cache_key: str | None = None,
) -> Path:
    if kind == "anime" and cache_key is None:
        return anime_catalog.save_metadata(root, metadata)

    path = metadata_path(root)
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                existing = raw
        except (OSError, json.JSONDecodeError):
            existing = {}

    existing["version"] = max(2, int(existing.get("version") or 1))
    entry = {
        "kind": kind,
        "metadata": metadata.to_dict(),
    }
    if cache_key:
        items = existing.setdefault(ITEMS_KEY, {})
        if not isinstance(items, dict):
            items = {}
            existing[ITEMS_KEY] = items
        items[cache_key] = entry
    else:
        existing[SOURCE_KEY] = entry

    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    return path


def status_display(status: str | None) -> str | None:
    if not status:
        return None
    key = status.strip().upper()
    if key in STATUS_PT:
        return STATUS_PT[key]
    return anime_catalog.status_display(status)


def genre_display(value: str) -> str:
    return GENRE_PT.get(value, anime_catalog.genre_display(value))


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[: max(0, limit - 1)].rstrip()
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" .,:;-") + "…"


def format_intro(
    metadata: anime_catalog.AnimeMetadata,
    kind: str,
    *,
    quality: str | None = None,
    audio_labels: tuple[str, ...] = (),
    max_length: int = 1000,
) -> str:
    if kind == "anime":
        return anime_catalog.format_intro(
            metadata,
            quality=quality,
            audio_labels=audio_labels,
            max_length=max_length,
        )

    icon = "🎬" if kind == "filme" else "📺"
    lines = [f"{icon} {metadata.title}"]
    if metadata.original_title and metadata.original_title.casefold() != metadata.title.casefold():
        lines.append(f"🌐 {metadata.original_title}")
    lines.append("")

    facts: list[str] = []
    if metadata.year:
        facts.append(f"📅 Ano: {metadata.year}")
    if metadata.episodes and kind != "filme":
        facts.append(f"📺 Episódios: {metadata.episodes}")
    status = status_display(metadata.status)
    if status:
        facts.append(f"✅ Status: {status}")
    if metadata.genres:
        facts.append(
            "🎭 Gêneros: " + " • ".join(genre_display(item) for item in metadata.genres)
        )
    if audio_labels:
        facts.append(f"🔊 Áudio: {' • '.join(audio_labels)}")
    if quality:
        facts.append(f"🖥️ Qualidade: {quality}")
    lines.extend(facts)

    base = "\n".join(lines).rstrip()
    synopsis = _clean_html(metadata.synopsis)
    if not synopsis:
        return _truncate(base, max_length)

    prefix = base + "\n\n📝 Sinopse:\n"
    remaining = max(80, max_length - len(prefix))
    return prefix + _truncate(synopsis, remaining)


def resolve_poster(
    metadata: anime_catalog.AnimeMetadata,
    root: Path,
):
    return anime_catalog.resolve_poster(metadata, root)

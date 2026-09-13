from __future__ import annotations

import html
import json
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ANILIST_ENDPOINT = "https://graphql.anilist.co"
METADATA_FILENAME = "tg-upload.json"
GENERIC_MEDIA_DIRS = {
    "mkv",
    "mp4",
    "video",
    "videos",
    "media",
    "files",
    "arquivos",
}
SEASON_DIR_RE = re.compile(r"(?i)^(?:season|temporada)\s*0*(\d+)$")

STATUS_PT = {
    "FINISHED": "Finalizado",
    "RELEASING": "Em lançamento",
    "NOT_YET_RELEASED": "Ainda não lançado",
    "CANCELLED": "Cancelado",
    "HIATUS": "Em hiato",
}

GENRE_PT = {
    "Action": "Ação",
    "Adventure": "Aventura",
    "Comedy": "Comédia",
    "Drama": "Drama",
    "Ecchi": "Ecchi",
    "Fantasy": "Fantasia",
    "Horror": "Terror",
    "Mahou Shoujo": "Garotas mágicas",
    "Mecha": "Mecha",
    "Music": "Música",
    "Mystery": "Mistério",
    "Psychological": "Psicológico",
    "Romance": "Romance",
    "Sci-Fi": "Ficção científica",
    "Slice of Life": "Cotidiano",
    "Sports": "Esportes",
    "Supernatural": "Sobrenatural",
    "Thriller": "Suspense",
}

LANGUAGE_PT = {
    "por": "Português",
    "pt": "Português",
    "pt-br": "Português",
    "jpn": "Japonês",
    "ja": "Japonês",
    "eng": "Inglês",
    "en": "Inglês",
    "spa": "Espanhol",
    "es": "Espanhol",
    "fra": "Francês",
    "fre": "Francês",
    "fr": "Francês",
    "deu": "Alemão",
    "ger": "Alemão",
    "de": "Alemão",
    "ita": "Italiano",
    "it": "Italiano",
}


class CatalogError(RuntimeError):
    pass


@dataclass(frozen=True)
class AnimeMetadata:
    title: str
    original_title: str | None = None
    year: int | None = None
    episodes: int | None = None
    status: str | None = None
    genres: tuple[str, ...] = ()
    synopsis: str | None = None
    poster: str | None = None
    source: str = "manual"
    source_id: int | None = None
    source_url: str | None = None

    @property
    def label(self) -> str:
        parts = [self.title]
        if self.year:
            parts.append(str(self.year))
        if self.episodes:
            parts.append(f"{self.episodes} eps")
        return " • ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["genres"] = list(self.genres)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AnimeMetadata":
        title = str(payload.get("title") or "").strip()
        if not title:
            raise ValueError("Metadata de anime sem título.")

        def optional_int(value: Any) -> int | None:
            if value in (None, ""):
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        genres_raw = payload.get("genres") or []
        if isinstance(genres_raw, str):
            genres = tuple(part.strip() for part in genres_raw.split(",") if part.strip())
        else:
            genres = tuple(str(item).strip() for item in genres_raw if str(item).strip())

        return cls(
            title=title,
            original_title=_optional_text(payload.get("original_title")),
            year=optional_int(payload.get("year")),
            episodes=optional_int(payload.get("episodes")),
            status=_optional_text(payload.get("status")),
            genres=genres,
            synopsis=_optional_text(payload.get("synopsis")),
            poster=_optional_text(payload.get("poster")),
            source=str(payload.get("source") or "manual"),
            source_id=optional_int(payload.get("source_id")),
            source_url=_optional_text(payload.get("source_url")),
        )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def library_root(target: Path) -> Path:
    current = target.parent if target.is_file() else target
    current = current.resolve()

    while current.parent != current:
        name = current.name.strip().casefold()
        if name in GENERIC_MEDIA_DIRS or SEASON_DIR_RE.fullmatch(current.name.strip()):
            current = current.parent
            continue
        break
    return current


def metadata_path(root: Path) -> Path:
    return Path(root) / METADATA_FILENAME


def guess_search_term(root: Path) -> str:
    value = root.name
    value = re.sub(r"\[[^\]]+\]", " ", value)
    value = re.sub(r"(?i)\b(?:final|complete|completo|batch|1080p|720p|2160p|4k)\b", " ", value)
    value = re.sub(r"[._]+", " ", value)
    value = re.sub(r"\s*[-–—]+\s*", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or root.name


def load_metadata(root: Path) -> AnimeMetadata | None:
    path = metadata_path(root)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        anime_payload = payload.get("anime") if isinstance(payload, dict) else None
        if not isinstance(anime_payload, dict):
            return None
        return AnimeMetadata.from_dict(anime_payload)
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return None


def save_metadata(root: Path, anime: AnimeMetadata) -> Path:
    path = metadata_path(root)
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                existing = raw
        except (OSError, json.JSONDecodeError):
            existing = {}

    existing["version"] = 1
    existing["anime"] = anime.to_dict()
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    return path


def _clean_description(value: str | None) -> str | None:
    if not value:
        return None
    text = html.unescape(value)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\[(.*?)\]\([^)]*\)", r"\1", text)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip() or None


def _metadata_from_anilist(payload: dict[str, Any]) -> AnimeMetadata:
    titles = payload.get("title") or {}
    display = titles.get("english") or titles.get("romaji") or titles.get("native") or "Anime"
    native = titles.get("native")
    original = native if native and native != display else titles.get("romaji")
    if original == display:
        original = None

    start = payload.get("startDate") or {}
    source_id = payload.get("id")
    poster = (payload.get("coverImage") or {}).get("extraLarge") or (payload.get("coverImage") or {}).get("large")
    source_url = f"https://anilist.co/anime/{source_id}" if source_id else None

    return AnimeMetadata(
        title=str(display).strip(),
        original_title=_optional_text(original),
        year=int(start["year"]) if start.get("year") else None,
        episodes=int(payload["episodes"]) if payload.get("episodes") else None,
        status=_optional_text(payload.get("status")),
        genres=tuple(str(item) for item in (payload.get("genres") or []) if item),
        synopsis=_clean_description(payload.get("description")),
        poster=_optional_text(poster),
        source="anilist",
        source_id=int(source_id) if source_id is not None else None,
        source_url=source_url,
    )


def search_anilist(search: str, limit: int = 5) -> list[AnimeMetadata]:
    query = """
    query ($search: String!, $perPage: Int!) {
      Page(page: 1, perPage: $perPage) {
        media(type: ANIME, search: $search) {
          id
          title { romaji english native }
          description(asHtml: false)
          startDate { year month day }
          episodes
          status
          genres
          coverImage { extraLarge large }
        }
      }
    }
    """
    body = json.dumps(
        {"query": query, "variables": {"search": search, "perPage": max(1, min(limit, 10))}}
    ).encode("utf-8")
    request = urllib.request.Request(
        ANILIST_ENDPOINT,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "tg-upload/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        retry = exc.headers.get("Retry-After") if exc.headers else None
        suffix = f" Tente novamente em {retry}s." if retry else ""
        raise CatalogError(f"AniList respondeu HTTP {exc.code}.{suffix}") from exc
    except urllib.error.URLError as exc:
        raise CatalogError(f"Não foi possível acessar o AniList: {exc.reason}") from exc
    except (OSError, TimeoutError, json.JSONDecodeError) as exc:
        raise CatalogError(f"Falha ao consultar o AniList: {exc}") from exc

    if payload.get("errors"):
        message = str((payload["errors"][0] or {}).get("message") or "erro desconhecido")
        raise CatalogError(f"AniList: {message}")

    media = (((payload.get("data") or {}).get("Page") or {}).get("media") or [])
    return [_metadata_from_anilist(item) for item in media if isinstance(item, dict)]


def status_display(status: str | None) -> str | None:
    if not status:
        return None
    return STATUS_PT.get(status.strip().upper(), status.strip())


def genre_display(genre: str) -> str:
    return GENRE_PT.get(genre, genre)


def language_display(code: str | None, title: str | None = None) -> str | None:
    if code:
        value = LANGUAGE_PT.get(code.strip().casefold())
        if value:
            return value
    return _optional_text(title) or _optional_text(code)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[: max(0, limit - 1)].rstrip()
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" .,:;-") + "…"


def format_intro(
    anime: AnimeMetadata,
    *,
    quality: str | None = None,
    audio_labels: tuple[str, ...] = (),
    max_length: int = 1000,
) -> str:
    lines = [f"🎬 {anime.title}"]
    if anime.original_title and anime.original_title.casefold() != anime.title.casefold():
        lines.append(f"🇯🇵 {anime.original_title}")
    lines.append("")

    facts: list[str] = []
    if anime.year:
        facts.append(f"📅 Ano: {anime.year}")
    if anime.episodes:
        facts.append(f"📺 Episódios: {anime.episodes}")
    status = status_display(anime.status)
    if status:
        facts.append(f"✅ Status: {status}")
    if anime.genres:
        genres = " • ".join(genre_display(item) for item in anime.genres)
        facts.append(f"🎭 Gêneros: {genres}")
    if audio_labels:
        facts.append(f"🔊 Áudio: {' • '.join(audio_labels)}")
    if quality:
        facts.append(f"🖥️ Qualidade: {quality}")
    lines.extend(facts)

    base = "\n".join(lines).rstrip()
    if not anime.synopsis:
        return _truncate(base, max_length)

    prefix = base + "\n\n📝 Sinopse:\n"
    remaining = max(80, max_length - len(prefix))
    return prefix + _truncate(anime.synopsis, remaining)


def resolve_poster(anime: AnimeMetadata, root: Path) -> tuple[Path | None, tempfile.TemporaryDirectory | None]:
    if not anime.poster:
        return None, None

    poster = anime.poster.strip()
    parsed = urllib.parse.urlparse(poster)
    if parsed.scheme in {"http", "https"}:
        tempdir = tempfile.TemporaryDirectory(prefix="tg-upload-poster-")
        suffix = Path(parsed.path).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            suffix = ".jpg"
        target = Path(tempdir.name) / f"poster{suffix}"
        request = urllib.request.Request(poster, headers={"User-Agent": "tg-upload/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response, target.open("wb") as handle:
                handle.write(response.read())
            if target.stat().st_size == 0:
                raise OSError("poster vazio")
            return target, tempdir
        except Exception:
            tempdir.cleanup()
            return None, None

    candidate = Path(poster).expanduser()
    if not candidate.is_absolute():
        candidate = Path(root) / candidate
    return (candidate if candidate.is_file() else None), None

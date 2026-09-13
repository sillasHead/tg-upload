from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache

# O Telethon se reconecta sozinho em quedas transitórias. Esses logs podem aparecer
# no meio dos menus do InquirerPy e corromper visualmente a interface. Exceções reais
# das operações continuam sendo tratadas e exibidas pelo próprio tg-upload.
for logger_name in (
    "telethon",
    "telethon.network",
    "telethon.network.connection",
    "telethon.network.mtprotosender",
):
    logging.getLogger(logger_name).setLevel(logging.CRITICAL)

import anime_catalog
import media_catalog


_ORIGINAL_SEARCH_TMDB = media_catalog.search_tmdb


def _clean_search_query(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\[[^\]]+\]", " ", text)
    text = re.sub(r"(?i)\b(?:19|20)\d{2}\b", " ", text)
    text = re.sub(r"(?i)\b(?:complete|completo|final|batch|1080p|720p|2160p|4k|8k)\b", " ", text)
    text = re.sub(r"[._]+", " ", text)
    text = re.sub(r"\s*[-–—|]+\s*", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


@lru_cache(maxsize=64)
def _translate_query_en(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return text

    params = urllib.parse.urlencode(
        {
            "client": "gtx",
            "sl": "auto",
            "tl": "en",
            "dt": "t",
            "q": text,
        }
    )
    request = urllib.request.Request(
        f"{anime_catalog.GOOGLE_TRANSLATE_ENDPOINT}?{params}",
        headers={"User-Agent": "tg-upload/1.0"},
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        segments = payload[0] if isinstance(payload, list) and payload else []
        translated = "".join(
            str(segment[0])
            for segment in segments
            if isinstance(segment, list) and segment and segment[0]
        ).strip()
        return translated or text
    except (
        OSError,
        TimeoutError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
        urllib.error.URLError,
    ):
        return text


def _query_variants(search: str) -> list[str]:
    original = _clean_search_query(search) or str(search or "").strip()
    variants: list[str] = []

    def add(value: str) -> None:
        value = _clean_search_query(value)
        if not value:
            return
        folded = value.casefold()
        if any(existing.casefold() == folded for existing in variants):
            return
        variants.append(value)

    add(original)

    translated = _translate_query_en(original)
    add(translated)

    # Se um título localizado não estiver indexado na busca do TMDB, uma forma
    # abreviada costuma encontrar a franquia/obra correta para o usuário escolher.
    words = original.split()
    if len(words) >= 3:
        add(" ".join(words[: max(2, len(words) - 1)]))
        add(" ".join(words[:2]))

    translated_words = _clean_search_query(translated).split()
    if len(translated_words) >= 3:
        add(" ".join(translated_words[: max(2, len(translated_words) - 1)]))

    return variants


def _search_tmdb_resilient(
    search: str,
    kind: str,
    credential: str,
    limit: int = 5,
):
    wanted = max(1, min(int(limit), 10))
    collected = []
    seen_ids: set[int] = set()
    last_error: Exception | None = None

    for query in _query_variants(search):
        try:
            results = _ORIGINAL_SEARCH_TMDB(
                query,
                kind,
                credential,
                limit=max(wanted, 8),
            )
        except (media_catalog.CatalogError, anime_catalog.CatalogError) as exc:
            last_error = exc
            continue

        for item in results:
            source_id = getattr(item, "source_id", None)
            if source_id is not None and int(source_id) in seen_ids:
                continue
            if source_id is not None:
                seen_ids.add(int(source_id))
            collected.append(item)

        # Uma consulta que já trouxe resultados bons é suficiente. Só usamos as
        # variantes como fallback quando a busca localizada falha ou traz pouco.
        if len(collected) >= wanted:
            break

    if collected:
        return collected[:wanted]
    if last_error is not None:
        raise last_error
    return []


# search_catalog() consulta o nome global search_tmdb no módulo em tempo de execução,
# então esta substituição melhora séries/desenhos/filmes sem duplicar o catálogo.
media_catalog.search_tmdb = _search_tmdb_resilient

import entrypoint


if __name__ == "__main__":
    raise SystemExit(entrypoint.main())

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

import anime_catalog
import media_catalog
import upload


_LIBRARY_LAYOUT = None
_CATALOG_ENRICHMENT = None
_ENTRYPOINT = None
_ORIGINAL_SEASON_HEADER = None

# AniList usa alguns títulos estilizados como "Parasyte -the maxim-". O separador
# abaixo considera um hífen precedido por espaço como separador de subtítulo mesmo
# quando não existe espaço depois dele, sem quebrar nomes normais como Spider-Man.
SUBTITLE_SEPARATOR_RE = re.compile(r"\s+(?:-|–|—)\s*|:\s+")
DECORATIVE_SUBTITLE_RE = re.compile(r"^(.+?)\s+[-–—]\s*(.+?)[-–—]\s*$")


def _normalized(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def generate_search_tag(title: str) -> str:
    """Gera a tag canônica sem carregar subtítulos decorativos da obra."""
    layout = _LIBRARY_LAYOUT
    if layout is None:
        return "Media"

    text = str(title or "").strip()
    if not text:
        return "Media"

    primary = SUBTITLE_SEPARATOR_RE.split(text, maxsplit=1)[0].strip()
    primary_words = layout._ascii_words(primary)
    pretty_primary = "_".join(layout._tag_word(word) for word in primary_words)
    if primary != text and primary_words and len(pretty_primary) <= 32:
        return layout.normalize_search_tag(pretty_primary)

    words = layout._ascii_words(text)
    if not words:
        return "Media"

    pretty_full = "_".join(layout._tag_word(word) for word in words)
    if len(pretty_full) <= 32 and len(words) <= 5:
        return layout.normalize_search_tag(pretty_full)

    meaningful = [
        word
        for word in words
        if word.casefold() not in layout.LONG_TITLE_STOPWORDS
    ]
    chosen = (meaningful or words)[:2]
    return layout.normalize_search_tag(
        "_".join(layout._tag_word(word) for word in chosen)
    )


def _display_title(value: str) -> str:
    """Remove apenas hífens decorativos de subtítulo; não renomeia a obra."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    match = DECORATIVE_SUBTITLE_RE.match(text)
    if not match:
        return text
    left, right = match.groups()
    return f"{left.strip()} - {right.strip()}"


def season_header_text(library: str, season: int) -> str:
    layout = _LIBRARY_LAYOUT
    if layout is None or _ORIGINAL_SEASON_HEADER is None:
        return f"📺 #S{season:02d} — TEMPORADA {season}"

    context = layout._CONTEXT
    if context.include_search_tag and context.search_tag:
        title = (
            context.metadata.title
            if context.metadata is not None and context.metadata.title
            else library
        )
        title = _display_title(title)
        return f"📺 {title.upper()} — TEMPORADA {season}\n#{context.search_tag}"
    return _ORIGINAL_SEASON_HEADER(library, season)


def _metadata_root(target: Path) -> Path:
    # Para um arquivo dentro de ...\Obra\mkv\episodio.mkv, o root deve ser Obra,
    # exatamente como já acontece quando o usuário passa a pasta inteira.
    return anime_catalog.library_root(Path(target))


def _tmdb_credential() -> str | None:
    if _ENTRYPOINT is None:
        return None
    config = upload.load_json(upload.CONFIG_PATH, {})
    try:
        value = _ENTRYPOINT._tmdb_credential(config)
    except Exception:
        return None
    return str(value).strip() if value else None


def _candidate_score(
    candidate: anime_catalog.AnimeMetadata,
    metadata: anime_catalog.AnimeMetadata,
) -> int:
    wanted = {
        value
        for value in (
            _normalized(metadata.title),
            _normalized(metadata.original_title),
        )
        if value
    }
    available = {
        value
        for value in (
            _normalized(candidate.title),
            _normalized(candidate.original_title),
        )
        if value
    }

    score = 0
    if wanted & available:
        score += 120
    elif any(
        left and right and (left in right or right in left)
        for left in wanted
        for right in available
    ):
        score += 70
    else:
        wanted_tokens = set(" ".join(wanted).split())
        available_tokens = set(" ".join(available).split())
        if wanted_tokens and available_tokens:
            overlap = len(wanted_tokens & available_tokens) / len(
                wanted_tokens | available_tokens
            )
            score += int(overlap * 60)

    if metadata.year and candidate.year:
        if int(metadata.year) == int(candidate.year):
            score += 25
        elif abs(int(metadata.year) - int(candidate.year)) <= 1:
            score += 10
        else:
            score -= 20
    return score


def _find_tmdb_anime(
    metadata: anime_catalog.AnimeMetadata,
) -> anime_catalog.AnimeMetadata | None:
    credential = _tmdb_credential()
    if not credential:
        return None

    candidates: list[anime_catalog.AnimeMetadata] = []
    seen: set[int] = set()
    for query in (metadata.title, metadata.original_title):
        query = str(query or "").strip()
        if not query:
            continue
        try:
            results = media_catalog.search_tmdb(
                query,
                "serie",
                credential,
                limit=10,
            )
        except Exception:
            continue
        for candidate in results:
            source_id = candidate.source_id
            if source_id is None or int(source_id) in seen:
                continue
            seen.add(int(source_id))
            candidates.append(candidate)

    if not candidates:
        return None
    ranked = sorted(
        candidates,
        key=lambda item: _candidate_score(item, metadata),
        reverse=True,
    )
    best = ranked[0]
    return best if _candidate_score(best, metadata) >= 70 else None


def _remap_single_anime_season(
    titles: dict[str, str],
    seasons: set[int],
) -> dict[str, str]:
    """AniList/MAL representam cada entrada como uma série própria.

    Se o diretório local usa S02 para uma entrada que no MAL começa em episódio 1,
    remapeia S01Exx para a única temporada ativa, sem alterar o cache do provedor.
    """
    if len(seasons) != 1:
        return titles
    season = next(iter(seasons))
    if season == 1:
        return titles
    remapped: dict[str, str] = {}
    for code, title in titles.items():
        match = re.fullmatch(r"S01E(\d+)", str(code), flags=re.IGNORECASE)
        if match:
            remapped[f"S{season:02d}E{int(match.group(1)):02d}"] = title
        else:
            remapped[str(code)] = title
    return remapped


def _cache_covers_seasons(titles: dict[str, str], seasons: set[int]) -> bool:
    return all(
        any(code.startswith(f"S{season:02d}E") for code in titles)
        for season in seasons
    )


def _active_layout():
    enrichment = _CATALOG_ENRICHMENT
    if enrichment is not None:
        candidate = getattr(enrichment, "_LIBRARY_LAYOUT", None)
        if candidate is not None:
            return candidate
    return _LIBRARY_LAYOUT


def _load_episode_titles() -> None:
    """Carrega nomes de episódios com retry e fallback TMDB para animes."""
    enrichment = _CATALOG_ENRICHMENT
    layout = _active_layout()
    if enrichment is None or layout is None:
        return

    context = layout._CONTEXT
    root = context.root
    metadata = context.metadata
    if (
        root is None
        or metadata is None
        or context.kind not in {"anime", "desenho", "serie"}
    ):
        enrichment._EPISODE_TITLES = {}
        enrichment._CONTEXT_KEY = None
        return

    seasons = enrichment._active_seasons()
    key = (
        str(root),
        context.kind,
        metadata.source,
        metadata.source_id,
        tuple(sorted(seasons)),
    )
    if key == enrichment._CONTEXT_KEY and enrichment._EPISODE_TITLES:
        return

    # Não marca a chave como concluída antes de termos títulos. Assim uma falha
    # transitória de rede na primeira passagem pode ser tentada novamente.
    enrichment._EPISODE_TITLES = {}
    enrichment._CONTEXT_KEY = None

    if context.kind == "anime" and metadata.source == "anilist":
        profile = enrichment._profile(root)
        raw_mal = profile.get("mal_id")
        try:
            mal_id = int(raw_mal) if raw_mal is not None else None
        except (TypeError, ValueError):
            mal_id = None

        if mal_id is None:
            try:
                mal_id = enrichment._resolve_anilist_mal_id(metadata)
            except RuntimeError as exc:
                enrichment._warn_once(
                    "anilist-mal",
                    f"Aviso: AniList não forneceu o vínculo de episódios ({exc}).",
                )
            if mal_id is not None:
                try:
                    enrichment._save_profile(root, {"mal_id": mal_id})
                except OSError:
                    pass

        if mal_id is not None:
            cached = enrichment._cached_titles(root, "jikan", mal_id)
            if cached:
                enrichment._EPISODE_TITLES = _remap_single_anime_season(
                    cached, seasons
                )
                enrichment._CONTEXT_KEY = key
                return
            try:
                titles = enrichment._jikan_episode_titles(mal_id)
            except RuntimeError as exc:
                enrichment._warn_once(
                    "jikan",
                    f"Aviso: Jikan não respondeu com os nomes dos episódios ({exc}).",
                )
                titles = {}
            if titles:
                try:
                    enrichment._save_titles(root, "jikan", mal_id, titles)
                except OSError:
                    pass
                enrichment._EPISODE_TITLES = _remap_single_anime_season(
                    titles, seasons
                )
                enrichment._CONTEXT_KEY = key
                print(
                    f"Títulos de episódios: {len(enrichment._EPISODE_TITLES)} "
                    "carregados do catálogo."
                )
                return

        # Fallback: o usuário já pode ter TMDB configurado para séries/desenhos.
        # Isso também costuma oferecer títulos pt-BR quando existem no catálogo.
        profile = enrichment._profile(root)
        raw_tmdb = profile.get("anime_tmdb_id")
        try:
            tmdb_id = int(raw_tmdb) if raw_tmdb is not None else None
        except (TypeError, ValueError):
            tmdb_id = None

        tmdb_metadata = None
        if tmdb_id is not None:
            tmdb_metadata = anime_catalog.AnimeMetadata(
                title=metadata.title,
                original_title=metadata.original_title,
                year=metadata.year,
                source="tmdb",
                source_id=tmdb_id,
            )
        else:
            tmdb_metadata = _find_tmdb_anime(metadata)
            if tmdb_metadata is not None and tmdb_metadata.source_id is not None:
                tmdb_id = int(tmdb_metadata.source_id)
                try:
                    enrichment._save_profile(root, {"anime_tmdb_id": tmdb_id})
                except OSError:
                    pass

        if tmdb_metadata is not None and tmdb_id is not None:
            cached = enrichment._cached_titles(root, "tmdb-anime", tmdb_id)
            if cached and _cache_covers_seasons(cached, seasons):
                enrichment._EPISODE_TITLES = cached
                enrichment._CONTEXT_KEY = key
                return
            fetched = enrichment._tmdb_season_titles(tmdb_metadata, seasons)
            if fetched:
                enrichment._EPISODE_TITLES = fetched
                enrichment._CONTEXT_KEY = key
                try:
                    enrichment._save_titles(
                        root,
                        "tmdb-anime",
                        tmdb_id,
                        fetched,
                    )
                except OSError:
                    pass
                print(
                    f"Títulos de episódios: {len(fetched)} carregados do TMDB."
                )
                return

        enrichment._warn_once(
            f"episodes:{root}",
            "Aviso: não foi possível obter nomes reais dos episódios; "
            "as legendas serão mantidas sem inventar títulos.",
        )
        return

    # Séries/desenhos continuam usando a implementação existente, mas sem a chave
    # prematuramente marcada: ela será preenchida somente se títulos forem obtidos.
    if (
        context.kind in {"desenho", "serie"}
        and metadata.source == "tmdb"
        and metadata.source_id is not None
    ):
        catalog_id = int(metadata.source_id)
        cached = enrichment._cached_titles(root, "tmdb", catalog_id)
        if cached and _cache_covers_seasons(cached, seasons):
            enrichment._EPISODE_TITLES = cached
            enrichment._CONTEXT_KEY = key
            return

        missing = {
            season
            for season in seasons
            if not any(code.startswith(f"S{season:02d}E") for code in cached)
        }
        fetched = enrichment._tmdb_season_titles(metadata, missing)
        merged = {**cached, **fetched}
        if merged:
            enrichment._EPISODE_TITLES = merged
            enrichment._CONTEXT_KEY = key
            if fetched:
                try:
                    enrichment._save_titles(root, "tmdb", catalog_id, merged)
                except OSError:
                    pass
                print(
                    f"Títulos de episódios: {len(merged)} carregados do catálogo."
                )


def _migrate_legacy_search_tag() -> None:
    """Troca apenas tags antigas que são claramente o título completo da obra."""
    enrichment = _CATALOG_ENRICHMENT
    layout = _active_layout()
    if layout is None or enrichment is None:
        return

    context = layout._CONTEXT
    if context.root is None or context.metadata is None or not context.search_tag:
        return

    launcher = layout._launcher()
    args = getattr(launcher, "_ACTIVE_ARGS", None)
    if str(getattr(args, "search_tag", "") or "").strip():
        # Nunca sobrescreve uma tag explicitamente escolhida pelo usuário.
        return

    canonical = layout.generate_search_tag(context.metadata.title)
    current = str(context.search_tag).strip()
    if current.casefold() == canonical.casefold():
        if current != canonical:
            try:
                layout._save_library_profile(context.root, canonical)
            except OSError:
                return
            context.search_tag = canonical
        return

    # A forma antiga era simplesmente o título inteiro normalizado. Fazemos a
    # comparação sem diferenciar maiúsculas/minúsculas para também migrar
    # "Parasyte_The_Maxim" quando o AniList fornece "Parasyte -the maxim-".
    try:
        full_title = layout.normalize_search_tag(context.metadata.title)
    except ValueError:
        full_title = ""
    if full_title and current.casefold() == full_title.casefold():
        try:
            layout._save_library_profile(context.root, canonical)
        except OSError:
            return
        context.search_tag = canonical
        print(f"Tag de busca ajustada: #{canonical}")
        return

    # Compatibilidade com versões que capitalizavam cada palavra antes de salvar.
    if hasattr(layout, "_ascii_words") and hasattr(layout, "_tag_word"):
        words = layout._ascii_words(context.metadata.title)
        if words:
            pretty_full = "_".join(layout._tag_word(word) for word in words)
            try:
                pretty_full = layout.normalize_search_tag(pretty_full)
            except ValueError:
                pretty_full = ""
            if pretty_full and current.casefold() == pretty_full.casefold():
                try:
                    layout._save_library_profile(context.root, canonical)
                except OSError:
                    return
                context.search_tag = canonical
                print(f"Tag de busca ajustada: #{canonical}")


def install(entrypoint_module, catalog_enrichment_module, library_layout_module) -> None:
    global _ENTRYPOINT, _CATALOG_ENRICHMENT, _LIBRARY_LAYOUT, _ORIGINAL_SEASON_HEADER

    _ENTRYPOINT = entrypoint_module
    _CATALOG_ENRICHMENT = catalog_enrichment_module
    _LIBRARY_LAYOUT = library_layout_module
    _ORIGINAL_SEASON_HEADER = library_layout_module.season_header_text

    # Corrige os sintomas vistos na biblioteca: tag longa de títulos estilizados,
    # cabeçalho decorativo e ausência de nome real quando o arquivo só repete a obra.
    library_layout_module.generate_search_tag = generate_search_tag
    library_layout_module.season_header_text = season_header_text
    catalog_enrichment_module._load_episode_titles = _load_episode_titles
    catalog_enrichment_module._migrate_legacy_search_tag = _migrate_legacy_search_tag
    catalog_enrichment_module._CONTEXT_KEY = None
    entrypoint_module._metadata_root = _metadata_root

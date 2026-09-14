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


# Teste opt-in: mantém o MKV original byte por byte, mas o envia como vídeo com
# supports_streaming + DocumentAttributeVideo + thumbnail JPEG. O comportamento
# padrão de MKV como documento continua inalterado quando a flag não é usada.
_ORIGINAL_RUNTIME_BUILD_PARSER = entrypoint.launcher._build_parser
_ORIGINAL_RUNTIME_SUPPORTS_STREAMING = entrypoint.launcher._supports_streaming
_ORIGINAL_RUNTIME_SEND_MEDIA = entrypoint.launcher._send_media


def _build_parser_with_mkv_video_test():
    parser = _ORIGINAL_RUNTIME_BUILD_PARSER()
    parser.add_argument(
        "--mkv-video-test",
        action="store_true",
        help=(
            "Teste experimental: envia MKV original como vídeo com metadata e thumbnail, "
            "sem converter nem alterar o arquivo."
        ),
    )
    return parser


def _mkv_video_test_enabled() -> bool:
    args = getattr(entrypoint.launcher, "_ACTIVE_ARGS", None)
    return bool(getattr(args, "mkv_video_test", False))


def _supports_streaming_with_mkv_test(path, as_document: bool) -> bool:
    if (
        not as_document
        and getattr(path, "suffix", str(path)[str(path).rfind(".") :]).casefold() == ".mkv"
        and _mkv_video_test_enabled()
    ):
        return True
    return _ORIGINAL_RUNTIME_SUPPORTS_STREAMING(path, as_document)


async def _send_media_with_mkv_video_test(
    client,
    entity,
    item,
    as_document: bool,
    topic_id: int | None = None,
) -> None:
    if item.path.suffix.casefold() == ".mkv" and _mkv_video_test_enabled() and not as_document:
        print("MKV teste: original sem conversão • vídeo/streaming • thumbnail explícita")
        # Bypassa somente a regra do entrypoint que força MKV a documento. A rotina
        # base continua fazendo todo o resto (retry, workers, estado e progress).
        await entrypoint._ORIGINAL_SEND_MEDIA(
            client,
            entity,
            item,
            False,
            topic_id,
        )
        return

    await _ORIGINAL_RUNTIME_SEND_MEDIA(
        client,
        entity,
        item,
        as_document,
        topic_id,
    )


entrypoint.launcher._build_parser = _build_parser_with_mkv_video_test
entrypoint.launcher._supports_streaming = _supports_streaming_with_mkv_test
entrypoint.launcher._send_media = _send_media_with_mkv_video_test


def _media_attributes_preserving_telethon(path, as_document: bool):
    """Mantém os atributos completos que o Telethon extrai do MP4.

    O launcher antigo removia DocumentAttributeVideo e recriava um atributo mínimo
    via ffprobe. Isso descartava flags/campos que o Telegram usa no tratamento do
    vídeo. Só recorremos ao ffprobe quando o Telethon realmente não conseguiu criar
    um atributo de vídeo.
    """
    launcher = entrypoint.launcher
    supports_streaming = launcher._supports_streaming(path, as_document)
    attributes, mime_type = launcher.upload.utils.get_attributes(
        str(path),
        force_document=as_document,
        supports_streaming=supports_streaming,
    )

    if as_document:
        return attributes, mime_type, supports_streaming

    if any(isinstance(attribute, launcher.types.DocumentAttributeVideo) for attribute in attributes):
        return attributes, mime_type, supports_streaming

    metadata = launcher._ffprobe_video(path)
    if metadata:
        attributes = list(attributes)
        attributes.append(
            launcher.types.DocumentAttributeVideo(
                duration=metadata["duration"],
                w=metadata["width"],
                h=metadata["height"],
                round_message=False,
                supports_streaming=supports_streaming,
            )
        )

    return attributes, mime_type, supports_streaming


async def _send_compatible_native(
    client,
    entity,
    item,
    as_document: bool,
    topic_id: int | None,
    reporter,
) -> None:
    # No modo de 1 worker passamos o caminho diretamente ao Telethon e deixamos
    # send_file extrair MIME e DocumentAttributeVideo sozinho, como no fluxo nativo.
    # Isso evita sobrescrever metadata de vídeo válida com atributos incompletos.
    supports_streaming = entrypoint.launcher._supports_streaming(item.path, as_document)
    await client.send_file(
        entity,
        str(item.path),
        caption=item.caption,
        force_document=as_document,
        supports_streaming=supports_streaming,
        reply_to=topic_id,
        progress_callback=reporter,
    )


# Mantemos estes fallbacks históricos instalados primeiro. O módulo telegram_video
# abaixo os substitui pela embalagem de vídeo baseada no comportamento dos clientes
# oficiais (metadata explícita via ffprobe + thumbnail JPEG).
entrypoint.launcher._media_attributes = _media_attributes_preserving_telethon
entrypoint.launcher._send_compatible = _send_compatible_native

import telegram_video

telegram_video.install(entrypoint.launcher)


def main() -> int:
    special = entrypoint._catalog_special_command()
    if special is not None:
        return special
    return entrypoint.launcher.main()


if __name__ == "__main__":
    raise SystemExit(main())

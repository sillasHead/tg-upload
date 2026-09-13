from __future__ import annotations

from pathlib import Path

import launcher


# Política padrão de formatos:
# - MP4/M4V/MOV: vídeo reproduzível/streamable quando o Telegram suportar.
# - MKV: preserva o arquivo original e envia como documento.
# O antigo playback-fix continua disponível apenas quando solicitado explicitamente.
launcher.DEFAULT_PLAYBACK_FIX = "off"
launcher._ACTIVE_PLAYBACK_FIX = "off"
launcher.STREAMABLE_EXTENSIONS = {".mp4", ".m4v", ".mov"}

_ORIGINAL_BUILD_PARSER = launcher._build_parser
_ORIGINAL_SEND_MEDIA = launcher._send_media


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


launcher._build_parser = _build_parser
launcher._supports_streaming = _supports_streaming
launcher._send_media = _send_media


if __name__ == "__main__":
    raise SystemExit(launcher.main())

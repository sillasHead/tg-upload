from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


_LAUNCHER = None
_STREAMABLE_VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov"}


def _launcher():
    if _LAUNCHER is None:
        raise RuntimeError("telegram_video.install() precisa ser chamado antes do upload.")
    return _LAUNCHER


def _probe_video(path: Path) -> dict[str, Any] | None:
    """Lê a metadata que será enviada ao Telegram usando ffprobe.

    Não dependemos do hachoir para o card do vídeo porque alguns MP4 válidos
    acabam recebendo duration/dimensões incompletas em clientes Web. O ffprobe é
    também o mesmo analisador que já usamos em outras rotas do projeto.
    """
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
        "stream=width,height,codec_name,duration:format=duration",
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
        duration = float(duration_raw)
        if width <= 0 or height <= 0 or duration <= 0:
            return None

        return {
            "width": width,
            "height": height,
            "duration": duration,
            "codec": str(stream.get("codec_name") or "").strip().casefold() or None,
        }
    except (
        OSError,
        subprocess.SubprocessError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ):
        return None


def _mkv_video_test_enabled() -> bool:
    launcher = _launcher()
    args = getattr(launcher, "_ACTIVE_ARGS", None)
    return bool(getattr(args, "mkv_video_test", False))


def _is_streamable_video(path: Path, as_document: bool) -> bool:
    if as_document:
        return False
    suffix = path.suffix.casefold()
    if suffix == ".mkv":
        return _mkv_video_test_enabled()
    return suffix in _STREAMABLE_VIDEO_EXTENSIONS


def _media_attributes(path: Path, as_document: bool):
    """Cria os mesmos campos essenciais que um cliente oficial envia.

    Mantemos filename/MIME inferidos pelo Telethon, mas para vídeo streamable
    substituímos DocumentAttributeVideo por valores confiáveis do ffprobe.
    """
    launcher = _launcher()
    supports_streaming = launcher._supports_streaming(path, as_document)
    attributes, mime_type = launcher.upload.utils.get_attributes(
        str(path),
        force_document=as_document,
        supports_streaming=supports_streaming,
    )

    if as_document or not _is_streamable_video(path, as_document):
        return attributes, mime_type, supports_streaming

    metadata = _probe_video(path)
    if metadata is None:
        return attributes, mime_type, supports_streaming

    attributes = [
        attribute
        for attribute in attributes
        if not isinstance(attribute, launcher.types.DocumentAttributeVideo)
    ]
    attributes.append(
        launcher.types.DocumentAttributeVideo(
            duration=metadata["duration"],
            w=metadata["width"],
            h=metadata["height"],
            round_message=False,
            supports_streaming=True,
        )
    )

    if path.suffix.casefold() == ".mp4":
        mime_type = "video/mp4"

    return attributes, mime_type, True


def _render_thumbnail(ffmpeg: str, source: Path, output: Path, seek: float, side: int, quality: int) -> bool:
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{seek:.3f}",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-frames:v",
        "1",
        "-vf",
        f"scale={side}:{side}:force_original_aspect_ratio=decrease",
        "-q:v",
        str(quality),
        str(output),
    ]
    try:
        subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        return output.is_file() and output.stat().st_size > 0
    except (OSError, subprocess.SubprocessError):
        return False


@contextmanager
def _video_thumbnail(path: Path, as_document: bool) -> Iterator[Path | None]:
    """Gera um JPEG pequeno para o campo `thumb` de InputMediaUploadedDocument.

    Telegram Desktop prepara thumbnails com lado máximo de 320 px. A documentação
    do Telethon recomenda JPEG <= 320x320 e, na prática, abaixo de ~20 KiB. Fazemos
    algumas tentativas rápidas sem tocar no vídeo original.
    """
    if not _is_streamable_video(path, as_document):
        yield None
        return

    metadata = _probe_video(path)
    ffmpeg = shutil.which("ffmpeg")
    if metadata is None or not ffmpeg:
        yield None
        return

    # Evita o primeiro frame preto/transition: usa até 5% do vídeo, limitado a 15 s.
    seek = min(max(metadata["duration"] * 0.05, 1.0), 15.0)

    with tempfile.TemporaryDirectory(prefix="tg-upload-thumb-") as temp_dir:
        output = Path(temp_dir) / "thumb.jpg"
        attempts = (
            (320, 7),
            (320, 12),
            (280, 14),
            (240, 16),
        )

        created = False
        for side, quality in attempts:
            output.unlink(missing_ok=True)
            if not _render_thumbnail(ffmpeg, path, output, seek, side, quality):
                continue
            created = True
            if output.stat().st_size <= 20 * 1024:
                break

        if not created:
            yield None
            return

        yield output


def _verify_video_message(message, expected_streaming: bool) -> None:
    if not expected_streaming or message is None:
        return

    launcher = _launcher()
    media = getattr(message, "media", None)
    document = getattr(media, "document", None)
    if document is None:
        print("Aviso: Telegram não devolveu um documento de vídeo para verificação.")
        return

    video = next(
        (
            attribute
            for attribute in (getattr(document, "attributes", None) or [])
            if isinstance(attribute, launcher.types.DocumentAttributeVideo)
        ),
        None,
    )
    thumbs = getattr(document, "thumbs", None) or []

    if video is None:
        print("Aviso: Telegram não registrou DocumentAttributeVideo no arquivo enviado.")
        return

    try:
        duration = float(video.duration)
    except (TypeError, ValueError):
        duration = 0.0

    print(
        "Telegram vídeo: "
        f"{int(getattr(video, 'w', 0) or 0)}x{int(getattr(video, 'h', 0) or 0)} • "
        f"{duration:.3f}s • "
        f"streaming={'sim' if bool(getattr(video, 'supports_streaming', False)) else 'não'} • "
        f"thumbnail={'sim' if thumbs else 'não'}"
    )


async def _send_compatible(client, entity, item, as_document: bool, topic_id: int | None, reporter) -> None:
    attributes, mime_type, supports_streaming = _media_attributes(item.path, as_document)

    with _video_thumbnail(item.path, as_document) as thumb:
        message = await client.send_file(
            entity,
            str(item.path),
            caption=item.caption,
            force_document=as_document,
            supports_streaming=supports_streaming,
            attributes=attributes,
            mime_type=mime_type,
            thumb=str(thumb) if thumb is not None else None,
            reply_to=topic_id,
            progress_callback=reporter,
        )

    _verify_video_message(message, supports_streaming)


async def _send_fast(client, entity, item, as_document: bool, topic_id: int | None, reporter) -> None:
    launcher = _launcher()
    attributes, mime_type, supports_streaming = _media_attributes(item.path, as_document)

    # Prepara o thumbnail antes do upload grande; se ffmpeg/ffprobe não estiverem
    # disponíveis, o upload continua com a compatibilidade antiga como fallback.
    with _video_thumbnail(item.path, as_document) as thumb:
        uploaded_file = await launcher.fast_upload.upload_file_parallel(
            client,
            item.path,
            workers=launcher._ACTIVE_UPLOAD_WORKERS,
            progress_callback=reporter,
        )
        print()

        message = await client.send_file(
            entity,
            uploaded_file,
            caption=item.caption,
            force_document=as_document,
            supports_streaming=supports_streaming,
            attributes=attributes,
            mime_type=mime_type,
            thumb=str(thumb) if thumb is not None else None,
            reply_to=topic_id,
        )

    _verify_video_message(message, supports_streaming)


def install(launcher) -> None:
    global _LAUNCHER
    _LAUNCHER = launcher

    # _send_media resolve estes nomes no módulo launcher em tempo de execução.
    # Assim os modos 1-worker e N-workers passam pela mesma embalagem de vídeo.
    launcher._media_attributes = _media_attributes
    launcher._send_compatible = _send_compatible
    launcher._send_fast = _send_fast

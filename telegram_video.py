from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import library_layout


_LAUNCHER = None
_STREAMABLE_VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".mkv"}


def _launcher():
    if _LAUNCHER is None:
        raise RuntimeError("telegram_video.install() precisa ser chamado antes do upload.")
    return _LAUNCHER


def _probe_video(path: Path) -> dict[str, Any] | None:
    """Lê duração/dimensões confiáveis para o atributo de vídeo do Telegram."""
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


def _is_streamable_video(path: Path, as_document: bool) -> bool:
    return not as_document and path.suffix.casefold() in _STREAMABLE_VIDEO_EXTENSIONS


def _document_filename(item) -> str:
    """Monta o nome exibido no Telegram sem renomear o arquivo local."""
    label = str(item.caption or "").strip().splitlines()[0].strip()
    if not label:
        label = item.path.stem

    # O nome vai no atributo do documento; limpamos apenas caracteres problemáticos
    # para que o arquivo continue amigável também ao ser baixado no Windows.
    label = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " - ", label)
    label = re.sub(r"\s+", " ", label).strip(" .")
    suffix = item.path.suffix
    if suffix and label.casefold().endswith(suffix.casefold()):
        return label
    return f"{label}{suffix}"


def _document_presentation(item, as_document: bool, attributes):
    """Para episódios-documento, concentra tudo no nome e remove a caption duplicada."""
    if not as_document or not item.code:
        return attributes, item.caption

    launcher = _launcher()
    filename = _document_filename(item)
    attributes = [
        attribute
        for attribute in attributes
        if not isinstance(attribute, launcher.types.DocumentAttributeFilename)
    ]
    attributes.append(launcher.types.DocumentAttributeFilename(file_name=filename))
    return attributes, None


def _media_attributes(path: Path, as_document: bool):
    """Envia metadata explícita para o Telegram Web interpretar o vídeo corretamente."""
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


def _render_thumbnail(
    ffmpeg: str,
    source: Path,
    output: Path,
    *,
    side: int,
    quality: int,
    seek: float | None = None,
) -> bool:
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    if seek is not None:
        command.extend(["-ss", f"{seek:.3f}"])
    command.extend(
        [
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
    )
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


def _make_small_jpeg(
    ffmpeg: str,
    source: Path,
    output: Path,
    *,
    seek: float | None,
) -> bool:
    attempts = (
        (320, 7),
        (320, 12),
        (280, 14),
        (240, 16),
    )
    created = False
    for side, quality in attempts:
        output.unlink(missing_ok=True)
        if not _render_thumbnail(
            ffmpeg,
            source,
            output,
            side=side,
            quality=quality,
            seek=seek,
        ):
            continue
        created = True
        if output.stat().st_size <= 20 * 1024:
            break
    return created


@contextmanager
def _video_thumbnail(path: Path, as_document: bool) -> Iterator[Path | None]:
    """Gera a thumbnail do vídeo.

    Prioridade: capa da obra/temporada do catálogo. Se ela não existir, usa um frame
    do próprio vídeo. Assim a biblioteca fica consistente sem perder o fallback que
    corrigiu a reprodução no Telegram Web.
    """
    if not _is_streamable_video(path, as_document):
        yield None
        return

    metadata = _probe_video(path)
    ffmpeg = shutil.which("ffmpeg")
    if metadata is None or not ffmpeg:
        yield None
        return

    with tempfile.TemporaryDirectory(prefix="tg-upload-thumb-") as temp_dir:
        output = Path(temp_dir) / "thumb.jpg"

        cover = library_layout.poster_source(path)
        if cover is not None and _make_small_jpeg(ffmpeg, cover, output, seek=None):
            yield output
            return

        # Fallback: evita primeiro frame preto/transição.
        seek = min(max(metadata["duration"] * 0.05, 1.0), 15.0)
        if _make_small_jpeg(ffmpeg, path, output, seek=seek):
            yield output
            return

        yield None


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
    attributes, caption = _document_presentation(item, as_document, attributes)

    with _video_thumbnail(item.path, as_document) as thumb:
        message = await client.send_file(
            entity,
            str(item.path),
            caption=caption,
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
    attributes, caption = _document_presentation(item, as_document, attributes)

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
            caption=caption,
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

    launcher._media_attributes = _media_attributes
    launcher._send_compatible = _send_compatible
    launcher._send_fast = _send_fast

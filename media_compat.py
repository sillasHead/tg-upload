from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


MAX_TELEGRAM_MKV_AUDIO_TRACKS = 2
SAFE_VIDEO_CODECS = {"h264"}
SAFE_VIDEO_PIXEL_FORMATS = {"yuv420p", "yuvj420p"}
AAC_LC_PROFILES = {"lc", "aac lc"}


@dataclass(frozen=True)
class StreamInfo:
    index: int
    codec_type: str
    codec_name: str
    profile: str | None = None
    pix_fmt: str | None = None
    sample_rate: int | None = None
    language: str | None = None
    title: str | None = None
    is_default: bool = False

    @property
    def label(self) -> str:
        parts = [f"#{self.index}"]
        if self.language:
            parts.append(self.language)
        if self.title:
            parts.append(self.title)
        return " ".join(parts)


@dataclass(frozen=True)
class MediaProbe:
    format_name: str
    video: StreamInfo | None
    audios: tuple[StreamInfo, ...]
    subtitles: tuple[StreamInfo, ...]
    attachments: tuple[StreamInfo, ...]


@dataclass(frozen=True)
class CompatibilityPlan:
    source: Path
    probe: MediaProbe
    selected_audios: tuple[StreamInfo, ...]
    dropped_audios: tuple[StreamInfo, ...]
    transcode_video: bool
    transcode_audio_positions: tuple[int, ...]
    actions: tuple[str, ...]

    @property
    def needs_conversion(self) -> bool:
        return bool(self.actions)


@dataclass
class PreparedMedia:
    path: Path
    changed: bool
    plan: CompatibilityPlan | None = None
    _tempdir: tempfile.TemporaryDirectory | None = field(default=None, repr=False)

    def cleanup(self) -> None:
        if self._tempdir is not None:
            self._tempdir.cleanup()
            self._tempdir = None


def _normalize_language(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().casefold() or None


def _stream_from_payload(payload: dict) -> StreamInfo:
    tags = payload.get("tags") or {}
    disposition = payload.get("disposition") or {}
    sample_rate_raw = payload.get("sample_rate")
    try:
        sample_rate = int(sample_rate_raw) if sample_rate_raw else None
    except (TypeError, ValueError):
        sample_rate = None

    return StreamInfo(
        index=int(payload.get("index", -1)),
        codec_type=str(payload.get("codec_type") or ""),
        codec_name=str(payload.get("codec_name") or "").casefold(),
        profile=str(payload.get("profile")) if payload.get("profile") is not None else None,
        pix_fmt=str(payload.get("pix_fmt")) if payload.get("pix_fmt") is not None else None,
        sample_rate=sample_rate,
        language=_normalize_language(tags.get("language")),
        title=str(tags.get("title")) if tags.get("title") else None,
        is_default=bool(disposition.get("default")),
    )


def probe_media(path: Path) -> MediaProbe:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError(
            "ffprobe não foi encontrado. Instale o FFmpeg ou use --playback-fix off."
        )

    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        (
            "format=format_name:"
            "stream=index,codec_type,codec_name,profile,pix_fmt,sample_rate:"
            "stream_tags=language,title:"
            "stream_disposition=default"
        ),
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
            timeout=30,
        )
        payload = json.loads(result.stdout or "{}")
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"ffprobe falhou ao analisar {path.name}: {message or exc}") from exc
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Não foi possível analisar {path.name} com ffprobe: {exc}") from exc

    streams = tuple(_stream_from_payload(item) for item in (payload.get("streams") or []))
    video = next((stream for stream in streams if stream.codec_type == "video"), None)
    audios = tuple(stream for stream in streams if stream.codec_type == "audio")
    subtitles = tuple(stream for stream in streams if stream.codec_type == "subtitle")
    attachments = tuple(stream for stream in streams if stream.codec_type == "attachment")
    format_name = str((payload.get("format") or {}).get("format_name") or "")
    return MediaProbe(
        format_name=format_name,
        video=video,
        audios=audios,
        subtitles=subtitles,
        attachments=attachments,
    )


def _audio_priority(
    audios: tuple[StreamInfo, ...],
    preferred_languages: tuple[str, ...],
) -> tuple[StreamInfo, ...]:
    if not audios:
        return ()

    normalized = tuple(
        value.strip().casefold()
        for value in preferred_languages
        if value and value.strip()
    )
    if not normalized:
        defaults = [audio for audio in audios if audio.is_default]
        ordered = defaults + [audio for audio in audios if audio not in defaults]
        return tuple(ordered)

    by_language: list[StreamInfo] = []
    used: set[int] = set()
    for language in normalized:
        for audio in audios:
            if audio.index in used:
                continue
            if audio.language == language:
                by_language.append(audio)
                used.add(audio.index)

    defaults = [
        audio
        for audio in audios
        if audio.index not in used and audio.is_default
    ]
    others = [audio for audio in audios if audio.index not in used and not audio.is_default]
    return tuple(by_language + defaults + others)


def _needs_audio_transcode(audio: StreamInfo) -> bool:
    if audio.codec_name != "aac":
        return True
    profile = (audio.profile or "").strip().casefold()
    return profile not in AAC_LC_PROFILES


def build_plan(
    path: Path,
    probe: MediaProbe,
    preferred_languages: tuple[str, ...] = (),
) -> CompatibilityPlan:
    source = Path(path)
    if source.suffix.casefold() != ".mkv" or probe.video is None:
        return CompatibilityPlan(
            source=source,
            probe=probe,
            selected_audios=probe.audios,
            dropped_audios=(),
            transcode_video=False,
            transcode_audio_positions=(),
            actions=(),
        )

    ordered = _audio_priority(probe.audios, preferred_languages)
    selected = tuple(ordered[:MAX_TELEGRAM_MKV_AUDIO_TRACKS])
    selected_ids = {audio.index for audio in selected}
    dropped = tuple(audio for audio in probe.audios if audio.index not in selected_ids)

    video = probe.video
    transcode_video = bool(
        video
        and (
            video.codec_name not in SAFE_VIDEO_CODECS
            or (video.pix_fmt or "").casefold() not in SAFE_VIDEO_PIXEL_FORMATS
        )
    )
    transcode_audio_positions = tuple(
        position
        for position, audio in enumerate(selected)
        if _needs_audio_transcode(audio)
    )

    actions: list[str] = []
    if transcode_video and video:
        profile = f" {video.profile}" if video.profile else ""
        pixel = f"/{video.pix_fmt}" if video.pix_fmt else ""
        actions.append(
            f"vídeo {video.codec_name.upper()}{profile}{pixel} -> H.264 High/yuv420p"
        )
    if dropped:
        actions.append(
            "limitar áudio a 2 faixas; manter "
            + ", ".join(audio.label for audio in selected)
            + "; remover da cópia temporária: "
            + ", ".join(audio.label for audio in dropped)
        )
    for position in transcode_audio_positions:
        audio = selected[position]
        profile = f" {audio.profile}" if audio.profile else ""
        actions.append(
            f"áudio {audio.label}: {audio.codec_name.upper()}{profile} -> AAC-LC 48 kHz"
        )

    return CompatibilityPlan(
        source=source,
        probe=probe,
        selected_audios=selected,
        dropped_audios=dropped,
        transcode_video=transcode_video,
        transcode_audio_positions=transcode_audio_positions,
        actions=tuple(actions),
    )


def analyze_for_telegram(
    path: Path,
    preferred_languages: tuple[str, ...] = (),
) -> CompatibilityPlan | None:
    source = Path(path)
    if source.suffix.casefold() != ".mkv":
        return None
    probe = probe_media(source)
    return build_plan(source, probe, preferred_languages)


def _compact_error(value: str, limit: int = 240) -> str:
    lines = [line.strip() for line in str(value or "").splitlines() if line.strip()]
    text = lines[-1] if lines else "erro desconhecido"
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


@lru_cache(maxsize=4)
def nvenc_status(ffmpeg: str) -> tuple[bool, str]:
    try:
        listed = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"não foi possível consultar os encoders do FFmpeg: {exc}"

    encoder_list = (listed.stdout or "") + "\n" + (listed.stderr or "")
    if "h264_nvenc" not in encoder_list:
        return False, "este FFmpeg não inclui o encoder h264_nvenc"

    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=size=1280x720:rate=30",
        "-t",
        "1",
        "-c:v",
        "h264_nvenc",
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"teste do NVENC não pôde ser executado: {exc}"

    if result.returncode == 0:
        return True, "disponível"
    return False, _compact_error(result.stderr)


def choose_h264_encoder(ffmpeg: str) -> str:
    available, _ = nvenc_status(ffmpeg)
    return "h264_nvenc" if available else "libx264"


def _build_ffmpeg_command(
    plan: CompatibilityPlan,
    output: Path,
    ffmpeg: str,
    encoder: str,
) -> list[str]:
    command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-stats",
        "-i",
        str(plan.source),
        "-map",
        "0:v:0",
    ]

    for audio in plan.selected_audios:
        command.extend(["-map", f"0:{audio.index}"])

    command.extend(["-map", "0:s?", "-map", "0:t?", "-map", "0:d?"])
    command.extend(["-map_metadata", "0", "-map_chapters", "0"])

    if plan.transcode_video:
        command.extend(["-c:v", encoder, "-vf", "format=yuv420p", "-profile:v", "high"])
        if encoder == "h264_nvenc":
            command.extend(
                [
                    "-preset",
                    "p5",
                    "-tune",
                    "hq",
                    "-rc",
                    "vbr",
                    "-cq",
                    "23",
                    "-b:v",
                    "0",
                ]
            )
        else:
            command.extend(["-preset", "veryfast", "-crf", "20"])
    else:
        command.extend(["-c:v", "copy"])

    command.extend(["-c:s", "copy", "-c:t", "copy", "-c:d", "copy"])
    transcode_audio = set(plan.transcode_audio_positions)
    for position in range(len(plan.selected_audios)):
        if position in transcode_audio:
            command.extend(
                [
                    f"-c:a:{position}",
                    "aac",
                    f"-profile:a:{position}",
                    "aac_low",
                    f"-b:a:{position}",
                    "160k",
                    f"-ar:a:{position}",
                    "48000",
                ]
            )
        else:
            command.extend([f"-c:a:{position}", "copy"])
        command.extend(
            [
                f"-disposition:a:{position}",
                "default" if position == 0 else "0",
            ]
        )

    command.append(str(output))
    return command


def prepare_for_telegram(plan: CompatibilityPlan) -> PreparedMedia:
    if not plan.needs_conversion:
        return PreparedMedia(path=plan.source, changed=False, plan=plan)

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg não foi encontrado. Instale o FFmpeg ou use --playback-fix off."
        )

    encoder = choose_h264_encoder(ffmpeg) if plan.transcode_video else "copy"
    tempdir = tempfile.TemporaryDirectory(prefix="tg-upload-compat-")
    output = Path(tempdir.name) / plan.source.name
    command = _build_ffmpeg_command(plan, output, ffmpeg, encoder)

    try:
        result = subprocess.run(command)
        if result.returncode != 0 or not output.exists() or output.stat().st_size == 0:
            raise RuntimeError(f"FFmpeg terminou com código {result.returncode}.")
    except BaseException:
        tempdir.cleanup()
        raise

    return PreparedMedia(path=output, changed=True, plan=plan, _tempdir=tempdir)


def describe_plan(plan: CompatibilityPlan) -> list[str]:
    if not plan.needs_conversion:
        return ["MKV já está no perfil de compatibilidade; envio sem conversão."]

    lines = ["Compatibilidade Telegram: criando cópia temporária; o original não será alterado."]
    lines.extend(f"  - {action}" for action in plan.actions)

    if plan.transcode_video:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            available, reason = nvenc_status(ffmpeg)
            if available:
                lines.append("  - encoder de vídeo: NVIDIA NVENC")
            else:
                lines.append(f"  - encoder de vídeo: libx264 (CPU; NVENC indisponível: {reason})")
                lines.append("  - fallback CPU otimizado: preset veryfast")
    return lines

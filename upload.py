from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from telethon import TelegramClient, utils
from telethon.errors import FloodWaitError


APP_DIR = Path.home() / ".telegram-media-upload"
CONFIG_PATH = APP_DIR / "config.json"
STATE_PATH = APP_DIR / "state.json"
SESSION_BASE = APP_DIR / "telegram"
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}
EPISODE_RE = re.compile(r"(?i)\bS(?P<season>\d{1,3})E(?P<episode>\d{1,4})\b")
QUALITY_RE = re.compile(r"\s*\[(?:\d{3,4}p|4k|8k)\]\s*$", re.IGNORECASE)
SEASON_DIR_RE = re.compile(r"(?i)^season\s+0*(\d+)$")
SPECIAL_COMMANDS = {"channel", "set-channel", "config"}


@dataclass(frozen=True)
class MediaItem:
    path: Path
    season: int | None
    episode: int | None
    code: str | None
    title: str

    @property
    def caption(self) -> str:
        if self.code:
            return f"#{self.code} - {self.title}"
        return self.title


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path: Path, value: Any) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def clean_title(stem: str, match: re.Match[str] | None) -> str:
    title = stem
    if match:
        title = title[match.end() :]
    title = re.sub(r"^[\s._+-]*[-–—:]?[\s._+-]*", "", title)
    title = QUALITY_RE.sub("", title)
    # Nomes antigos do video-dl usavam " _ " quando a origem trazia "/".
    title = re.sub(r"\s+_\s+", " + ", title)
    title = re.sub(r"\s*/\s*", " + ", title)
    title = re.sub(r"\s+", " ", title).strip(" ._-+")
    return title or stem


def parse_media(path: Path) -> MediaItem:
    stem = path.stem
    match = EPISODE_RE.search(stem)
    if not match:
        return MediaItem(path=path, season=None, episode=None, code=None, title=clean_title(stem, None))

    season = int(match.group("season"))
    episode = int(match.group("episode"))
    code = f"S{season:02d}E{episode:02d}"
    return MediaItem(
        path=path,
        season=season,
        episode=episode,
        code=code,
        title=clean_title(stem, match),
    )


def collect_media(target: Path, recursive: bool) -> list[MediaItem]:
    if target.is_file():
        if target.suffix.lower() not in VIDEO_EXTENSIONS:
            raise ValueError(f"Formato não suportado: {target.suffix}")
        paths = [target]
    elif target.is_dir():
        iterator = target.rglob("*") if recursive else target.glob("*")
        paths = [p for p in iterator if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]
    else:
        raise FileNotFoundError(f"Caminho não encontrado: {target}")

    items = [parse_media(path) for path in paths]
    items.sort(
        key=lambda item: (
            item.season if item.season is not None else 9999,
            item.episode if item.episode is not None else 999999,
            item.path.name.lower(),
        )
    )
    return items


def infer_library_name(target: Path) -> str:
    base = target.parent if target.is_file() else target
    if SEASON_DIR_RE.match(base.name) and base.parent.name:
        return base.parent.name
    return base.name or "biblioteca"


def upload_key(channel_id: int, library: str, item: MediaItem) -> str:
    if item.code:
        return f"{channel_id}|{library}|{item.code}"
    stat = item.path.stat()
    return f"{channel_id}|{library}|{item.path.resolve()}|{stat.st_size}"


def header_key(channel_id: int, library: str, season: int) -> str:
    return f"{channel_id}|{library}|S{season:02d}"


def print_plan(items: list[MediaItem]) -> None:
    if not items:
        print("Nenhum vídeo encontrado.")
        return

    last_season: int | None = None
    for item in items:
        if item.season is not None and item.season != last_season:
            print(f"\n📺 #S{item.season:02d} — TEMPORADA {item.season}")
            last_season = item.season
        print(f"\n{item.path.name}")
        print(item.caption)


def get_api_credentials(config: dict[str, Any]) -> tuple[int, str]:
    env_id = os.getenv("TG_API_ID")
    env_hash = os.getenv("TG_API_HASH")

    raw_id = env_id or config.get("api_id")
    api_hash = env_hash or config.get("api_hash")

    if not raw_id:
        raw_id = input("Telegram API ID: ").strip()
    if not api_hash:
        api_hash = getpass.getpass("Telegram API hash: ").strip()

    try:
        api_id = int(raw_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("API ID inválido.") from exc

    if not api_hash:
        raise ValueError("API hash não pode ficar vazio.")

    if not env_id and not env_hash:
        config["api_id"] = api_id
        config["api_hash"] = api_hash
        save_json(CONFIG_PATH, config)

    return api_id, str(api_hash)


def channel_display_name(entity) -> str:
    return (
        getattr(entity, "title", None)
        or getattr(entity, "username", None)
        or str(utils.get_peer_id(entity))
    )


def save_default_channel(config: dict[str, Any], entity) -> None:
    config["channel_id"] = utils.get_peer_id(entity)
    config["channel_name"] = channel_display_name(entity)
    save_json(CONFIG_PATH, config)


async def prompt_channel(client: TelegramClient):
    dialogs = []
    async for dialog in client.iter_dialogs():
        if dialog.is_channel:
            dialogs.append(dialog)

    if not dialogs:
        raise RuntimeError("Nenhum canal/grupo do Telegram foi encontrado nessa conta.")

    print("\nEscolha o canal de destino:")
    for index, dialog in enumerate(dialogs, start=1):
        entity = dialog.entity
        kind = "canal" if getattr(entity, "broadcast", False) else "grupo"
        print(f"  {index}. {dialog.name} ({kind}, {dialog.id})")

    while True:
        choice = input("Número do canal: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(dialogs):
            return dialogs[int(choice) - 1].entity
        print("Opção inválida.")


async def resolve_channel(client: TelegramClient, requested: str):
    candidate: str | int = requested
    if re.fullmatch(r"-?\d+", requested):
        candidate = int(requested)
    return await client.get_entity(candidate)


async def choose_channel(client: TelegramClient, config: dict[str, Any], requested: str | None):
    if requested:
        return await resolve_channel(client, requested)

    env_channel = os.getenv("TG_CHANNEL")
    if env_channel:
        return await resolve_channel(client, env_channel)

    configured_id = config.get("channel_id")
    if configured_id is not None:
        try:
            return await client.get_entity(int(configured_id))
        except Exception:
            pass

    entity = await prompt_channel(client)
    save_default_channel(config, entity)
    return entity


def show_channel() -> int:
    config: dict[str, Any] = load_json(CONFIG_PATH, {})
    env_channel = os.getenv("TG_CHANNEL")
    if env_channel:
        print(f"Canal ativo via TG_CHANNEL: {env_channel}")
        if config.get("channel_id") is not None:
            print(
                f"Canal padrão salvo: {config.get('channel_name') or '(sem nome)'} "
                f"({config.get('channel_id')})"
            )
        return 0

    channel_id = config.get("channel_id")
    if channel_id is None:
        print("Nenhum canal padrão configurado.")
        print("Use: tg-upload set-channel")
        return 1

    print(f"Canal padrão: {config.get('channel_name') or '(sem nome)'} ({channel_id})")
    return 0


def show_config() -> int:
    config: dict[str, Any] = load_json(CONFIG_PATH, {})
    print(f"Config:    {CONFIG_PATH}")
    print(f"Sessão:    {SESSION_BASE}.session")
    print(f"Histórico: {STATE_PATH}")
    print(f"API ID:    {'configurado' if (os.getenv('TG_API_ID') or config.get('api_id')) else 'não configurado'}")
    print(f"API hash:  {'configurado' if (os.getenv('TG_API_HASH') or config.get('api_hash')) else 'não configurado'}")

    if os.getenv("TG_CHANNEL"):
        print(f"Canal:     {os.getenv('TG_CHANNEL')} (via TG_CHANNEL)")
    elif config.get("channel_id") is not None:
        print(
            f"Canal:     {config.get('channel_name') or '(sem nome)'} "
            f"({config.get('channel_id')})"
        )
    else:
        print("Canal:     não configurado")
    return 0


async def set_channel(requested: str | None) -> int:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    config: dict[str, Any] = load_json(CONFIG_PATH, {})
    api_id, api_hash = get_api_credentials(config)

    client = TelegramClient(str(SESSION_BASE), api_id, api_hash)
    await client.start()
    try:
        entity = await resolve_channel(client, requested) if requested else await prompt_channel(client)
        save_default_channel(config, entity)
        print(f"Canal padrão definido: {channel_display_name(entity)} ({utils.get_peer_id(entity)})")
        return 0
    finally:
        await client.disconnect()


def progress_callback(label: str):
    state = {"bucket": -1}

    def callback(current: int, total: int) -> None:
        if total <= 0:
            return
        percent = int(current * 100 / total)
        bucket = percent // 5
        if bucket != state["bucket"] or percent == 100:
            state["bucket"] = bucket
            current_mb = current / (1024 * 1024)
            total_mb = total / (1024 * 1024)
            print(
                f"\r{label}: {percent:3d}% ({current_mb:.1f}/{total_mb:.1f} MiB)",
                end="",
                flush=True,
            )

    return callback


async def send_media(client: TelegramClient, entity, item: MediaItem, as_document: bool) -> None:
    label = item.code or item.path.name
    for attempt in range(2):
        try:
            await client.send_file(
                entity,
                str(item.path),
                caption=item.caption,
                force_document=as_document,
                supports_streaming=not as_document,
                progress_callback=progress_callback(label),
            )
            print()
            return
        except FloodWaitError as exc:
            if attempt == 1:
                raise
            wait = int(exc.seconds) + 1
            print(f"\nTelegram pediu espera de {wait}s. Aguardando...")
            await asyncio.sleep(wait)


async def run(args: argparse.Namespace) -> int:
    target = Path(args.path).expanduser().resolve()
    items = collect_media(target, recursive=not args.no_recursive)
    if not items:
        print("Nenhum vídeo encontrado.")
        return 1

    if args.dry_run:
        print_plan(items)
        print(f"\nTotal: {len(items)} arquivo(s). Nada foi enviado.")
        return 0

    APP_DIR.mkdir(parents=True, exist_ok=True)
    config: dict[str, Any] = load_json(CONFIG_PATH, {})
    state: dict[str, Any] = load_json(STATE_PATH, {"uploads": {}, "headers": {}})
    state.setdefault("uploads", {})
    state.setdefault("headers", {})

    api_id, api_hash = get_api_credentials(config)
    library = args.library or infer_library_name(target)

    client = TelegramClient(str(SESSION_BASE), api_id, api_hash)
    await client.start()

    try:
        entity = await choose_channel(client, config, args.channel)
        channel_id = utils.get_peer_id(entity)
        display_name = channel_display_name(entity)
        print(f"\nDestino: {display_name}")
        print(f"Biblioteca: {library}")
        print(f"Arquivos encontrados: {len(items)}\n")

        sent = 0
        skipped = 0
        failed = 0
        announced_this_run: set[int] = set()

        for item in items:
            key = upload_key(channel_id, library, item)
            if not args.force and key in state["uploads"]:
                print(f"Pulado: {item.path.name}")
                skipped += 1
                continue

            if (
                item.season is not None
                and not args.no_season_header
                and item.season not in announced_this_run
            ):
                hkey = header_key(channel_id, library, item.season)
                if args.force_header or hkey not in state["headers"]:
                    text = f"📺 #S{item.season:02d} — TEMPORADA {item.season}"
                    await client.send_message(entity, text)
                    state["headers"][hkey] = {
                        "sent_at": int(time.time()),
                        "text": text,
                    }
                    save_json(STATE_PATH, state)
                announced_this_run.add(item.season)

            print(f"Enviando: {item.path.name}")
            try:
                await send_media(client, entity, item, as_document=args.document)
            except Exception as exc:
                failed += 1
                print(f"Falhou: {item.path.name}\n  {exc}", file=sys.stderr)
                if args.stop_on_error:
                    raise
                continue

            stat = item.path.stat()
            state["uploads"][key] = {
                "file": item.path.name,
                "size": stat.st_size,
                "sent_at": int(time.time()),
                "caption": item.caption,
            }
            save_json(STATE_PATH, state)
            sent += 1

            if args.delay > 0:
                await asyncio.sleep(args.delay)

        print("\nResumo:")
        print(f"  Enviados: {sent}")
        print(f"  Pulados:  {skipped}")
        print(f"  Falharam: {failed}")
        return 0 if failed == 0 else 2
    finally:
        await client.disconnect()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tg-upload",
        description="Envia vídeos em lote para um canal do Telegram e gera uma hashtag SxxExx por episódio.",
        epilog=(
            "Comandos: tg-upload channel | tg-upload set-channel [@canal|-100...] | "
            "tg-upload config"
        ),
    )
    parser.add_argument("path", help="Arquivo ou pasta que será enviada.")
    parser.add_argument("--channel", help="@username, ID ou -100... do canal para esta execução.")
    parser.add_argument("--library", help="Nome da biblioteca/série usado no estado local.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra arquivos e legendas sem conectar ao Telegram.")
    parser.add_argument("--force", action="store_true", help="Reenvia episódios já registrados no estado local.")
    parser.add_argument("--force-header", action="store_true", help="Publica novamente o separador da temporada.")
    parser.add_argument("--document", action="store_true", help="Envia como documento em vez de vídeo reproduzível.")
    parser.add_argument("--no-season-header", action="store_true", help="Não publica a mensagem de início da temporada.")
    parser.add_argument("--no-recursive", action="store_true", help="Não procura vídeos em subpastas.")
    parser.add_argument("--stop-on-error", action="store_true", help="Interrompe o lote no primeiro erro.")
    parser.add_argument("--delay", type=float, default=0.75, help="Pausa entre uploads em segundos (padrão: 0.75).")
    return parser


def main() -> int:
    try:
        if len(sys.argv) >= 2 and sys.argv[1].lower() in SPECIAL_COMMANDS:
            command = sys.argv[1].lower()

            if command == "channel":
                if len(sys.argv) != 2:
                    print("Uso: tg-upload channel", file=sys.stderr)
                    return 2
                return show_channel()

            if command == "config":
                if len(sys.argv) != 2:
                    print("Uso: tg-upload config", file=sys.stderr)
                    return 2
                return show_config()

            if command == "set-channel":
                if len(sys.argv) > 3:
                    print("Uso: tg-upload set-channel [@canal|-100...]", file=sys.stderr)
                    return 2
                requested = sys.argv[2] if len(sys.argv) == 3 else None
                return asyncio.run(set_channel(requested))

        parser = build_parser()
        args = parser.parse_args()
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nCancelado.")
        return 130
    except Exception as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

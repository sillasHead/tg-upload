from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time
from dataclasses import dataclass
from typing import Any

from telethon import TelegramClient, utils
from telethon.errors import FloodWaitError

import upload


CLONE_STATE_PATH = upload.APP_DIR / "clone-state.json"
SECTIONS = ("original", "legendado", "dublado", "nao-classificado")

_SECTION_LABELS = {
    "original": "Original / inglês",
    "legendado": "Legendado",
    "dublado": "Dublado PT-BR",
    "nao-classificado": "Não classificado",
}

_SECTION_PATTERNS = (
    (
        "legendado",
        re.compile(
            r"(?i)\b(?:legendad[oa]s?|legendas?|subtitulad[oa]s?|subbed|subtitles?)\b"
        ),
    ),
    (
        "dublado",
        re.compile(
            r"(?i)\b(?:dublad[oa]s?|dubbed|pt[ ._-]?br|portugu[eê]s(?:\s+brasileiro)?)\b"
        ),
    ),
    (
        "original",
        re.compile(
            r"(?i)\b(?:original|ingl[eê]s|english|sem\s+legendas?|no\s+subtitles?)\b"
        ),
    ),
)


@dataclass
class CloneEntry:
    message: Any
    section: str
    filename: str | None


@dataclass
class ClonePlan:
    source_id: int
    source_name: str
    entries: list[CloneEntry]
    markers: list[tuple[int, str, str]]

    @property
    def media_entries(self) -> list[CloneEntry]:
        return [entry for entry in self.entries if entry.filename]

    def counts(self) -> dict[str, int]:
        return {
            section: sum(
                1
                for entry in self.media_entries
                if entry.section == section
            )
            for section in SECTIONS
        }


def classify_marker(text: str | None) -> str | None:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if not value:
        return None
    for section, pattern in _SECTION_PATTERNS:
        if pattern.search(value):
            return section
    return None


def message_filename(message: Any) -> str | None:
    file_info = getattr(message, "file", None)
    name = getattr(file_info, "name", None)
    if name:
        return str(name)

    document = getattr(message, "document", None)
    if document is None:
        return None

    attributes = getattr(document, "attributes", None) or []
    for attribute in attributes:
        candidate = getattr(attribute, "file_name", None)
        if candidate:
            return str(candidate)
    return None


async def resolve_source(client: TelegramClient, requested: str | None):
    if requested:
        return await upload.resolve_channel(client, requested)
    print("Escolha o canal de origem:")
    return await upload.prompt_channel(client)


async def inspect_source(client: TelegramClient, source) -> ClonePlan:
    source_id = utils.get_peer_id(source)
    source_name = upload.channel_display_name(source)
    entries: list[CloneEntry] = []
    markers: list[tuple[int, str, str]] = []
    section = "nao-classificado"

    async for message in client.iter_messages(source, reverse=True):
        text = str(getattr(message, "message", "") or "").strip()
        filename = message_filename(message)

        if filename is None:
            marker_section = classify_marker(text)
            if marker_section is not None:
                section = marker_section
                markers.append((int(message.id), marker_section, text))
            continue

        entries.append(
            CloneEntry(
                message=message,
                section=section,
                filename=filename,
            )
        )

    return ClonePlan(
        source_id=source_id,
        source_name=source_name,
        entries=entries,
        markers=markers,
    )


def print_plan(plan: ClonePlan) -> None:
    counts = plan.counts()
    print(f"\nCanal de origem: {plan.source_name} ({plan.source_id})")
    print(f"Arquivos encontrados: {len(plan.media_entries)}")
    print(f"Marcadores reconhecidos: {len(plan.markers)}\n")

    for section in SECTIONS:
        print(f"  {_SECTION_LABELS[section]:<20} {counts[section]}")

    if plan.markers:
        print("\nMarcadores/seções detectados:")
        for message_id, section, text in plan.markers[:30]:
            preview = re.sub(r"\s+", " ", text).strip()
            if len(preview) > 100:
                preview = preview[:97] + "..."
            print(f"  [{message_id}] {_SECTION_LABELS[section]}: {preview}")
        if len(plan.markers) > 30:
            print(f"  ... e mais {len(plan.markers) - 30}")

    unclassified = [
        entry for entry in plan.media_entries if entry.section == "nao-classificado"
    ]
    if unclassified:
        print("\nPrimeiros arquivos não classificados:")
        for entry in unclassified[:10]:
            print(f"  [{entry.message.id}] {entry.filename}")
        if len(unclassified) > 10:
            print(f"  ... e mais {len(unclassified) - 10}")


def _destination_entry(config: dict[str, Any], alias: str | None) -> dict[str, Any] | None:
    if not alias:
        return None
    normalized = upload.normalize_destination_name(alias)
    return (config.get("destinations") or {}).get(normalized)


async def _resolve_destination_alias(
    client: TelegramClient,
    config: dict[str, Any],
    alias: str,
) -> upload.Destination:
    normalized = upload.normalize_destination_name(alias)
    entry = _destination_entry(config, normalized)
    if not entry:
        raise ValueError(
            f"Destino '{normalized}' não configurado. "
            f"Use: tg-upload set-destination {normalized}"
        )
    entity = await client.get_entity(int(entry["channel_id"]))
    return upload.Destination(
        entity=entity,
        channel_id=utils.get_peer_id(entity),
        channel_name=str(entry.get("channel_name") or upload.channel_display_name(entity)),
        topic_id=int(entry["topic_id"]) if entry.get("topic_id") is not None else None,
        topic_name=entry.get("topic_name"),
        alias=normalized,
    )


async def _copy_media(client, destination: upload.Destination, entry: CloneEntry) -> None:
    message = entry.message
    caption = str(getattr(message, "message", "") or "").strip() or None
    media = getattr(message, "media", None)
    if media is None:
        raise RuntimeError("Mensagem não contém mídia copiável.")

    await client.send_file(
        destination.entity,
        media,
        caption=caption,
        reply_to=destination.topic_id,
    )


async def execute_plan(
    client: TelegramClient,
    config: dict[str, Any],
    plan: ClonePlan,
    aliases: dict[str, str | None],
    *,
    stop_on_error: bool,
    delay: float,
) -> int:
    destinations: dict[str, upload.Destination] = {}
    for section, alias in aliases.items():
        if alias:
            destinations[section] = await _resolve_destination_alias(client, config, alias)

    missing = [
        section
        for section in ("original", "legendado", "dublado")
        if plan.counts()[section] and section not in destinations
    ]
    if missing:
        names = ", ".join(_SECTION_LABELS[section] for section in missing)
        raise ValueError(
            "Há arquivos sem destino configurado para: "
            f"{names}. Informe os respectivos --*-to."
        )

    state = upload.load_json(CLONE_STATE_PATH, {"copied": {}})
    copied_state = state.setdefault("copied", {})
    copied = 0
    skipped = 0
    failed = 0

    print("\nDestinos:")
    for section in SECTIONS:
        destination = destinations.get(section)
        if destination:
            print(f"  {_SECTION_LABELS[section]:<20} -> {destination.display_name}")

    for entry in plan.media_entries:
        destination = destinations.get(entry.section)
        if destination is None:
            print(
                f"Sem destino: [{entry.message.id}] {entry.filename} "
                f"({_SECTION_LABELS[entry.section]})"
            )
            skipped += 1
            continue

        key = (
            f"{plan.source_id}|{entry.message.id}|"
            f"{upload.destination_scope(destination.channel_id, destination.topic_id)}"
        )
        if key in copied_state:
            print(f"Já copiado: {entry.filename}")
            skipped += 1
            continue

        print(
            f"Copiando: {entry.filename} -> "
            f"{_SECTION_LABELS[entry.section]}"
        )
        try:
            for attempt in range(2):
                try:
                    await _copy_media(client, destination, entry)
                    break
                except FloodWaitError as exc:
                    if attempt == 1:
                        raise
                    wait = int(exc.seconds) + 1
                    print(f"Telegram pediu espera de {wait}s. Aguardando...")
                    await asyncio.sleep(wait)
        except Exception as exc:
            failed += 1
            print(f"Falhou: {entry.filename}\n  {exc}", file=sys.stderr)
            if stop_on_error:
                raise
            continue

        copied_state[key] = {
            "source_channel_id": plan.source_id,
            "source_message_id": int(entry.message.id),
            "source_file": entry.filename,
            "section": entry.section,
            "destination": destination.alias,
            "copied_at": int(time.time()),
        }
        upload.save_json(CLONE_STATE_PATH, state)
        copied += 1

        if delay > 0:
            await asyncio.sleep(delay)

    print("\nResumo da clonagem:")
    print(f"  Copiados: {copied}")
    print(f"  Pulados:  {skipped}")
    print(f"  Falharam: {failed}")
    return 0 if failed == 0 else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tg-upload clone-channel",
        description=(
            "Analisa um canal e separa os arquivos em blocos Original, Legendado e "
            "Dublado PT-BR a partir das mensagens de seção."
        ),
    )
    parser.add_argument(
        "--from",
        dest="source",
        help="@username ou ID do canal de origem. Se omitido, pergunta interativamente.",
    )
    parser.add_argument("--original-to", help="Destino salvo para o bloco Original/inglês.")
    parser.add_argument("--legendado-to", help="Destino salvo para o bloco Legendado.")
    parser.add_argument("--dublado-to", help="Destino salvo para o bloco Dublado PT-BR.")
    parser.add_argument(
        "--unclassified-to",
        help="Destino salvo para arquivos que aparecem antes de um marcador reconhecido.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Executa a cópia. Sem esta opção, apenas analisa e mostra o plano.",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Interrompe no primeiro arquivo que falhar.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.2,
        help="Pausa entre cópias em segundos (padrão: 0.2).",
    )
    return parser


async def run(options: argparse.Namespace) -> int:
    upload.APP_DIR.mkdir(parents=True, exist_ok=True)
    config: dict[str, Any] = upload.load_json(upload.CONFIG_PATH, {})
    api_id, api_hash = upload.get_api_credentials(config)

    client = TelegramClient(str(upload.SESSION_BASE), api_id, api_hash)
    await client.start()
    try:
        source = await resolve_source(client, options.source)
        plan = await inspect_source(client, source)
        print_plan(plan)

        if not options.execute:
            print(
                "\nNada foi copiado. Revise as seções acima. "
                "Quando estiver correto, execute novamente com --execute e os destinos."
            )
            return 0

        aliases = {
            "original": options.original_to,
            "legendado": options.legendado_to,
            "dublado": options.dublado_to,
            "nao-classificado": options.unclassified_to,
        }
        return await execute_plan(
            client,
            config,
            plan,
            aliases,
            stop_on_error=options.stop_on_error,
            delay=max(0.0, float(options.delay)),
        )
    finally:
        await client.disconnect()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    options = parser.parse_args(argv)
    try:
        return asyncio.run(run(options))
    except KeyboardInterrupt:
        print("\nCancelado.")
        return 130
    except Exception as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"marker not found: {label}")
    return text.replace(old, new, 1)


root = Path('.')
path = root / 'upload.py'
text = path.read_text(encoding='utf-8')

text = replace_once(
    text,
    'from telethon import TelegramClient, utils',
    'from telethon import TelegramClient, functions, utils',
    'telethon imports',
)
text = replace_once(
    text,
    'SPECIAL_COMMANDS = {"channel", "set-channel", "config"}',
    'SPECIAL_COMMANDS = {"channel", "set-channel", "config", "destinations", "set-destination", "remove-destination"}',
    'special commands',
)

marker = '\n\ndef load_json(path: Path, default: Any) -> Any:\n'
destination_dataclass = '''\n\n@dataclass(frozen=True)\nclass Destination:\n    entity: Any\n    channel_id: int\n    channel_name: str\n    topic_id: int | None = None\n    topic_name: str | None = None\n    alias: str | None = None\n\n    @property\n    def display_name(self) -> str:\n        if self.topic_name:\n            return f"{self.channel_name} > {self.topic_name}"\n        if self.topic_id is not None:\n            return f"{self.channel_name} > tópico {self.topic_id}"\n        return self.channel_name\n\n\ndef normalize_destination_name(value: str) -> str:\n    name = value.strip().lower()\n    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", name):\n        raise ValueError("Nome de destino inválido. Use letras minúsculas, números, ponto, _ ou -.")\n    return name\n'''
text = replace_once(text, marker, destination_dataclass + marker, 'destination dataclass')

old_keys = '''def upload_key(channel_id: int, library: str, item: MediaItem) -> str:\n    if item.code:\n        return f"{channel_id}|{library}|{item.code}"\n    stat = item.path.stat()\n    return f"{channel_id}|{library}|{item.path.resolve()}|{stat.st_size}"\n\n\ndef header_key(channel_id: int, library: str, season: int) -> str:\n    return f"{channel_id}|{library}|S{season:02d}"\n'''
new_keys = '''def destination_scope(channel_id: int, topic_id: int | None) -> str:\n    # Sem tópico mantém a chave histórica para não reenviar uploads antigos.\n    if topic_id is None:\n        return str(channel_id)\n    return f"{channel_id}|topic:{topic_id}"\n\n\ndef upload_key(channel_id: int, topic_id: int | None, library: str, item: MediaItem) -> str:\n    scope = destination_scope(channel_id, topic_id)\n    if item.code:\n        return f"{scope}|{library}|{item.code}"\n    stat = item.path.stat()\n    return f"{scope}|{library}|{item.path.resolve()}|{stat.st_size}"\n\n\ndef header_key(channel_id: int, topic_id: int | None, library: str, season: int) -> str:\n    scope = destination_scope(channel_id, topic_id)\n    return f"{scope}|{library}|S{season:02d}"\n'''
text = replace_once(text, old_keys, new_keys, 'state keys')

prompt_marker = '\n\nasync def resolve_channel(client: TelegramClient, requested: str):\n'
topic_helpers = '''\n\nasync def get_forum_topics(client: TelegramClient, entity) -> list[Any]:\n    if not getattr(entity, "forum", False):\n        return []\n\n    result = await client(\n        functions.channels.GetForumTopicsRequest(\n            channel=entity,\n            q="",\n            offset_date=0,\n            offset_id=0,\n            offset_topic=0,\n            limit=100,\n        )\n    )\n    topics = list(getattr(result, "topics", []) or [])\n    topics.sort(key=lambda topic: int(getattr(topic, "id", 0)))\n    return topics\n\n\ndef topic_display_name(topic) -> str:\n    return str(getattr(topic, "title", None) or f"tópico {getattr(topic, 'id', '?')}")\n\n\nasync def resolve_topic(client: TelegramClient, entity, requested: str | None) -> tuple[int | None, str | None]:\n    if requested is None:\n        return None, None\n    if not getattr(entity, "forum", False):\n        raise ValueError("O destino escolhido não é um grupo com tópicos.")\n\n    value = requested.strip()\n    if value.lower() in {"general", "geral", "none", "sem-topico", "sem-tópico"}:\n        return None, "Geral"\n\n    topics = await get_forum_topics(client, entity)\n    if re.fullmatch(r"\\d+", value):\n        topic_id = int(value)\n        match = next((topic for topic in topics if int(getattr(topic, "id", -1)) == topic_id), None)\n        return topic_id, topic_display_name(match) if match else f"tópico {topic_id}"\n\n    exact = [topic for topic in topics if topic_display_name(topic).casefold() == value.casefold()]\n    if len(exact) == 1:\n        return int(exact[0].id), topic_display_name(exact[0])\n\n    partial = [topic for topic in topics if value.casefold() in topic_display_name(topic).casefold()]\n    if len(partial) == 1:\n        return int(partial[0].id), topic_display_name(partial[0])\n    if len(partial) > 1:\n        names = ", ".join(topic_display_name(topic) for topic in partial)\n        raise ValueError(f"Tópico ambíguo: {requested}. Correspondências: {names}")\n    raise ValueError(f"Tópico não encontrado: {requested}")\n\n\nasync def prompt_topic(client: TelegramClient, entity) -> tuple[int | None, str | None]:\n    if not getattr(entity, "forum", False):\n        return None, None\n\n    topics = await get_forum_topics(client, entity)\n    print("\\nEscolha o tópico de destino:")\n    print("  0. Geral")\n    for index, topic in enumerate(topics, start=1):\n        print(f"  {index}. {topic_display_name(topic)} (ID {topic.id})")\n\n    while True:\n        choice = input("Número do tópico [0]: ").strip() or "0"\n        if choice == "0":\n            return None, "Geral"\n        if choice.isdigit() and 1 <= int(choice) <= len(topics):\n            topic = topics[int(choice) - 1]\n            return int(topic.id), topic_display_name(topic)\n        print("Opção inválida.")\n'''
text = replace_once(text, prompt_marker, topic_helpers + prompt_marker, 'topic helpers')

choose_marker = '\n\ndef show_channel() -> int:\n'
choose_destination = '''\n\nasync def choose_destination(\n    client: TelegramClient,\n    config: dict[str, Any],\n    alias: str | None,\n    requested_channel: str | None,\n    requested_topic: str | None,\n) -> Destination:\n    if alias:\n        if requested_channel or requested_topic:\n            raise ValueError("Use --to sozinho; não combine com --channel/--topic.")\n        key = normalize_destination_name(alias)\n        entry = (config.get("destinations") or {}).get(key)\n        if not entry:\n            raise ValueError(f"Destino '{key}' não configurado. Use: tg-upload set-destination {key}")\n        entity = await client.get_entity(int(entry["channel_id"]))\n        return Destination(\n            entity=entity,\n            channel_id=utils.get_peer_id(entity),\n            channel_name=str(entry.get("channel_name") or channel_display_name(entity)),\n            topic_id=int(entry["topic_id"]) if entry.get("topic_id") is not None else None,\n            topic_name=entry.get("topic_name"),\n            alias=key,\n        )\n\n    entity = await choose_channel(client, config, requested_channel)\n    topic_id, topic_name = await resolve_topic(client, entity, requested_topic) if requested_topic else (None, None)\n    return Destination(\n        entity=entity,\n        channel_id=utils.get_peer_id(entity),\n        channel_name=channel_display_name(entity),\n        topic_id=topic_id,\n        topic_name=topic_name,\n    )\n'''
text = replace_once(text, choose_marker, choose_destination + choose_marker, 'choose destination')

old_config_tail = '''    else:\n        print("Canal:     não configurado")\n    return 0\n'''
new_config_tail = '''    else:\n        print("Canal:     não configurado")\n\n    destinations = config.get("destinations") or {}\n    print(f"Destinos:  {len(destinations)} configurado(s)")\n    return 0\n'''
text = replace_once(text, old_config_tail, new_config_tail, 'show config destinations')

set_channel_marker = '\n\ndef progress_callback(label: str):\n'
destination_commands = '''\n\ndef show_destinations() -> int:\n    config: dict[str, Any] = load_json(CONFIG_PATH, {})\n    destinations = config.get("destinations") or {}\n    if not destinations:\n        print("Nenhum destino configurado.")\n        print("Use: tg-upload set-destination anime")\n        return 0\n\n    print("Destinos configurados:")\n    for alias in sorted(destinations):\n        entry = destinations[alias]\n        channel_name = entry.get("channel_name") or str(entry.get("channel_id"))\n        topic_name = entry.get("topic_name")\n        topic_id = entry.get("topic_id")\n        if topic_name:\n            location = f"{channel_name} > {topic_name}"\n        elif topic_id is not None:\n            location = f"{channel_name} > tópico {topic_id}"\n        else:\n            location = channel_name\n        print(f"  {alias:<16} {location}")\n    return 0\n\n\nasync def set_destination(name: str, requested_channel: str | None, requested_topic: str | None) -> int:\n    APP_DIR.mkdir(parents=True, exist_ok=True)\n    config: dict[str, Any] = load_json(CONFIG_PATH, {})\n    api_id, api_hash = get_api_credentials(config)\n    alias = normalize_destination_name(name)\n\n    client = TelegramClient(str(SESSION_BASE), api_id, api_hash)\n    await client.start()\n    try:\n        entity = await resolve_channel(client, requested_channel) if requested_channel else await prompt_channel(client)\n        if requested_topic is not None:\n            topic_id, topic_name = await resolve_topic(client, entity, requested_topic)\n        else:\n            topic_id, topic_name = await prompt_topic(client, entity)\n\n        destinations = config.setdefault("destinations", {})\n        destinations[alias] = {\n            "channel_id": utils.get_peer_id(entity),\n            "channel_name": channel_display_name(entity),\n            "topic_id": topic_id,\n            "topic_name": topic_name,\n        }\n        save_json(CONFIG_PATH, config)\n        destination = Destination(\n            entity=entity,\n            channel_id=utils.get_peer_id(entity),\n            channel_name=channel_display_name(entity),\n            topic_id=topic_id,\n            topic_name=topic_name,\n            alias=alias,\n        )\n        print(f"Destino '{alias}' definido: {destination.display_name}")\n        return 0\n    finally:\n        await client.disconnect()\n\n\ndef remove_destination(name: str) -> int:\n    config: dict[str, Any] = load_json(CONFIG_PATH, {})\n    alias = normalize_destination_name(name)\n    destinations = config.get("destinations") or {}\n    if alias not in destinations:\n        print(f"Destino '{alias}' não existe.")\n        return 1\n    del destinations[alias]\n    config["destinations"] = destinations\n    save_json(CONFIG_PATH, config)\n    print(f"Destino '{alias}' removido.")\n    return 0\n'''
text = replace_once(text, set_channel_marker, destination_commands + set_channel_marker, 'destination commands')

text = replace_once(
    text,
    'async def send_media(client: TelegramClient, entity, item: MediaItem, as_document: bool) -> None:',
    'async def send_media(client: TelegramClient, entity, item: MediaItem, as_document: bool, topic_id: int | None = None) -> None:',
    'send media signature',
)
text = replace_once(
    text,
    '                supports_streaming=not as_document,\n                progress_callback=progress_callback(label),',
    '                supports_streaming=not as_document,\n                reply_to=topic_id,\n                progress_callback=progress_callback(label),',
    'send file topic',
)

old_run_destination = '''        entity = await choose_channel(client, config, args.channel)\n        channel_id = utils.get_peer_id(entity)\n        display_name = channel_display_name(entity)\n        print(f"\\nDestino: {display_name}")\n        print(f"Biblioteca: {library}")\n'''
new_run_destination = '''        destination = await choose_destination(client, config, args.to, args.channel, args.topic)\n        entity = destination.entity\n        channel_id = destination.channel_id\n        topic_id = destination.topic_id\n        print(f"\\nDestino: {destination.display_name}")\n        if destination.alias:\n            print(f"Atalho: {destination.alias}")\n        print(f"Biblioteca: {library}")\n'''
text = replace_once(text, old_run_destination, new_run_destination, 'run destination')
text = text.replace('upload_key(channel_id, library, item)', 'upload_key(channel_id, topic_id, library, item)')
text = text.replace('header_key(channel_id, library, item.season)', 'header_key(channel_id, topic_id, library, item.season)')
text = replace_once(
    text,
    '                    await client.send_message(entity, text)',
    '                    await client.send_message(entity, text, reply_to=topic_id)',
    'season header topic',
)
text = replace_once(
    text,
    '                await send_media(client, entity, item, as_document=args.document)',
    '                await send_media(client, entity, item, as_document=args.document, topic_id=topic_id)',
    'media topic argument',
)

text = replace_once(
    text,
    '            "Comandos: tg-upload channel | tg-upload set-channel [@canal|-100...] | "\n            "tg-upload config"',
    '            "Comandos: tg-upload channel | tg-upload set-channel [@canal|-100...] | "\n            "tg-upload destinations | tg-upload set-destination NOME | tg-upload config"',
    'parser epilog',
)
text = replace_once(
    text,
    '    parser.add_argument("--channel", help="@username, ID ou -100... do canal para esta execução.")\n',
    '    parser.add_argument("--channel", help="@username, ID ou -100... do canal/grupo para esta execução.")\n    parser.add_argument("--topic", help="Nome ou ID do tópico para esta execução (requer grupo com tópicos).")\n    parser.add_argument("--to", help="Atalho de destino salvo, por exemplo: anime, desenho, filme ou one-piece.")\n',
    'parser destination args',
)

main_marker = '''            if command == "set-channel":\n                if len(sys.argv) > 3:\n                    print("Uso: tg-upload set-channel [@canal|-100...]", file=sys.stderr)\n                    return 2\n                requested = sys.argv[2] if len(sys.argv) == 3 else None\n                return asyncio.run(set_channel(requested))\n'''
main_replacement = main_marker + '''\n            if command == "destinations":\n                if len(sys.argv) != 2:\n                    print("Uso: tg-upload destinations", file=sys.stderr)\n                    return 2\n                return show_destinations()\n\n            if command == "remove-destination":\n                if len(sys.argv) != 3:\n                    print("Uso: tg-upload remove-destination NOME", file=sys.stderr)\n                    return 2\n                return remove_destination(sys.argv[2])\n\n            if command == "set-destination":\n                destination_parser = argparse.ArgumentParser(prog="tg-upload set-destination")\n                destination_parser.add_argument("name", help="Atalho do destino, ex.: anime ou one-piece.")\n                destination_parser.add_argument("--channel", help="@username ou ID. Se omitido, pergunta interativamente.")\n                destination_parser.add_argument("--topic", help="Nome ou ID do tópico. Se omitido em fórum, pergunta interativamente.")\n                options = destination_parser.parse_args(sys.argv[2:])\n                return asyncio.run(set_destination(options.name, options.channel, options.topic))\n'''
text = replace_once(text, main_marker, main_replacement, 'main destination commands')

path.write_text(text, encoding='utf-8')

# README
path = root / 'README.md'
readme = path.read_text(encoding='utf-8')
insert_before = '\n## Uso\n'
destinations_docs = r'''

## Destinos e tópicos

Para uma biblioteca que mistura obras pequenas/médias em tópicos e deixa obras grandes em canais próprios, salve atalhos de destino.

Exemplo para o tópico **Animes** do grupo **Biblioteca**:

```powershell
tg-upload set-destination anime
```

O comando lista os canais/grupos da conta e, se o grupo escolhido tiver tópicos, lista também os tópicos disponíveis. Tudo fica salvo apenas no `config.json` local.

Você também pode informar diretamente:

```powershell
tg-upload set-destination anime --channel -1001234567890 --topic "Animes"
tg-upload set-destination desenho --channel -1001234567890 --topic "Desenhos"
tg-upload set-destination filme --channel -1001234567890 --topic "Filmes"
```

Depois o upload fica simples:

```powershell
tg-upload "C:\Videos\Kiseijuu" --to anime
tg-upload "C:\Videos\Bob Esponja" --to desenho
tg-upload "C:\Videos\Filmes\Meu Filme.mp4" --to filme
```

Para uma obra grande que tenha canal próprio, use outro atalho sem tópico:

```powershell
tg-upload set-destination one-piece --channel @meu_canal_onepiece
tg-upload "C:\Videos\One Piece" --to one-piece
```

Assim o mesmo programa suporta os dois modelos:

```text
Biblioteca (supergrupo)
├─ Animes   <- --to anime
├─ Desenhos <- --to desenho
└─ Filmes   <- --to filme

One Piece (canal próprio) <- --to one-piece
```

Ver os atalhos salvos:

```powershell
tg-upload destinations
```

Remover um:

```powershell
tg-upload remove-destination anime
```

Também é possível escolher um tópico só para uma execução, sem salvar atalho:

```powershell
tg-upload "C:\Videos\Kiseijuu" --channel -1001234567890 --topic "Animes"
```

O histórico diferencia canal **e tópico**. Portanto, enviar o mesmo arquivo para `Biblioteca > Animes` e depois para outro tópico é tratado como dois destinos diferentes.
'''
readme = replace_once(readme, insert_before, destinations_docs + insert_before, 'README destination section')
path.write_text(readme, encoding='utf-8')

# Tests
(root / 'tests').mkdir(exist_ok=True)
(root / 'tests' / 'test_destinations.py').write_text(r'''import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import upload


class FakeForumClient:
    async def __call__(self, request):
        return SimpleNamespace(
            topics=[
                SimpleNamespace(id=11, title="Animes"),
                SimpleNamespace(id=22, title="Desenhos"),
                SimpleNamespace(id=33, title="Filmes"),
            ]
        )


class DestinationTests(unittest.TestCase):
    def test_normalize_destination(self):
        self.assertEqual(upload.normalize_destination_name(" One-Piece "), "one-piece")
        with self.assertRaises(ValueError):
            upload.normalize_destination_name("anime grande")

    def test_topic_aware_state_key_preserves_legacy_without_topic(self):
        item = upload.MediaItem(Path("S01E02 - Teste.mp4"), 1, 2, "S01E02", "Teste")
        self.assertEqual(upload.upload_key(-1001, None, "Teste", item), "-1001|Teste|S01E02")
        self.assertEqual(upload.upload_key(-1001, 11, "Teste", item), "-1001|topic:11|Teste|S01E02")

    def test_resolve_topic_by_name(self):
        entity = SimpleNamespace(forum=True)
        topic_id, topic_name = asyncio.run(upload.resolve_topic(FakeForumClient(), entity, "Animes"))
        self.assertEqual(topic_id, 11)
        self.assertEqual(topic_name, "Animes")

    def test_resolve_general_without_topic_id(self):
        entity = SimpleNamespace(forum=True)
        topic_id, topic_name = asyncio.run(upload.resolve_topic(FakeForumClient(), entity, "Geral"))
        self.assertIsNone(topic_id)
        self.assertEqual(topic_name, "Geral")


if __name__ == "__main__":
    unittest.main()
''', encoding='utf-8')

# CI
workflow_dir = root / '.github' / 'workflows'
workflow_dir.mkdir(parents=True, exist_ok=True)
(workflow_dir / 'ci.yml').write_text(r'''name: CI

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: python -m pip install -r requirements.txt
      - name: Compile
        run: python -m py_compile upload.py
      - name: Tests
        run: python -m unittest discover -s tests -v
''', encoding='utf-8')

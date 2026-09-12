from __future__ import annotations

import asyncio

from InquirerPy import inquirer
from InquirerPy.base.control import Choice

import upload


def _channel_label(dialog) -> str:
    entity = dialog.entity
    kind = "canal" if getattr(entity, "broadcast", False) else "grupo"
    return f"{dialog.name}  [{kind}]  {dialog.id}"


async def prompt_channel(client):
    dialogs = []
    async for dialog in client.iter_dialogs():
        if dialog.is_channel:
            dialogs.append(dialog)

    if not dialogs:
        raise RuntimeError("Nenhum canal/grupo do Telegram foi encontrado nessa conta.")

    choices = [Choice(value=dialog.entity, name=_channel_label(dialog)) for dialog in dialogs]
    print("\nDigite para pesquisar. Use ↑/↓ para navegar e Enter para selecionar.")
    return inquirer.fuzzy(
        message="Canal de destino:",
        choices=choices,
        max_height="70%",
        border=True,
        info=True,
        match_exact=False,
    ).execute()


async def prompt_topic(client, entity):
    if not getattr(entity, "forum", False):
        return None, None

    topics = await upload.get_forum_topics(client, entity)
    choices = [Choice(value=(None, "Geral"), name="Geral")]
    choices.extend(
        Choice(
            value=(int(topic.id), upload.topic_display_name(topic)),
            name=f"{upload.topic_display_name(topic)}  [ID {topic.id}]",
        )
        for topic in topics
    )

    print("\nDigite para pesquisar. Use ↑/↓ para navegar e Enter para selecionar.")
    return inquirer.fuzzy(
        message="Tópico de destino:",
        choices=choices,
        max_height="70%",
        border=True,
        info=True,
        match_exact=False,
    ).execute()


def main() -> int:
    upload.prompt_channel = prompt_channel
    upload.prompt_topic = prompt_topic
    return upload.main()


if __name__ == "__main__":
    raise SystemExit(main())

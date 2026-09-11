from pathlib import Path

path = Path('upload.py')
text = path.read_text(encoding='utf-8')
old = '''    result = await client(\n        functions.channels.GetForumTopicsRequest(\n            channel=entity,\n            q="",\n            offset_date=0,\n            offset_id=0,\n            offset_topic=0,\n            limit=100,\n        )\n    )\n'''
new = '''    messages_request = getattr(functions.messages, "GetForumTopicsRequest", None)\n    channels_request = getattr(functions.channels, "GetForumTopicsRequest", None)\n    if messages_request is not None:\n        request = messages_request(\n            peer=entity,\n            q="",\n            offset_date=0,\n            offset_id=0,\n            offset_topic=0,\n            limit=100,\n        )\n    elif channels_request is not None:\n        request = channels_request(\n            channel=entity,\n            q="",\n            offset_date=0,\n            offset_id=0,\n            offset_topic=0,\n            limit=100,\n        )\n    else:\n        raise RuntimeError("Esta versão do Telethon não oferece suporte à listagem de tópicos.")\n\n    result = await client(request)\n'''
if old not in text:
    raise SystemExit('topic request marker not found')
path.write_text(text.replace(old, new, 1), encoding='utf-8')

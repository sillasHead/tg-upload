# telegram-media-upload

Uploader em lote para canais do Telegram usando Telethon.

Pensado para bibliotecas de episódios com nomes como:

```text
S01E01 - Bolhas de sabão + Calça rasgada [720p].mp4
S01E02 - Vizinhos náuticos terríveis + Escola de pilotagem [720p].mp4
```

O uploader ordena os arquivos por temporada/episódio e gera automaticamente legendas como:

```text
#S01 #S01E01
Bolhas de sabão + Calça rasgada
```

Também pode criar uma mensagem separadora quando começa uma temporada:

```text
📺 #S01 — TEMPORADA 1
```

## Instalação

Requer Python 3.10+.

```powershell
git clone https://github.com/sillasHead/telegram-media-upload.git
cd telegram-media-upload
python -m pip install -r requirements.txt
```

No primeiro uso, o programa pede seu `api_id` e `api_hash` do Telegram e salva apenas no seu computador em:

```text
%USERPROFILE%\.telegram-media-upload\config.json
```

A sessão do Telethon também fica nessa pasta. Nada disso deve ser enviado ao GitHub.

Para obter `api_id` e `api_hash`, use `my.telegram.org` > **API development tools**.

## Uso

Enviar uma temporada inteira:

```powershell
python upload.py "C:\Users\silla\Videos\video-dl\Bob Esponja Calça Quadrada\Season 01"
```

Visualizar o que seria enviado sem publicar:

```powershell
python upload.py "C:\caminho\Season 01" --dry-run
```

Enviar novamente arquivos que já constam no estado local:

```powershell
python upload.py "C:\caminho\Season 01" --force
```

Enviar como documento em vez de vídeo reproduzível no feed:

```powershell
python upload.py "C:\caminho\Season 01" --document
```

Não publicar separadores de temporada:

```powershell
python upload.py "C:\caminho\Season 01" --no-season-header
```

Escolher outro canal apenas nessa execução:

```powershell
python upload.py "C:\caminho\Season 01" --channel -1001234567890
```

## Organização

O programa reconhece `SxxExx` no nome do arquivo. O título usado na legenda é o restante do nome, removendo o sufixo de qualidade como `[720p]`.

Os uploads concluídos são registrados localmente em:

```text
%USERPROFILE%\.telegram-media-upload\state.json
```

Assim, executar o mesmo lote novamente não reenviará os episódios já registrados, a menos que seja usado `--force`.

## Segurança

Não coloque `api_hash`, telefone, código de login ou arquivo `.session` no repositório. O `.gitignore` deste projeto ignora arquivos de sessão e configurações locais comuns.

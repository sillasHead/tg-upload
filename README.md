# telegram-media-upload

Uploader em lote para canais do Telegram usando Telethon.

Pensado para bibliotecas de episódios com nomes como:

```text
S01E01 - Bolhas de sabão + Calça rasgada [720p].mp4
S01E02 - Vizinhos náuticos terríveis + Escola de pilotagem [720p].mp4
```

O uploader ordena os arquivos por temporada/episódio e gera automaticamente uma legenda simples:

```text
#S01E01 - Bolhas de sabão + Calça rasgada
```

Também pode criar uma mensagem separadora quando começa uma temporada:

```text
📺 #S01 — TEMPORADA 1
```

## Instalação

Requer Windows e Python 3.10+.

Depois que o repositório estiver público, a instalação pode ser feita diretamente pelo PowerShell:

```powershell
irm https://raw.githubusercontent.com/sillasHead/telegram-media-upload/main/setup.ps1 | iex
```

O instalador adiciona `tg-upload` ao PATH do usuário. Depois, em qualquer terminal:

```powershell
tg-upload "C:\Videos\Minha Serie\Season 01"
```

Para atualizar:

```powershell
tg-upload update
```

## Primeiro uso

No primeiro envio real, o programa pede seu `api_id` e `api_hash` do Telegram. Esses dados não ficam no repositório: são salvos somente no computador em:

```text
%USERPROFILE%\.telegram-media-upload\config.json
```

A sessão do Telethon e o histórico de uploads também ficam nessa pasta.

Para obter `api_id` e `api_hash`, use `my.telegram.org` > **API development tools**.

## Uso

Antes do primeiro envio real, vale conferir o lote:

```powershell
tg-upload "C:\Videos\Minha Serie\Season 01" --dry-run
```

Enviar a temporada inteira:

```powershell
tg-upload "C:\Videos\Minha Serie\Season 01"
```

Enviar novamente arquivos que já constam no estado local:

```powershell
tg-upload "C:\Videos\Minha Serie\Season 01" --force
```

Enviar como documento em vez de vídeo reproduzível no feed:

```powershell
tg-upload "C:\Videos\Minha Serie\Season 01" --document
```

Não publicar separadores de temporada:

```powershell
tg-upload "C:\Videos\Minha Serie\Season 01" --no-season-header
```

Escolher outro canal apenas nessa execução:

```powershell
tg-upload "C:\Videos\Minha Serie\Season 01" --channel -1001234567890
```

## Organização

O programa reconhece `SxxExx` no nome do arquivo. O título usado na legenda é o restante do nome, removendo o sufixo de qualidade como `[720p]`.

Arquivos antigos do `video-dl` que tenham ` _ ` entre dois segmentos também são mostrados na legenda como ` + `, sem renomear o arquivo original.

Os uploads concluídos são registrados localmente em:

```text
%USERPROFILE%\.telegram-media-upload\state.json
```

Assim, executar o mesmo lote novamente não reenviará os episódios já registrados, a menos que seja usado `--force`.

## Privacidade e segurança

Nenhuma credencial do Telegram, telefone, código de login, sessão ou ID de canal precisa ser armazenado no GitHub. O `.gitignore` também ignora `.env`, arquivos `.session`, `config.json`, `state.json` e a pasta local `.telegram-media-upload`.

Por isso, o código pode ser mantido em um repositório público sem publicar esses dados pessoais. O próprio nome da conta do GitHub e o histórico público de commits continuam, naturalmente, visíveis no GitHub.

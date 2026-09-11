# tg-upload

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

Ao mudar de temporada, ele também pode criar automaticamente um separador:

```text
📺 #S01 — TEMPORADA 1
```

## Instalação

Requer Windows e Python 3.10+.

Abra o PowerShell e rode:

```powershell
irm https://raw.githubusercontent.com/sillasHead/tg-upload/main/setup.ps1 | iex
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

Na primeira vez em que não houver canal padrão configurado, o programa lista os canais/grupos disponíveis na sua conta e pede que você escolha um. A escolha fica salva apenas localmente.

## Canal padrão

Ver o canal padrão atual:

```powershell
tg-upload channel
```

Escolher outro canal padrão interativamente:

```powershell
tg-upload set-channel
```

Ou definir diretamente por username/ID:

```powershell
tg-upload set-channel @meucanal
tg-upload set-channel -1001234567890
```

Ver os caminhos e o estado da configuração sem exibir o `api_hash`:

```powershell
tg-upload config
```

Para usar outro canal somente em uma execução, sem trocar o padrão:

```powershell
tg-upload "C:\Videos\Minha Serie" --channel -1001234567890
```

## Uso

Antes do primeiro envio real, vale conferir o lote:

```powershell
tg-upload "C:\Videos\Minha Serie" --dry-run
```

Enviar uma temporada inteira:

```powershell
tg-upload "C:\Videos\Minha Serie\Season 01"
```

Enviar a série inteira, procurando vídeos recursivamente nas subpastas:

```powershell
tg-upload "C:\Videos\Minha Serie"
```

Exemplo de estrutura:

```text
Minha Serie\
├─ Season 01\
│  ├─ S01E01 - Título.mp4
│  └─ S01E02 - Título.mp4
├─ Season 02\
│  ├─ S02E01 - Título.mp4
│  └─ S02E02 - Título.mp4
```

Os arquivos são ordenados por temporada e episódio. Antes do primeiro episódio de cada temporada, o `tg-upload` publica o separador correspondente, a menos que seja usado `--no-season-header`.

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

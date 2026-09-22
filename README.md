# tg-upload

Uploader em lote para Telegram usando Telethon, voltado a uma biblioteca organizada de **animes, desenhos, séries e filmes**.

O projeto preserva os arquivos originais, mantém estado local para não reenviar conteúdo por engano e automatiza legenda, catálogo, thumbnail e envio rápido.

## Como a biblioteca fica

A estrutura recomendada é manter categorias gerais para obras pequenas e médias:

```text
Free Media
├─ Animes
├─ Desenhos
├─ Séries
└─ Filmes
```

Franquias muito grandes podem continuar em canais próprios. O `tg-upload` evita repetir a hashtag da obra quando o destino não é um tópico geral de categoria.

Em um tópico geral, uma temporada fica assim:

```text
📺 PARASYTE - THE MAXIM — TEMPORADA 1
#Parasyte

#S01E01 - Nome do episódio [1080p • Multi Áudio]
#Parasyte
```

A hashtag da obra é canônica e reutilizada em todos os episódios. Isso deixa a busca do Telegram simples sem colocar o título inteiro em cada legenda.

Exemplos de tags geradas automaticamente:

```text
Attack on Titan                       → #Attack_On_Titan
Parasyte - The Maxim                  → #Parasyte
Frieren: Beyond Journey's End         → #Frieren
The 100 Girlfriends Who Really...     → #100_Girlfriends
```

A tag escolhida fica salva no `tg-upload.json` da obra. Para definir ou corrigir manualmente:

```powershell
tg-upload "C:\Videos\Attack on Titan" --to anime --search-tag Attack_On_Titan
```

## Legendas dos episódios

O programa reconhece `SxxExx` em qualquer posição do nome, ordena por temporada/episódio e monta a legenda automaticamente.

Formato:

```text
#S01E21 - Nome do episódio [1080p • Dublado]
#Nome_Da_Obra
```

O estado do áudio é inferido apenas quando as faixas possuem informação suficiente:

- uma faixa em português: `Dublado`;
- português + outra faixa: `Dual Áudio`;
- português + três ou mais faixas: `Multi Áudio`;
- áudio sem português + legenda em português: `Legendado`.

Se a metadata das faixas não permitir concluir com segurança, o rótulo é omitido em vez de inventado.

A qualidade vem do nome (`[720p]`, `[1080p]`, etc.) ou, quando necessário, do `ffprobe`.

## Thumbnails e reprodução no Telegram Web

MP4, M4V e MOV são enviados como vídeo reproduzível por padrão. **MKV é enviado como documento por padrão**, preservando exatamente o arquivo original e evitando conversões desnecessárias.

Para vídeos enviados inline, o uploader envia explicitamente:

- duração e resolução obtidas com `ffprobe`;
- `DocumentAttributeVideo` com streaming habilitado;
- thumbnail JPEG compatível com o Telegram.

A thumbnail segue esta prioridade:

1. **capa/pôster do catálogo da obra** (AniList ou TMDB);
2. um frame do próprio vídeo como fallback.

Assim episódios da mesma obra ficam visualmente consistentes quando enviados como vídeo. Filmes usam o pôster do próprio filme quando disponível.

Para MKV, a prioridade padrão é armazenamento fiel: o arquivo é enviado como documento, sem recodificação, mantendo HEVC/H.264, áudios, legendas, capítulos, anexos e demais dados exatamente como estão no arquivo local.

Para forçar qualquer outra mídia a ser enviada como arquivo/documento:

```powershell
tg-upload "C:\Videos\Minha Serie" --document
```

## Catálogo

- **Animes:** AniList.
- **Desenhos, séries e filmes:** TMDB.

A apresentação da obra e o pôster ficam associados ao `tg-upload.json` local da biblioteca.

Modos de catálogo:

```powershell
tg-upload "C:\Videos\Parasyte" --to anime --media-info auto
tg-upload "C:\Videos\Parasyte" --to anime --media-info refresh
tg-upload "C:\Videos\Parasyte" --to anime --media-info off
```

`auto` reutiliza o cache quando existe; `refresh` permite escolher novamente; `off` não publica apresentação.

Para TMDB, configure uma vez:

```powershell
tg-upload set-tmdb-token
```

A credencial fica somente no computador.

## Instalação

Requer Windows e Python 3.10+. `ffmpeg` e `ffprobe` são fortemente recomendados para metadata, classificação das faixas e thumbnails.

No PowerShell:

```powershell
$setup = Join-Path $env:TEMP "tg-upload-setup.ps1"
Invoke-WebRequest "https://raw.githubusercontent.com/sillasHead/tg-upload/main/setup.ps1" -OutFile $setup
powershell -NoProfile -ExecutionPolicy Bypass -File $setup
Remove-Item $setup -Force -ErrorAction SilentlyContinue
```

Depois, para atualizar:

```powershell
tg-upload update
```

O executável e os módulos ficam em `%LOCALAPPDATA%\telegram-media-upload`; credenciais, sessão e estado ficam em `%USERPROFILE%\.telegram-media-upload`.

## Primeiro uso

No primeiro envio real, o programa pede `api_id` e `api_hash` do Telegram, obtidos em `my.telegram.org` > **API development tools**.

Eles são armazenados localmente em:

```text
%USERPROFILE%\.telegram-media-upload\config.json
```

Ver configuração sem exibir o API hash:

```powershell
tg-upload config
```

## Destinos e tópicos

Crie atalhos para as categorias uma vez:

```powershell
tg-upload set-destination anime --channel -1001234567890 --topic "Animes"
tg-upload set-destination desenho --channel -1001234567890 --topic "Desenhos"
tg-upload set-destination serie --channel -1001234567890 --topic "Séries"
tg-upload set-destination filme --channel -1001234567890 --topic "Filmes"
```

Se canal/tópico forem omitidos, o programa abre menus pesquisáveis.

Uso depois disso:

```powershell
tg-upload "C:\Videos\Parasyte" --to anime
tg-upload "C:\Videos\Bob Esponja" --to desenho
tg-upload "C:\Videos\Minha Serie" --to serie
tg-upload "C:\Videos\Filmes\Meu Filme.mp4" --to filme
```

Para uma franquia grande em canal próprio:

```powershell
tg-upload set-destination one-piece --channel @meu_canal_onepiece
tg-upload "C:\Videos\One Piece" --to one-piece
```

Ver/remover destinos:

```powershell
tg-upload destinations
tg-upload remove-destination anime
```

O histórico diferencia canal e tópico, então a mesma mídia em dois destinos é tratada separadamente.

## Upload rápido

O padrão é **8 workers por arquivo**. Eles mantêm várias partes em voo pela conexão autenticada do próprio cliente; episódios diferentes não são enviados simultaneamente, preservando a ordem da série.

O progresso mostra porcentagem, tamanho, velocidade e ETA:

```text
S01E01:  42% (298.0/708.0 MiB) • 7.81 MiB/s • ETA 00:52
```

Alterar para uma execução:

```powershell
tg-upload "C:\Videos\Minha Serie" --upload-workers 4
```

Valores aceitos: `1` a `8`. Se houver falha no modo rápido, o programa tenta o modo compatível do Telethon.

`TG_UPLOAD_WORKERS` ou `"upload_workers"` no `config.json` podem sobrescrever o padrão.

## MKV e playback-fix

O comportamento normal é **preservar o MKV original e enviá-lo como documento**. Não há recodificação, remux ou redução de faixas no fluxo padrão.

Isso é especialmente indicado quando o Telegram será usado como armazenamento temporário: o arquivo enviado permanece com os mesmos bytes do arquivo local, inclusive HEVC Main 10, múltiplos áudios, legendas, capítulos e anexos.

O ajuste de compatibilidade para reprodução inline continua disponível apenas quando solicitado explicitamente:

```powershell
tg-upload "C:\Videos\Minha Serie" --playback-fix auto
```

Esse modo pode preparar uma cópia temporária quando a mídia exigir conversão. O original nunca é sobrescrito.

Sem essa opção, o padrão é equivalente a:

```powershell
tg-upload "C:\Videos\Minha Serie" --playback-fix off
```

Para guardar arquivos no Telegram e posteriormente apagar a cópia local, prefira o padrão `off`. Antes de apagar arquivos importantes, confirme que o upload terminou e que o arquivo pode ser baixado novamente.

## Envio em lote e estado

Uma estrutura típica:

```text
Minha Serie\
├─ Season 01\
│  ├─ S01E01 - Título.mp4
│  └─ S01E02 - Título.mp4
└─ Season 02\
   ├─ S02E01 - Título.mp4
   └─ S02E02 - Título.mp4
```

Enviar tudo recursivamente:

```powershell
tg-upload "C:\Videos\Minha Serie" --to serie
```

Prévia sem enviar:

```powershell
tg-upload "C:\Videos\Minha Serie" --dry-run
```

Reenviar arquivos já registrados:

```powershell
tg-upload "C:\Videos\Minha Serie" --force
```

Republicar separador de temporada:

```powershell
tg-upload "C:\Videos\Minha Serie" --force-header
```

Não publicar separadores:

```powershell
tg-upload "C:\Videos\Minha Serie" --no-season-header
```

Uploads concluídos ficam registrados em:

```text
%USERPROFILE%\.telegram-media-upload\state.json
```

Por isso, repetir o mesmo comando não reenvia automaticamente episódios já concluídos.

## Histórico das fontes da biblioteca

As origens das releases e os métodos usados para montar/baixar cada obra ficam registrados em:

`docs/media-source-history.md`

O histórico inclui, entre outros, **Psycho-Pass**, **Oggy e as Baratas Tontas** e **Coragem, o Cão Covarde**.

## Privacidade

API ID/hash, telefone, códigos de login, sessão do Telegram, token do TMDB, IDs privados e histórico de upload não precisam ser publicados no GitHub. O repositório contém apenas o código; os dados de execução permanecem no computador do usuário.

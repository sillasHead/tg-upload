# Apresentação automática de anime

Quando o destino é o atalho `anime`/`animes` ou um tópico cujo nome contém `anime`, o `tg-upload` pode publicar uma apresentação da obra **antes** do separador da primeira temporada.

No primeiro envio, se ainda não existir metadata local, o programa pesquisa o anime no AniList e mostra alguns candidatos. Depois de escolher um resultado, é possível:

- usar os dados como vieram;
- usar e editar os campos antes de salvar;
- voltar aos resultados;
- pesquisar outro nome;
- preencher tudo manualmente;
- pular a apresentação somente naquela execução.

Se o AniList estiver indisponível ou não retornar o anime correto, o fluxo continua oferecendo **Pesquisar outro nome**, **Preencher manualmente** e **Pular**. A API não é um ponto único de falha.

## Cache local

Ao confirmar os dados, eles são salvos ao lado da biblioteca em:

```text
Minha Serie\
├─ tg-upload.json
└─ mkv\
   ├─ S01E01 ...
   └─ S01E02 ...
```

Pastas genéricas como `mkv`, `mp4`, `videos` e `Season 01` são ignoradas ao localizar a raiz da obra. Assim, ao enviar `C:\Videos\Parasyte\mkv`, o arquivo fica em `C:\Videos\Parasyte\tg-upload.json`.

O `tg-upload.json` é a fonte final depois da primeira confirmação. Você pode editá-lo manualmente quando quiser.

Exemplo:

```json
{
  "version": 1,
  "anime": {
    "title": "Parasyte - The Maxim",
    "original_title": "寄生獣 セイの格率",
    "year": 2014,
    "episodes": 24,
    "status": "FINISHED",
    "genres": ["Action", "Horror", "Sci-Fi"],
    "synopsis": "...",
    "poster": "https://...",
    "source": "anilist",
    "source_id": 20623,
    "source_url": "https://anilist.co/anime/20623"
  }
}
```

`poster` também pode ser um caminho local, absoluto ou relativo à pasta da obra.

## Formato publicado

Além do catálogo, o uploader tenta extrair da sua própria mídia a qualidade e os idiomas de áudio que efetivamente serão enviados. O resultado fica próximo de:

```text
🎬 Parasyte - The Maxim
🇯🇵 寄生獣 セイの格率

📅 Ano: 2014
📺 Episódios: 24
✅ Status: Finalizado
🎭 Gêneros: Ação • Terror • Ficção científica
🔊 Áudio: Português • Japonês
🖥️ Qualidade: 1080p

📝 Sinopse:
...
```

Se houver poster, a apresentação é enviada como foto com legenda. Se o poster falhar ou estiver ausente, a mesma apresentação é enviada como texto.

## Evitar duplicatas

As apresentações já publicadas são registradas separadamente em:

```text
%USERPROFILE%\.telegram-media-upload\intros.json
```

Por isso, rodar o mesmo lote novamente não publica a descrição de novo.

Para republicar:

```powershell
tg-upload "C:\Videos\Parasyte\mkv" --to anime --force-info
```

## Trocar os dados escolhidos

Para ignorar o `tg-upload.json` atual e voltar ao seletor do catálogo:

```powershell
tg-upload "C:\Videos\Parasyte\mkv" --to anime --anime-info refresh
```

Se a apresentação já tiver sido publicada, `refresh` atualiza o arquivo local mas não duplica a mensagem. Para atualizar **e** publicar de novo:

```powershell
tg-upload "C:\Videos\Parasyte\mkv" --to anime --anime-info refresh --force-info
```

É possível definir o termo inicial da busca:

```powershell
tg-upload "C:\Videos\Parasyte\mkv" --to anime --anime-query "Kiseijuu"
```

Para desativar a apresentação:

```powershell
tg-upload "C:\Videos\Parasyte\mkv" --to anime --anime-info off
```

Também é possível persistir `"anime_info": "off"` no `config.json` ou usar `TG_ANIME_INFO=off`.

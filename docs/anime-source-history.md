# Histórico de fontes dos animes

Este arquivo registra **de onde veio cada release** e **qual método foi usado para montar a versão final**.  
A ideia é manter o mesmo padrão para os próximos animes, facilitando refazer uma biblioteca no futuro sem depender de memória.

## Padrão para novos registros

Para cada anime, registrar:

- **Anime / temporada**
- **Fonte principal**
- **Fontes auxiliares**
- **Links de origem**
- **Método utilizado**
- **Resultado final**
- **Observações importantes**

---

## Psycho-Pass (2012) — Temporada 1

### Fontes

| Uso | Release | Origem |
| --- | --- | --- |
| Base principal | Erai-raws | https://nyaa.si/view/1181787 |
| Fonte WEB auxiliar | EmmidRips | https://nyaa.si/view/1565097 |

### Método utilizado

1. A release da **Erai-raws** foi usada como base da versão final.
2. A versão **WEB da EmmidRips** foi usada como fonte auxiliar para a legenda em português.
3. A legenda PT-BR foi extraída e sincronizada com o timing da Erai-raws.
4. Foram corrigidas diferenças estruturais de timing entre as duas releases, incluindo trechos extras/cortes diferentes.
5. Depois do ajuste estrutural, os episódios foram revisados manualmente e receberam pequenos ajustes finos de entrada e duração das legendas quando necessário.
6. Legendas consecutivas com intervalos visuais muito pequenos foram ajustadas para evitar o efeito de “piscar” entre uma fala e outra.
7. A legenda final PT-BR foi adicionada ao MKV da Erai-raws por **remux**, sem recodificar vídeo ou áudio.
8. As faixas originais da Erai-raws foram preservadas; a legenda PT-BR final foi incluída como faixa adicional.
9. Para publicação no Telegram, os MKVs finais são enviados pelo **tg-upload** mantendo o arquivo original, sem nova recodificação no fluxo padrão.

### Resultado final

- Vídeo/base: **Erai-raws**
- Legenda PT-BR: **EmmidRips WEB**, sincronizada e revisada para a Erai-raws
- Container final: **MKV**
- Método de montagem: **remux**
- Recodificação de vídeo: **não**
- Recodificação de áudio: **não**
- Organização dos episódios: `S01E01 - Título do episódio.mkv`

### Observações

- A sincronização não foi tratada apenas como um deslocamento único para toda a temporada; alguns episódios exigiram ajustes específicos.
- A versão final deve ser considerada a referência para futuras cópias ou reconstruções desta temporada.

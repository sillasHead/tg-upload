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


### Detalhes da sincronização das legendas PT-BR

A legenda PT-BR da EmmidRips não encaixava diretamente na Erai-raws porque as duas versões tinham diferenças de montagem. O processo usado foi:

1. aplicar primeiro a correção estrutural de sincronização entre WEB e Erai-raws;
2. revisar manualmente os episódios;
3. aplicar pequenos atrasos adicionais no início das legendas para evitar que aparecessem antes da fala;
4. aumentar levemente a duração das legendas para evitar que desaparecessem cedo demais;
5. eliminar pequenos “piscas” entre legendas consecutivas.

#### Correção estrutural

O E01 foi usado para identificar o padrão inicial das diferenças entre as releases:

- antes do primeiro ponto de diferença: aproximadamente **-5,214 s**;
- depois do trecho adicional/intermediário: aproximadamente **-10,100 s**;
- havia uma diferença de cerca de **4,886 s** em torno do eyecatch;
- também existia diferença de aproximadamente **3 s** no trecho final;
- no E01, as entradas de legenda **255–257** da fonte WEB foram removidas porque não correspondiam corretamente à versão Erai-raws.

Na temporada, os deslocamentos estruturais encontrados ficaram em geral perto de:

- bloco inicial: cerca de **4,6 a 6,5 s**;
- bloco posterior: cerca de **9,6 a 10,5 s**.

Isso significa que não foi usado um único offset fixo para todos os episódios.

Correções pontuais importantes:

- **E08:** entradas **8–12** deslocadas em **-4,875 s**;
- **E12:** entrada **28** deslocada em **+4,975 s**, pois pertencia ao bloco anterior de sincronização.

#### Ajuste fino final por episódio

Depois da correção estrutural, foi aplicado um atraso adicional no **início** das legendas:

| Episódio | Atraso adicional |
| --- | ---: |
| S01E01 | +0 ms |
| S01E02 | +150 ms |
| S01E03 | +50 ms |
| S01E04 | +0 ms |
| S01E05 | +200 ms |
| S01E06 | +150 ms |
| S01E07 | +100 ms |
| S01E08 | +150 ms |
| S01E09 | +100 ms |
| S01E10 | +0 ms |
| S01E11 | +50 ms |
| S01E12 | **+300 ms** |
| S01E13 | +150 ms |
| S01E14 | +150 ms |
| S01E15 | +0 ms |
| S01E16 | +150 ms |
| S01E17 | +0 ms |
| S01E18 | +150 ms |
| S01E19 | +100 ms |
| S01E20 | +0 ms |
| S01E21 | +0 ms |
| S01E22 | +0 ms |

O **S01E02** serviu como principal referência visual para o ajuste fino da temporada.

#### Duração das legendas

Regra geral:

- fim da legenda: **+350 ms**.

Exceção:

- **S01E12:** fim da legenda: **+450 ms**.

O E12 recebeu esse ajuste maior porque o atraso de entrada estava bom, mas a legenda ainda desaparecia um pouco cedo.

#### Regra para intervalos muito pequenos

Depois dos ajustes de início/fim:

- se o intervalo resultante entre uma legenda e a próxima fosse **menor que 100 ms** — inclusive quando os tempos passassem a se sobrepor — o fim da legenda anterior era ajustado exatamente para o início da próxima;
- intervalos de **100 ms ou mais** eram preservados.

Objetivo: evitar o pequeno “piscar” visual entre duas legendas consecutivas sem transformar todos os intervalos naturais em texto contínuo.

#### Resultado da legenda final

A sequência final foi, portanto:

`EmmidRips WEB PT-BR`
→ correção estrutural por episódio
→ ajuste fino de início
→ extensão de duração
→ correção de gaps < 100 ms
→ revisão manual
→ remux como faixa SRT PT-BR no MKV da Erai-raws.

O remux apenas adicionou/substituiu a faixa de legenda desejada; **vídeo e áudio permaneceram sem recodificação**.

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

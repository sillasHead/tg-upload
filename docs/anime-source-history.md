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


---

## Psycho-Pass 2 (2014) — Temporada 2

### Fontes

| Uso | Release | Origem |
| --- | --- | --- |
| Base principal | Erai-raws — `Psycho-Pass 2 - 01 ~ 11 [1080p][Multiple Subtitle]` | Link de origem ainda não registrado |
| Fonte da legenda PT-BR | EmmidRips — NF WEB-DL DDP2.0 x264 DUAL AUDIO MULTI SUBS | Link de origem ainda não registrado |

### Método utilizado

1. A release da **Erai-raws** foi usada como base de vídeo da versão final.
2. A legenda final em português veio da versão **EmmidRips / Netflix WEB-DL**.
3. A legenda portuguesa já presente na Erai **não foi usada como texto final**, pois a tradução não foi considerada adequada.
4. Inicialmente foi testada a hipótese de diferenças estruturais entre as duas releases, como havia ocorrido na Temporada 1.
5. A validação manual mostrou que, na Temporada 2, o conteúdo principal das duas versões segue praticamente a **mesma timeline**.
6. A versão WEB possui apenas um pequeno trecho adicional de aproximadamente **3 segundos no final**, sem afetar o sincronismo do conteúdo principal.
7. Portanto, **não foi necessário aplicar offsets estruturais por blocos**.
8. Foi aplicado apenas um **delay global específico por episódio**, definido manualmente após testes visuais em vários pontos de cada episódio.
9. Não foi aplicada extensão geral da duração das legendas.
10. Depois do delay, foram corrigidos apenas gaps positivos menores que **100 ms**, fazendo o fim da legenda anterior coincidir exatamente com o início da próxima.
11. Os gaps encontrados eram praticamente todos de **83–84 ms**, sem overlaps na legenda original.
12. O texto da legenda PT-BR da EmmidRips foi preservado; apenas os timestamps foram alterados.

### Delays finais por episódio

| Episódio | Delay aplicado |
| --- | ---: |
| S02E01 | +250 ms |
| S02E02 | +500 ms |
| S02E03 | +50 ms |
| S02E04 | +50 ms |
| S02E05 | +400 ms |
| S02E06 | +400 ms |
| S02E07 | +400 ms |
| S02E08 | +100 ms |
| S02E09 | +450 ms |
| S02E10 | +500 ms |
| S02E11 | +100 ms |

### Regra de gaps

Após aplicar o delay específico de cada episódio:

- se o intervalo positivo entre o fim de uma legenda e o início da próxima fosse **menor que 100 ms**, o fim da legenda anterior era estendido exatamente até o início da próxima;
- gaps de **100 ms ou mais** eram preservados;
- não foi aplicada extensão geral como `+350 ms` ou `+450 ms`;
- não foram encontrados overlaps na legenda original;
- os gaps afetados ficaram em torno de **83–84 ms**.

### Resultado final

- Vídeo/base: **Erai-raws**
- Legenda PT-BR: **EmmidRips / Netflix WEB-DL**
- Sincronização estrutural por blocos: **não necessária**
- Ajuste utilizado: **delay global específico por episódio**
- Extensão geral da duração: **não**
- Correção de gaps: **sim, somente gaps <100 ms**
- Texto da legenda: **preservado integralmente**
- Nome final das legendas: `Psycho-Pass.S02E01.PT-BR.srt` até `Psycho-Pass.S02E11.PT-BR.srt`
- Container final pretendido: **MKV**
- Método de montagem pretendido: **remux**
- Recodificação de vídeo: **não**
- Recodificação de áudio: **não**

### Observações

- A primeira tentativa de sincronização por múltiplos blocos foi descartada após os testes manuais mostrarem que as duas versões tinham praticamente o mesmo timing.
- O ajuste fino foi feito episódio por episódio, porque diferenças de aproximadamente 50–500 ms eram perceptíveis visualmente.
- O S02E01 foi usado como referência inicial e fechou em **+250 ms**.

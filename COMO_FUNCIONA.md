# Como funciona o simulador LPC

Este documento explica **o problema** que o projeto estuda (correção de erros com um
código de produto 4x4) e **como o código** implementa a simulação. Para instalar e
executar, veja o [README.md](README.md).

---

## 1. O problema

### 1.1 Por que corrigir erros

Quando bits são guardados numa memória ou enviados por um canal, alguns podem ser
invertidos (0 vira 1 ou 1 vira 0) por ruído, radiação ou falha de hardware. Um **código
corretor de erros** acrescenta bits redundantes aos dados. Na leitura, essa redundância
permite **detectar** e, em muitos casos, **corrigir** os bits invertidos.

A pergunta que o projeto responde é:

> Dado um código e um algoritmo de decodificação, **quantos padrões de *n* erros o
> decodificador deixa de corrigir?**

Para responder sem estimativa estatística, o simulador testa **todos** os padrões
possíveis de *n* erros. É uma simulação exaustiva, não um Monte Carlo.

### 1.2 O bloco básico: Hamming(7,4) estendido

Cada linha e cada coluna de dados é protegida por um **código de Hamming(7,4)** mais um
**bit de paridade geral**, formando 8 bits (Hamming estendido, (8,4)):

| Bit | Fórmula |
|---|---|
| `C0` | `d1 ⊕ d2 ⊕ d3` |
| `C1` | `d0 ⊕ d2 ⊕ d3` |
| `C2` | `d0 ⊕ d1 ⊕ d3` |
| `P`  | `d0 ⊕ d1 ⊕ d2 ⊕ d3 ⊕ C0 ⊕ C1 ⊕ C2` |

Na leitura, os bits `C` são recalculados a partir dos dados recebidos e comparados com
os `C` recebidos. A diferença é a **síndrome** `(s0, s1, s2)`. Lida como número binário
(`s0·4 + s1·2 + s2`), ela é o **endereço do erro**. Cada bit sozinho produz um endereço
diferente:

| Endereço | Bit com erro |
|---|---|
| 0 | nenhum |
| 1 | `C2` |
| 2 | `C1` |
| 3 | `d0` |
| 4 | `C0` |
| 5 | `d1` |
| 6 | `d2` |
| 7 | `d3` |

A paridade `P` distingue quantos erros houve:

| Síndrome | Paridade `sP` | Interpretação | Sinal no código |
|---|---|---|---|
| = 0 | 0 | sem erro | — |
| ≠ 0 | 1 | **erro simples** (número ímpar de erros): o endereço aponta o bit | `SE` |
| ≠ 0 | 0 | **erro duplo** (número par ≥ 2): detectado, mas o endereço não localiza os bits | `DE` |
| = 0 | 1 | erro só no próprio `P` | — |

Sozinho, um Hamming estendido corrige 1 erro e detecta 2. Com 3 erros na mesma linha,
ele "corrige" o bit errado, porque o padrão parece um erro simples.

### 1.3 O código de produto LPC 4x4

O LPC organiza 16 bits de dados numa matriz 4x4 e aplica o Hamming estendido **em cada
linha e em cada coluna**:

```
            col0 col1 col2 col3 | Cr0 Cr1 Cr2 | Pr
    linha0   D    D    D    D   |  .   .   .  | .
    linha1   D    D    D    D   |  .   .   .  | .
    linha2   D    D    D    D   |  .   .   .  | .
    linha3   D    D    D    D   |  .   .   .  | .
    ------------------------------
    Cc0      .    .    .    .
    Cc1      .    .    .    .
    Cc2      .    .    .    .
    Pc       .    .    .    .
```

- 16 bits de dados `D`
- 12 bits de verificação de linha `Cr` e 4 paridades de linha `Pr`
- 12 bits de verificação de coluna `Cc` e 4 paridades de coluna `Pc`
- **48 bits no total** (taxa 1/3)

Não há "verificação da verificação" (o canto inferior direito fica vazio). Cada bit de
dado pertence a uma linha e a uma coluna, então tem **duas chances** de ser corrigido.
É isso que torna o código mais forte do que os Hamming isolados: um padrão que confunde
a linha pode ser resolvido pela coluna, e vice-versa. Por isso a decodificação é
**iterativa**: corrige linhas, recalcula, corrige colunas, recalcula, e assim por diante.

### 1.4 O que se quer medir

Há várias formas de montar esse decodificador iterativo. O projeto compara:

- **4 modelos de correção**: o que pode ser corrigido e com que cautela (seção 3.2);
- **4 estratégias de laço**: em que ordem linhas e colunas são processadas (seção 3.1);
- **número de iterações** do AlgSE;
- **um passo final AlgDE**, que tenta resolver erros duplos cruzando linhas e colunas.

Para cada combinação, e para cada *n* de 0 até o máximo, conta-se quantos dos
C(48, *n*) padrões terminam com a matriz `D` diferente da original.

---

## 2. Visão geral do código

```
src/lpc_sim/
├── lpc.py               Lpc: codifica os 16 bits de dados na palavra de 48 bits
├── lpc_with_error.py    LpcWithError: palavra recebida + erros + síndromes
├── decoder_lpc.py       algoritmos AlgSE (4 laços x 4 modelos) e AlgDE
├── simulation_system.py gera todos os padrões de erro, decodifica e conta falhas
├── enums.py             LoopType e CorrectionModel
├── exceptions.py        InvalidErrorPositionError
└── cli.py               argumentos de linha de comando e exportação CSV
```

O fluxo de **um** teste de decodificação:

```
  Lpc(D)                        palavra correta (48 bits)
     │
     ▼
  LpcWithError(lpc, padrão)     inverte os bits do padrão e calcula as síndromes
     │
     ▼
  decoding_se(...)              AlgSE: correções Hamming iterativas em linhas/colunas
     │
     ├── D == original? ── sim ──► sucesso
     │
     ▼ não  (conta em errorSeDecoding)
  decoding_de(...)              AlgDE: votação cruzada para erros duplos
     │
     ├── D == original? ── sim ──► corrigido pelo AlgDE
     │
     ▼ não  (conta em errorDeDecoding = falha final)
```

Esse fluxo está em `decode_pattern()`, em
[simulation_system.py](src/lpc_sim/simulation_system.py). Os modos sequencial e paralelo
usam a mesma função.

---

## 3. Os módulos em detalhe

### 3.1 `lpc.py`: codificação

`Lpc(data_bits)` copia a matriz 4x4 para `D` e calcula `Cc`/`Pc` (colunas) e `Cr`/`Pr`
(linhas) com as fórmulas da seção 1.2. `is_equal()` compara **somente** `D`, porque o que
importa no fim é se os dados foram recuperados. Um erro que sobra num bit de verificação
não conta como falha.

Exemplo com dados arbitrários (saída real de `print(Lpc(...))`):

```
[1 0 1 1][0 1 0] 0     ← linha 0: dados | C0 C1 C2 | P
[0 1 1 0][0 1 1] 0
[1 1 0 0][1 1 0] 0
[0 0 0 1][1 1 1] 0
[1 0 1 1]              ← Cc0 de cada coluna
[0 1 1 0]              ← Cc1
[1 1 0 0]              ← Cc2
 0 0 0 1               ← Pc
```

### 3.2 `lpc_with_error.py`: a palavra recebida

`LpcWithError(lpc, padrão)` recria a palavra correta, inverte os bits listados em
`padrão` e chama `recompute_control_variables()`. Esse método roda sempre na mesma
ordem:

1. `recompute_check_bits_and_parity()`: recalcula `recCr`, `recPr`, `recCc`, `recPc`
   a partir de `D`;
2. `compute_syndromes()`: `sCr`, `sPr`, `sCc`, `sPc` valem 1 onde o recebido difere do
   recalculado. `sCrq`/`sCcq` indicam se a síndrome Hamming da linha/coluna é ≠ 0;
3. `compute_error_address()`: `EAr`/`EAc` são o endereço `s0·4 + s1·2 + s2`;
4. `compute_se_de()`: `SEr`/`SEc` (erro simples) e `DEr`/`DEc` (erro duplo), pela
   tabela da seção 1.2.

**Mapa das 48 posições de erro.** A ordem vem do Java original (repare que `Pc` vem antes
de `Cc`):

| Posições | Bit | Índice |
|---|---|---|
| 0–15  | `D[linha][coluna]` | `linha = p // 4`, `coluna = p % 4` |
| 16–27 | `Cr[linha][bit]` | `p−16`: `linha = //3`, `bit = %3` |
| 28–31 | `Pc[coluna]` | `p − 28` |
| 32–43 | `Cc[bit][coluna]` | `p−32`: `bit = //4`, `coluna = %4` |
| 44–47 | `Pr[linha]` | `p − 44` |

Exemplo: um erro na posição 5 inverte `D[1][1]`. Saída real de `print(LpcWithError(...))`:

```
   D0 1 2 3 C0 1 2 P sC0 1 2 sP sCq SE DE Add
D1 [0 0 1 0][0 1 1]0  [1 0 1  1] 1  [1 0] 5    ← linha 1: SE, endereço 5 = d1
...
sC0[0 1 0 0]
sC2[0 1 0 0]
sP [0 1 0 0]
SE [0 1 0 0]                                   ← coluna 1: SE
Add 0 5 0 0                                    ← endereço 5 = linha 1
```

A linha 1 e a coluna 1 apontam para o mesmo bit, `D[1][1]`.

### 3.3 `decoder_lpc.py`: AlgSE (erro simples)

`decoding_se(iterações, laço, modelo, lpc)` escolhe uma das quatro estratégias de laço.
Todas usam duas operações:

- `_apply_hamming_on_rows`: em cada linha com `SE`, corrige o bit que o endereço aponta;
- `_apply_hamming_on_columns`: o mesmo, nas colunas.

Numa passada, todas as síndromes são lidas **antes** de qualquer correção. As variáveis
de controle só são recalculadas no fim, e só se algum bit mudou.

#### Estratégias de laço (`LoopType`)

| Laço | O que faz | Nº de meias-passadas |
|---|---|---|
| `BasicLoop` | linhas, depois colunas, repetido | `2·(it+1)` |
| `InvertLoop` | alterna colunas, linhas, colunas... (começa pelas colunas) | `it+1` |
| `PriorityLoop` | a cada volta, processa só o lado (linhas ou colunas) com mais `SE`; empate vai para colunas | até `2·it+2` |
| `FairPriorityLoop` | a cada volta, processa os dois lados, começando pelo que tem mais `SE` | até `2·(it+1)` |

`it` é o número de iterações (`iterations_se`). Nos laços com prioridade, uma volta sem
nenhum `SE` é pulada (`continue`, não `break`), como no Java.

#### Modelos de correção (`CorrectionModel`)

Os modelos variam em duas propriedades:

| Modelo | Corrige bits `C`? | Exige confirmação cruzada? |
|---|---|---|
| `DCO`  (Data Correction Only) | não | não |
| `DCOC` (… Cross-check) | não | **sim** |
| `DRC`  (Data and Redundancy Correction) | **sim** | não |
| `DRCC` (… Cross-check) | **sim** | **sim** (só para dados) |

- **Corrigir bits `C`** (endereços 4, 2, 1): o DRC/DRCC também conserta `C0`/`C1`/`C2`.
  Isso limpa síndromes falsas e ajuda nas passadas seguintes.
- **Confirmação cruzada**: antes de inverter `D[r][c]` a partir da linha `r`, o decodificador
  verifica se a **coluna** `c` também acusa algo (`SE`, `DE` ou paridade ≠ 0), e o mesmo
  vale no sentido inverso. Com isso ele evita "corrigir" um bit certo quando a linha tem
  3 erros disfarçados de 1. No DRCC, a correção dos bits `C` não passa por essa verificação.

No Java eram oito métodos quase idênticos. Aqui eles foram unificados em
`_apply_hamming()`, que recebe essas duas propriedades como parâmetro.

### 3.4 `decoder_lpc.py`: AlgDE (erro duplo)

O AlgDE só roda se o AlgSE não recuperou `D`. Ele usa a informação que o Hamming não usa
sozinho: uma linha com `DE` tem síndrome ≠ 0, e cada síndrome pode ser gerada por
exatamente **3 pares** de bits da linha. A tabela `TAB` lista esses pares. Nela, as
posições 0–3 são dados e 4–6 são `C0`–`C2`.

Para cada linha (e depois cada coluna) com `DE`:

1. para cada par candidato, verifica se os bits de dado do par caem em colunas (ou
   linhas) que **também** estão em `DE`. Bits `C` do par não precisam de confirmação;
2. se o par é compatível, cada bit de dado dele recebe **1 voto**;
3. se nenhum par foi compatível e a síndrome é um endereço de dado (3, 5, 6, 7), o bit
   apontado recebe 1 voto. A hipótese é 1 erro de dado mais 1 erro em `P`.

No fim, só são invertidos os bits com **exatamente 2 votos**, ou seja, apontados tanto
pela análise da linha quanto pela da coluna.

> **Observação sobre a `TAB`.** Pelo mapa da seção 1.2, o XOR dos endereços de cada par
> deveria ser igual à síndrome da entrada. Duas entradas não satisfazem isso:
> na síndrome 3, o par `(1, 3)` gera 5⊕7 = 2 (o esperado seria `(1, 2)`: 5⊕6 = 3); na
> síndrome 4, o par `(1, 5)` gera 5⊕2 = 7 (o esperado seria `(1, 6)`: 5⊕1 = 4). A tabela
> foi mantida **igual à do Java**, porque o objetivo da conversão é reproduzir o original.
> Se for um erro do original, ele afeta só a eficácia do AlgDE nesses casos.

### 3.5 `simulation_system.py`: a simulação exaustiva

`LpcSimulationSystem` guarda a configuração de um teste (modelo, laço, *n*, iterações) e os
contadores:

| Contador | Significado |
|---|---|
| `numberOfDecodigns` | padrões testados = C(48, *n*) (a grafia errada vem do Java) |
| `errorSeDecoding` | padrões em que `D` continuou errado **após o AlgSE** |
| `errorDeDecoding` | padrões em que `D` continuou errado **após AlgSE + AlgDE** (falha final) |

`error_generator()` percorre `itertools.combinations(range(inicio, fim), n)`, na mesma
ordem da recursão do Java. Para cada padrão, chama `decode_pattern()` e imprime o
progresso em %.

**Por que os dados iniciais são todos zero.** O código é linear e o decodificador só
decide com base nas síndromes, que dependem apenas do padrão de erro. Por isso o
resultado não depende da palavra transmitida, e a matriz de zeros basta.

**Varredura** (`run_sweep` + `SweepConfig`): os laços aninhados seguem a ordem do Java,
modelo → laço → *n* → iterações.

| Preset | Modelos | Laços | *n* | Iterações |
|---|---|---|---|---|
| `main`  | DCOC | InvertLoop | 0–7 | 0–7 |
| `main2` | os 4 | os 4 | 0–5 | 0–3 |

**Custo.** C(48, *n*) cresce rápido: 1, 48, 1 128, 17 296, 194 580, 1 712 304, 12 271 512
e 73 629 072 para *n* = 0 a 7. O preset `main` faz cerca de 703 milhões de decodificações.
Por isso existe o modo paralelo (`--workers`), que divide as combinações pelos dois
primeiros índices (C(48,2) = 1 128 fatias) entre processos e soma os contadores.

### 3.6 `cli.py`: linha de comando

Monta um `SweepConfig` a partir de um preset e sobrescreve o que foi passado por argumento
(`--correction-model`, `--loop-type`, `--max-errors`, `--max-iterations`,
`--error-interval`, `--workers`). Com `--csv ARQUIVO`, grava uma linha por teste com os
três contadores.

---

## 4. Como ler a saída

```
AlgSE1_DCOC (InvertLoop) + AlgDE : #Errors=3
0 1 2 3 ... 99 100
	numberOfDecodigns = 17296
	errorSeDecoding = 448
	errorDeDecoding = 192
```

Leitura: com 1 iteração de AlgSE, modelo DCOC e laço InvertLoop, foram testados todos os
17 296 padrões de 3 erros. O AlgSE sozinho falhou em 448. Desses, o AlgDE recuperou 256 e
sobraram 192 falhas.

Resultados reais do preset `main` (tirados de
[tests/golden/java_main_e3_i7.txt](tests/golden/java_main_e3_i7.txt)):

| *n* | Iterações | Padrões | Falhas após SE | Falhas finais |
|---|---|---|---|---|
| 1 | 0 | 48 | 0 | 0 |
| 2 | 0 | 1 128 | 88 | 88 |
| 2 | ≥ 1 | 1 128 | 0 | 0 |
| 3 | 0 | 17 296 | 3 728 | 3 472 |
| 3 | 1 | 17 296 | 448 | 192 |
| 3 | ≥ 2 | 17 296 | 256 | **0** |

Esses números mostram o que o projeto quer evidenciar:

- **1 erro** é sempre corrigido, mesmo sem iterar;
- **2 erros** exigem pelo menos uma iteração extra, para que o outro lado (linhas ou
  colunas) termine o trabalho;
- **3 erros**: a partir de 2 iterações, sobram 256 padrões que o AlgSE não resolve, e o
  **AlgDE resolve todos**. Sem o AlgDE, o decodificador falharia nesses 256 casos.

---

## 5. Relação com o projeto Java original

O código é uma conversão de um projeto Eclipse em Java. A saída é verificada **byte a
byte** contra execuções do Java (arquivos em `tests/golden/`). Por isso algumas
peculiaridades do original foram mantidas de propósito: o nome `numberOfDecodigns`, o
progresso que não chega a 100 % com `--error-interval` começando acima de 0, o `continue`
no PriorityLoop e a `TAB` da seção 3.4. A lista completa e o mapeamento Java → Python
estão no [README.md](README.md).

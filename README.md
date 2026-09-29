# LPC — Simulação de decodificação (conversão Java → Python)

Conversão do projeto Eclipse `LPC` (Java SE 12) para Python 3.12+, pronta para o VS Code.
Simula, de forma exaustiva, todos os padrões de *n* erros num código de produto LPC 4x4
(Hamming(7,4) + paridade em linhas e colunas, 48 bits) e conta as falhas dos algoritmos
AlgSE (erro simples) e AlgDE (erro duplo).

## Estrutura

```
lpc-python/
├── .vscode/
│   ├── extensions.json      # extensões recomendadas (Python, Pylance, Ruff)
│   ├── launch.json          # F5: main, main paralelo, main2, teste rápido
│   └── settings.json        # pytest, PYTHONPATH p/ Pylance, formatação
├── src/lpc_sim/
│   ├── __init__.py          # API pública
│   ├── __main__.py          # python -m lpc_sim
│   ├── cli.py               # argumentos de linha de comando (substitui editar main)
│   ├── enums.py             # LoopType, CorrectionModel (antes: int 0..3)
│   ├── exceptions.py        # LpcError, InvalidErrorPositionError
│   ├── lpc.py               # Lpc.java
│   ├── lpc_with_error.py    # LpcWithErrror.java
│   ├── decoder_lpc.py       # DecoderLpc.java
│   └── simulation_system.py # LpcSimulationSystem.java
├── tests/
│   ├── golden/              # saídas geradas executando o código JAVA original
│   ├── test_lpc.py
│   ├── test_decoder.py
│   └── test_simulation.py
├── pyproject.toml
├── requirements.txt         # vazio de dependências (só biblioteca padrão)
└── requirements-dev.txt     # pytest, ruff, mypy
```

## Instalação e execução

Windows (PowerShell):

```powershell
cd lpc-python
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt   # opcional: só para testes/lint
pip install -e .                      # opcional: habilita o comando `lpc-sim`
python -m lpc_sim
```

Linux / macOS:

```bash
cd lpc-python
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install -e .
python -m lpc_sim
```

Sem `pip install -e .`, rode com `PYTHONPATH=src python -m lpc_sim` (no PowerShell:
`$env:PYTHONPATH="src"; python -m lpc_sim`). O `launch.json` já define o `PYTHONPATH`.

No VS Code: abra a pasta `lpc-python`, `Ctrl+Shift+P` → **Python: Select Interpreter** →
escolha `.venv`, depois **F5** e escolha uma das configurações. Os testes aparecem na aba
**Testing** (ícone do frasco).

### Comandos úteis

```bash
python -m lpc_sim                               # = main() do Java
python -m lpc_sim --preset main2                # = main2() do Java
python -m lpc_sim --workers 0                   # main em paralelo (todos os núcleos)
python -m lpc_sim --max-errors 3 --max-iterations 2
python -m lpc_sim --correction-model DCO DRCC --loop-type BasicLoop PriorityLoop
python -m lpc_sim --error-interval 0 16         # só bits de dados
python -m lpc_sim --preset main > resultado.txt # salvar saída (texto, igual ao console)
python -m lpc_sim --max-errors 5 --csv dados.csv > resultado.txt  # + dados em CSV
pytest                                          # testes rápidos (~7 s)
pytest -m slow                                  # testes longos (~1 min)
ruff check . && mypy src
```

## Mapeamento Java → Python

| Java | Python | Observação |
|---|---|---|
| `class Lpc` | `lpc_sim.lpc.Lpc` | atributos `D`, `Cr`, `Pr`, `Cc`, `Pc` mantidos |
| `isEqual(Lpc)` | `Lpc.is_equal()` | compara só `D`; não virou `__eq__` (ver abaixo) |
| `toString()` | `__str__()` | formato idêntico, caractere a caractere |
| `class LpcWithErrror` | `LpcWithError` + alias `LpcWithErrror` | nome corrigido, alias p/ comparação |
| `recomputeControlVariables`, `computeSE_DE`... | `recompute_control_variables`, `compute_se_de`... | snake_case |
| `int[][]`, `boolean[]` | `list[list[int]]`, `list[bool]` | |
| `throw new Exception(...)` | `InvalidErrorPositionError` | mesma mensagem |
| `class DecoderLpc` (só `static`) | módulo `decoder_lpc` | funções de módulo |
| 8 × `ApplyHammingOn{Rows,Columns}{DCO,...}` | `_apply_hamming(lpc, model, on_rows=...)` | unificados (ver abaixo) |
| `int loopType` / `int correctionModel` | `LoopType` / `CorrectionModel` (`IntEnum`) | aceitam também 0..3 |
| `switch` | `match` / dicionários | |
| campos `static` de `LpcSimulationSystem` | instância de `LpcSimulationSystem` | sem estado global |
| recursão `errorGenerator` | `itertools.combinations` | mesma ordem lexicográfica |
| `main` / `main2` | presets `main` / `main2` (`MAIN_CONFIG`, `MAIN2_CONFIG`) | |
| `System.out.print/println` | `print(..., file=out)` | `flush=True` no progresso |
| `.project`, `.classpath`, `.settings` | `pyproject.toml`, `.vscode/` | JavaSE-12 → Python ≥ 3.12 |

## Decisões de conversão e suposições

1. **Nomes de domínio fora da PEP 8.** `D`, `Cr`, `SEr`, `EAc`, `sPc` etc. são a notação do
   código corretor de erros. Renomeá-los dificultaria a comparação com o Java; as regras
   `N8xx` do Ruff para eles estão desativadas no `pyproject.toml`. Métodos, funções e
   variáveis locais seguem snake_case.
2. **Unificação dos 8 métodos de correção.** Eram cópias que só variavam em "corrige bits
   de redundância?" (DRC/DRCC) e "exige verificação cruzada?" (DCOC/DRCC). Essas duas
   propriedades foram para `CorrectionModel` e há um só núcleo. Detalhes preservados: as
   síndromes são lidas do estado anterior à passada; `recompute_control_variables()` só
   roda se algum bit mudou; no DRCC a correção dos bits C **não** tem verificação cruzada.
3. **`switch` sem `default`.** Um código de laço/modelo desconhecido não faz nada, como no
   Java. A CLI valida as opções, então isso só ocorre via API.
4. **`is_equal` em vez de `__eq__`.** O método original compara apenas `D`; um `__eq__`
   sugeriria igualdade total e tornaria o objeto não-hashable.
5. **Posições de erro negativas.** No Java geravam `ArrayIndexOutOfBoundsException`; em
   Python, índices negativos acessariam a lista pelo fim e inverteriam um bit errado em
   silêncio. Agora levantam `InvalidErrorPositionError`, como posições ≥ 48.
6. **`setNumberOfErrors`.** Os dois laços em `long` calculavam exatamente C(n, k); foi usado
   `math.comb`, que dá o mesmo resultado (inclusive 0 quando k > n).
7. **Peculiaridades mantidas de propósito** (alterariam a saída se "corrigidas"):
   - `percentageLP` nunca é zerado entre testes: um teste de 0 erros depois de outro que
     terminou em 100 % não imprime progresso;
   - `setErrorInterval(inicio, fim)` calcula C(`fim`, n), não C(`fim − inicio`, n): com
     `inicio > 0` o progresso não chega a 100 % (os contadores continuam corretos);
   - o texto impresso `numberOfDecodigns` mantém o erro de digitação do original;
   - `decoding_de` não recalcula as variáveis de controle ao final;
   - `PriorityLoop` executa `2·iterações + 2` voltas e usa `continue`, não `break`.
8. **Chamada sem `set_number_of_errors`.** No Java, dividir por `numCombinations = 0` em
   `double` imprimiria um valor absurdo; em Python gera `ZeroDivisionError`. Os roteiros
   `main`/`main2` sempre chamam o setter, então isso não acontece no uso normal.

O projeto original **não** tem arquivos de configuração, leitura de arquivos, banco de dados
nem chamadas de API; toda a entrada está no código (`main`). Por isso a única "integração"
convertida é a configuração do projeto Eclipse, substituída por `pyproject.toml` e `.vscode/`.

## Desempenho

Python puro é cerca de 30 vezes mais lento que a JVM neste tipo de laço numérico. Medido
aqui: cerca de 28 µs por decodificação. O `main` completo faz cerca de 703 milhões de
decodificações (C(48, 0..7) × 8 iterações), então:

| Execução | Tempo estimado |
|---|---|
| Java original | ~11 min |
| Python, `--workers 1` (padrão) | ~5,5 h |
| Python, `--workers 8` | ~45 min |

O modo paralelo (`ProcessPoolExecutor`, biblioteca padrão) fatia as combinações pelos dois
primeiros índices. Os contadores são idênticos aos do modo sequencial; só o progresso
avança em saltos. O padrão continua sequencial para que a saída seja idêntica à do Java.

## Verificação de equivalência

As classes Java originais foram executadas e suas saídas salvas em `tests/golden/`. Os
testes comparam a saída do Python **byte a byte** com essas saídas:

- `main2` com até 3 erros e 3 iterações (256 testes, 1,18 milhão de decodificações);
- `main` com até 3 erros e 7 iterações; intervalo de erro (10, 40);
- estado interno completo (`toString` após recepção, AlgSE e AlgDE) em 300 casos
  aleatórios com dados ≠ 0, até 10 erros, posições repetidas e códigos inválidos.

Fora da suíte, também conferi `main` com até 5 erros (3,85 milhões de decodificações) e
6.000 casos aleatórios de estado completo: tudo idêntico.

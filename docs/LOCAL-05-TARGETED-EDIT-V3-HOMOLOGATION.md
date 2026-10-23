# LOCAL-05 — Homologação Targeted Edit V3 (auditoria sem inferência)

Data: 23/10/2026. Projeto: oigorbrito/local. Gate atual: **BLOCKED_SOURCE_UNAVAILABLE**, não homologado.

## Evidências realmente inspecionadas
- Inventário completo da árvore Git da branch `experiment/local-restart-protocol-01`: nenhum runner, pacote, fixture ou resultado bruto do `local-bench-04` ou `Targeted Edit V3` está versionado. A árvore contém documentação de reconciliação e os workflows independentes.
- Busca dos arquivos de conversa/biblioteca: disponíveis transcrições PowerShell e handoffs `Texto colado (2).txt`, `Texto colado(6).txt`, `Texto colado(7).txt`. Nenhum arquivo executável do pacote V3 foi encontrado nessa busca.
- Handoff local registra pacote `LOCAL-BENCH-04 Targeted Edit V3` com **12/12 testes automatizados reportados**, mas não contém código para reproduzir nem prova de execução real com issues oficiais. Este é um reporte secundário, não um gate de eficácia.
- PILOT01/PILOT02 dos modelos Nemotron 4B e LFM2.5 2.6B usaram somente três issues SWE-bench Lite: `marshmallow-code__marshmallow-1343`, `marshmallow-code__marshmallow-1359`, `pvlib__pvlib-python-1072`. O resultado 0/3 por configuração/piloto é **validade estrutural de patch**, não resolução oficial.
- Falhas documentadas: retrieval de arquivos errados, truncamento em 2048 tokens no LFM e 2/3 do Nemotron no PILOT02, edições alheias, erros de sintaxe, normalização CRLF/LF afetando hashes. Não atribuir todos esses fenômenos à capacidade do modelo.

## Gate de homologação e resultado atual

| Gate | Evidência requerida | Estado |
|---|---|---|
| Fonte V3 | pacote, hashes, runner, dependências, fixtures disponíveis | **BLOCKED** |
| Proveniência | commit(s) base e identificadores de instâncias verificados com payload oficial | **NOT_VERIFIED** |
| Retrieval | `schema.py`, `fields.py`, `temperature.py` localizados por traceback/símbolos, sem patch-oráculo no prompt | **NOT_RUN** |
| Edição/patch | patch localizado, `git apply --check`, limites de caminho, não alteração de trechos não relacionados | **NOT_RUN** |
| Isolamento | referências-oráculo isoladas dos dados dos agentes, Docker, limite de recursos, execução sequencial | **NOT_RUN** |
| Avaliação independente | comandos oficiais realmente executados e logs PASS_TO_PASS/FAIL_TO_PASS persistidos | **NOT_RUN** |
| Integridade | artefatos byte a byte, SHA256, Unicode/newlines, ids e parâmetros | **NOT_RUN** |

## Decisão objetiva

**Não executar modelos, não repetir três issues, não chamar 12/12 de homologação real.** O bloqueio é acesso ao código e aos artefatos V3; não há uma falha funcional comprovada do runner atual porque seu executável não pôde ser inspecionado.

O próximo ato, sem inferência, é incorporar o ZIP/arquivos já existentes de `C:\\Users\\igorb\\Downloads\\local-bench-04\\local-bench-04` ou o artefato `LOCAL-BENCH-04 Targeted Edit V3` ao contexto de auditoria, mantendo cópia e hashes. A partir daí executar unicamente preflight/contratos locais, fixtures e avaliador independente com soluções-oráculo isoladas do input — sem reutilizar resultados para forçar um ranking.

PR #16 permanece draft. Não copiar esses dados para FineCore, não fazer merge/force push, não instalar modelos, não rodar inferências pagas.

## Verificação complementar de fontes (23/10/2026)

Busca ampliada por dados preexistentes, **sem inferência**:
- `local-eval-block05.zip` encontrado em anexos anteriores e aberto por inspeção de índice: contém 10 entradas (`src/local_eval/core.py`, `src/local_eval/adapters.py`, `src/local_eval/__main__.py`, `tests/test_core.py`, duas tarefas JSON e metadados), **não** o Targeted Edit V3. Tamanho do ZIP 8.157 bytes. Não usar esse avaliador distinto como evidência de homologação V3.
- As branches `experiment/local-repair-01`, `experiment/local-swebench-real-01`, `experiment/local-agent-tools-01` e `experiment/local-failure-gate-02` foram inspecionadas via árvores Git. Contêm scripts `ci/repair.py`, `ci/swebench_real.py` e `ci/agent_tools.py` conforme a branch, mas **nenhum arquivo identificado como pacote Targeted Edit V3**; esses scripts são experimentos de outro pipeline, não equivalentes sem prova de identidade.
- Persistem transcrições PowerShell e documentação dos pilotos, sem os bytes originais do V3 disponibilizados ao ambiente. O caminho local Windows registrado não é automaticamente acessível pela conexão GitHub.

**Gate mantém BLOCKED_SOURCE_UNAVAILABLE.** Única ação que desbloqueia auditoria de código do V3 é disponibilizar o pacote original, sua árvore ou upload com bytes verificáveis. Não presumir que outro projeto com nome `block05` seja o mesmo artefato.

## Atualização por fontes originais recebidas em 23/10/2026

**O bloqueio geral SOURCE_UNAVAILABLE foi parcialmente resolvido.** Foram inspecionados três ZIPs enviados diretamente pelo usuário. Dois ZIPs de ~184 MB possuem 15.319 entradas idênticas em conteúdo (CRC/tamanho), mas SHA-256 externos diferentes; outro contém runner inicial. SHA dos ZIPs (2), (3) e (1): `109b3b352056616e96a6d05819454ee0fababcac7f0a8a7b0e893f3932374711`, `52a808dd6cb8e3a0832537b358b53e31981bd01558044283499f1d40626f8e22`, `cfc4739ea1de7d222d9875ed356a90526b506525d77a17b46f288f8094ead6fd`.

Código efetivamente recuperado: `local_bench_04.py`, `local_bench_04_v2.py`, `file_edit_runner.py`, testes `test_contract.py` e `test_file_edit.py`, manifestos, checkpoints e 18 traces (6 PILOT01 + 6 PILOT02 + 6 file-edit-01). **Não se encontrou o executável específico do Targeted Edit V3**, distinto do runner de substituição integral.

- Execução local isolada **sem inferência**: `python -m unittest -v test_contract test_file_edit` → **9 PASS / 0 FAIL**; compilação sintática de cinco scripts → PASS.
- PILOT01: **0/6** `patch_validated`. PILOT02: **0/6** `patch_validated`.
- File-edit-01: LFM teve **3/3 OUTPUT_TRUNCATED**; Nemotron teve **1 OUTPUT_TRUNCATED, 1 PYTHON_SYNTAX_ERROR, 1 DIFF_CHECK_FAILED** com aviso de LF/CRLF.
- PILOT02: seis hashes de resposta divergentes em bytes persistidos, mas recuperados pela normalização CRLF→LF. File-edit-01: seis casos equivalentes. Não alegar integridade byte a byte.
- Manifesto de file-edit-01 mantém `requested_revision: main` e status `prepared_not_evaluated`; não demonstra execução do julgamento oficial.

**Estado atualizado:** `CONTRACTS_PASS_9_OF_9`; `HISTORICAL_FAILURES_VERIFIED`; `TARGETED_EDIT_V3_SOURCE_STILL_UNAVAILABLE`; `OFFICIAL_RESOLUTION_NOT_VERIFIED`. O código recuperado não autoriza promover V3 como homologado. Nenhum benchmark de modelo foi iniciado e a main permaneceu intacta.

## Gate de recuperação de arquivos — evidência primária ampliada
Em 23/10/2026 foram lidos os **18 JSON de trace originais** incluídos no ZIP `local-bench-04 (2).zip`: 6 de PILOT01, 6 de PILOT02 e 6 de file-edit-01. Inspeção automatizada verificou o array `selected_files` de cada trace e confrontou-o com o arquivo relevante identificado no histórico da issue:
- `marshmallow-code__marshmallow-1343`: relevante `schema.py`; selecionados `src/marshmallow/decorators.py`, `exceptions.py`, `warnings.py`; file-edit escolheu `decorators.py`.
- `marshmallow-code__marshmallow-1359`: relevante `fields.py`; selecionados `decorators.py`, `exceptions.py`; file-edit escolheu `decorators.py`.
- `pvlib__pvlib-python-1072`: relevante `temperature.py`; selecionados `pvlib/soiling.py`, `pvlib/version.py`; file-edit escolheu `soiling.py`.

**Resultado: 0/18 traces incluíram o arquivo relevante no conjunto `selected_files`**. Esta é uma falha reproduzível de *recall* da recuperação para as três issues, repetida por configuração e estratégia; não são 18 issues independentes. O código `file_edit_runner.py` confirma que o caminho editado é `selected[0]` e valida apenas a segurança do caminho, não sua relevância semântica. Os nomes esperados vêm da identificação anterior dos pontos de reparo, não de execução de oráculo funcional neste turno.

Conclusão causal delimitada: o protocolo antigo enviou contexto incorreto aos modelos, tornando a taxa de resolução oficial desses ensaios não interpretável como qualidade isolada do LLM. **Não implica que os modelos resolveriam os defeitos com recuperação correta.** Gate LOCAL-05/RETRIEVAL = FAIL_CONFIRMED. Gate V3_SOURCE = BLOCKED; nenhum novo modelo foi inferido, nenhum score antigo sobrescrito.

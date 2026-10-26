# LOCAL-WINNER-04 — competição local de programação (protocolo congelado)

**Base:** PR #35 / LOCAL-WINNER-03. **Estado:** plano de competição; nenhuma pontuação funcional autorizada enquanto os controles baseline/gold estiverem bloqueados.

## Universo e separação
Usar exclusivamente os oito casos do manifesto gerado por `experiments/local_winner01/select_cases.py` (SWE-bench Lite/dev, seed `LOCAL-WINNER-01-freeze-2026-10-26-v1`). Eliminatória: `pvlib__pvlib-python-1854`, `sqlfluff__sqlfluff-2419`, `pyvista__pyvista-4315`. Final holdout: `sqlfluff__sqlfluff-1625`, `pydicom__pydicom-1256`, `pylint-dev__astroid-1196`, `pvlib__pvlib-python-1707`, `pydicom__pydicom-901`. Não reutilizar resultados históricos como novas amostras.

Modelos candidatos, com IDs **a confirmar no Ollama local** antes de executar: Nemotron 4B; LFM2.5 2.6B; Qwen3.5 2B; Ministral 3 3B. Nome de família não prova tag, digest, quantização ou template. Registrar `ollama show`, digest do modelo, versão do Ollama, parâmetros e hardware antes da geração.

## Gates obrigatórios
1. Todos os oito casos precisam estar homologados pelo avaliador oficial: baseline com pelo menos um `FAIL_TO_PASS` reprovado; gold com todos `FAIL_TO_PASS` aprovados, nenhum `PASS_TO_PASS` regredido e parser válido; mesmos scripts, imagem fixada e isolamento.
2. Pré-voo local: verificar os quatro modelos presentes, contexto suportado, capacidade de executar inferência sem swapping excessivo, limite RAM/VRAM e ausência de tarefas locais concorrentes; qualquer alteração de modelo/quantização cria uma configuração distinta.
3. Executar eliminatória 4×3 = 12 gerações independentes, uma por par modelo/caso. Ordem por blocos alternados e pré-registrados para reduzir viés térmico. A entrada ao modelo contém apenas o enunciado original e a árvore de código no commit-base, nunca gold/test patch ou conteúdo do holdout.
4. Corrigir cada candidato em **contêiner descartável** idêntico ao controle, mantendo limites de recursos e avaliador oficial. Não executar patches gerados diretamente no host. Patch inválido, timeout ou modelo que não produza patch: fracasso contado, não excluído silenciosamente.
5. Promover os dois com mais tarefas resolvidas na eliminatória. Empate: acerto na primeira tentativa, tempo por tarefa corrigida e consumo; se persistir, reportar empate pré-registrado, não escolher subjetivamente.
6. Final: 2×5 casos, uma primeira tentativa e no máximo um reparo por caso. O reparo pode ver apenas feedback sanitizado da primeira tentativa, nunca gold ou testes privados; contabilizar tempo total de ambas as tentativas e manter métricas de primeira tentativa separadas.

## Orçamento e justiça
O mesmo teto de tokens de entrada/saída, contexto efetivo, temperatura, política de ferramentas, número de chamadas, timeout e acesso ao código deve ser definido **antes** de qualquer trial. Não comparar wall-clock de CPU-only remoto com wall-clock da GTX 1650 local. Reportar tokens/s, tempo end-to-end, RAM pico, VRAM pico, falha/timeout, sucesso estrito e consumo por tarefa correta. Parâmetros incompatíveis entre backends devem ser documentados, sem esconder desigualdades.

**Ranking:** (1) tarefas integralmente corrigidas, (2) acertos na primeira tentativa, (3) menor tempo total por correção, (4) viabilidade no i5-10300H / 16 GB RAM / GTX 1650 4 GB. Declarar separadamente vencedor *relativo* e modelo *aprovado para uso*. Amostra pequena: resultados exploratórios; não alegar superioridade geral ou significância estatística inexistente. Nenhum vencedor funcional se todos obtiverem zero.

## Artefatos de cada trial
Identidade caso/modelo/digest/quantização, commits base e ferramenta, SHA-256 da entrada e patch (patch privado), parâmetros exatos, duração, tokens, perfil de recursos, logs sanitizados de execução/avaliador, marcação estrita `FAIL_TO_PASS` e `PASS_TO_PASS`, primeira tentativa vs reparo, motivo de falha e hash de relatório. Fazer validação contra duplicatas. Merges exclusivamente manuais.

**Bloqueio atual:** WINNER-03A sem baseline/gold funcional homologados. Por isso este documento não autoriza declarar resultados ou iniciar inferência como se houvesse competição válida.

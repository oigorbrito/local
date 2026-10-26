# LOCAL-WINNER-01 — reconciliação offline antes de escolher o vencedor

O reconciliador é **somente leitura**: não chama Ollama, não executa testes de modelo, não abre Docker e nunca substitui evidências históricas. Ele identifica os relatórios locais já realizados, confirma relações por SHA-256, dá precedência ao rejudge HOME-MODEL-01 v2 **quando o relatório original está presente e com hash idêntico**, e não conta continuidades/reparos como tarefas novas. Relatórios não reconhecidos não viram resultados imaginados.

## Fontes já examinadas

- `ci/BREADTH-01-RESULTS.md`: seis tarefas sintéticas no CPU/CI; 5/6 para Phi-4 Mini, Qwen2.5-Coder 7B, Nemotron 4B e Ministral 3B. Qwen3.5 2B/4B teve captura vazia, não falha de programação comprovada.
- `docs/LOCAL-13-REAL-ISSUE-GATE.md`: 3 SWE-bench Lite dev já utilizados (marshmallow-1343, marshmallow-1359, pvlib-1072); Recall@2=3/3 é recuperação, não resolução.
- `benchmarks/nemotron4b/README.md` na branch LOCAL-27: um mesmo candidato Nemotron recuperado em dois relatos e validado 6/6; **um resultado independente, não dois**.
- Handoffs LOCAL-BENCH-04: V1–V3, Nemotron, LFM2.5, Qwen3.5 etc. Dados resumidos continuam documentais até conferência física dos artefatos de Windows.
- HOME-MODEL-01 v2: Phi-4 Mini 1/5, Qwen2.5-Coder 3B 0/5; `calendar_merge` reavaliado em 7/7 sem nova inferência.
- LOCAL-REAL-02 + RECOVERY-02: Qwen3.5 4B, Qwen2.5-Coder 7B e Phi-4 Mini sem solução integral da mesma issue. Não repetir.

## Executar somente auditoria local no Windows

Obtenha `reconcile.py` desta branch (ou faça fetch da PR). Salve em `D:\projetos\local-winner01\reconcile.py`. Depois:

```powershell
python -B D:\projetos\local-winner01\reconcile.py `
  --root "C:\Users\igorb" `
  --root "C:\Users\igorb\Downloads\local-bench-04" `
  --root "D:\projetos" `
  --output "D:\projetos\local-winner01\inventory-20261026.json"
```

O comando lê arquivos `report.json`, `rejudge-report.json`, `completion_report.json` e `score.json` de diretórios de evidências conhecidos. Não percorre arbitrariamente toda a máquina, não copia resposta bruta nem prompts e recusa sobrescrever um inventário anterior. Para um diretório fora dos padrões conhecidos, use `--evidence "C:\caminho\da\evidencia"`.

### Bloquear antes de gastar tokens

A próxima proposta de casos inéditos deve ser um arquivo JSON **array**, com uma linha por caso e identificadores completos:
```json
[
  {
    "case_id": "id-real-da-nova-issue",
    "source_repo": "owner/repo",
    "base_commit": "sha-completo",
    "prompt_sha256": "sha256-do-prompt",
    "oracle_sha256": "sha256-do-oraculo"
  }
]
```

Rode o reconciliador acrescentando `--tasks D:\projetos\candidatos.json` e uma saída nova. Casos já usados são recusados por identificador, alias ou hash de prompt/oráculo. Um caso marcado `NEW_UNVERIFIED` não está automaticamente aprovado: precisa de commit fixo, baseline quebrada e testes independentes funcionais.

## Seleção restante sem repetir baterias

**Prioridades experimentais, não ranking definitivo:** Nemotron 4B (V2/V3 e caso 6/6), LiquidAI LFM2.5 2.6B (boa velocidade na bateria curta), Qwen3.5 2B (3/3 em 23,35s na bateria curta; não validado na tarefa real) e Ministral 3 3B (5/6 BREADTH CPU, não validado no notebook). Não promover modelos por popularidade.

CI somente Python offline; nenhuma inferência executada. Branch experimental, PR Draft, merge manual.

# LOCAL-11 — Smoke real do Ollama no Windows (uma chamada controlada)

**Estado:** `OFFLINE_ORCHESTRATION_PASS / WINDOWS_GENERATION_NOT_RUN`.

## Implementação

`experiments/local07/windows_runtime_smoke.py` prepara uma única fixture Python em repositório Git temporário, chama o adaptador do LOCAL-09 uma vez (modelo fixo `nemotron-3-nano:4b`), valida o JSON e a aplicabilidade do patch e gera `local11-report.json`. O código gerado **não é executado** e a origem não é modificada. `adapter-report.json` e `candidate.patch` são gerados somente em caso de retorno válido; erro preserva o relatório parcial.

Não é benchmark de velocidade, nem resolução de uma issue SWE-bench. Falha de saída JSON, timeout, transporte e patch inválido permanecem distinguíveis no diagnóstico.

## Gate CI
[GitHub Actions #40053670669](https://github.com/oigorbrito/local/actions/runs/40053670669): compilação e **14/14 contratos offline aprovados**; nenhum modelo foi chamado. A validação de transporte real depende do Windows.

## Execução única no alvo
A partir de `D:\projetos\local`, com Ollama já instalado e acessível, e o checkout desta branch:

```powershell
git fetch origin
git switch experiment/local11-windows-smoke
git pull --ff-only origin experiment/local11-windows-smoke
python .\experiments\local07\windows_runtime_smoke.py --output-dir .\runs\local11 --model nemotron-3-nano:4b --timeout 180
Get-Content .\runs\local11\local11-report.json -Raw
```

Essa operação chama o modelo **uma vez**. Não instala ou faz pull de pesos, não toca outros projetos, não reexecuta V1/V2/V3 ou três issues SWE-bench. A tarefa diagnóstica é propositalmente nova, reduzida à prova da cadeia contrato→modelo→diff, não à comparação de modelos.

## Critérios
- `PATCH_APPLICABLE_NOT_GRADED` — integração real gerou patch sintaticamente válido e aplicável (não prova correção).
- `ADAPTER_FAILED` — observar stderr e separar conexão, contrato e edição; não atribuir automaticamente à competência do modelo.
- `ADAPTER_TIMEOUT` — falha de disponibilidade/latência no orçamento, não avaliação de qualidade.
- `SOURCE_INTEGRITY_FAILURE` — bloqueio de segurança.
- `INFRA_ERROR` — falha de pré-requisitos ou filesystem.

Resultados do Windows não foram fabricados nem simulados como êxito funcional.

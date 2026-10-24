# LOCAL-14 — Gate isolado de patches reais

**Estado:** infraestrutura implementada; **nenhuma issue real ainda resolvida/avaliada com testes oficiais**. O LOCAL-13 anterior fixou os três casos `dev` de SWE-bench Lite e obteve Recall@1=2/3 e Recall@2=3/3.

## O que faz
`experiments/local07/real_patch_gate.py` valida bytes e escopo de um diff Git sobre um checkout limpo fixado pelo SHA-base, usando worktree descartável e `git apply --cached --check`. Patches binários, multifile, renames, symlinks, alterações de modo, caminhos fora da allowlist, checkout sujo e base divergente são rejeitados.

O gate padrão **não executa código gerado**, nem Ollama, nem Docker. Retorna `PATCH_APPLICABLE_NOT_GRADED` quando apenas a aplicabilidade é comprovada.

## Testes públicos opcionais
A execução de testes exige `--run-tests`, imagem Docker já existente **fixada por digest sha256**, comando em allowlist e isolamento `--network none`, `--read-only`, usuário sem privilégios, `--cap-drop ALL`, `no-new-privileges`, memória/CPU/PIDs limitados, checkout montado somente leitura e filesystem temporário. Não constrói ou baixa imagens.

**Restrições:** isto é uma barreira de contenção, não uma garantia de isolamento absoluto de código malicioso. O operador deve usar host/VM descartável e runtime Docker confiável antes de executar patches não confiáveis. O gate opcional avalia testes públicos, não os testes ocultos oficiais do SWE-bench.

## Contrato de entrada
O arquivo JSON da issue deve conter exatamente:
```json
{"schema":1,"base_commit":"<sha40>","allowed_files":["src/module.py"]}
```
Os arquivos permitidos devem vir do LOCAL-13 **antes da geração**; nunca de `evaluator.json` nem do patch gold.

## Execução sem modelo, sem testes, sem alterar repositório
```powershell
python .\experiments\local07\real_patch_gate.py `
  --repo D:\snapshots\case-pinned `
  --issue-json D:\dados\case-gate.json `
  --patch D:\resultados\candidate.patch `
  --output D:\resultados\local14-triage.json
```

Separar métricas: recuperação, geração, contrato, aplicabilidade, testes públicos em sandbox e resolução oficial. Não computar taxa de resolução até executar um avaliador oficial com instâncias, versões e isolamento definidos.

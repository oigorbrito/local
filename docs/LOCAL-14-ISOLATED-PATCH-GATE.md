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

## Qualificação real de sandbox — Linux GitHub Actions, 24/10/2026

Foi implementado `experiments/local07/qualify_sandbox.py`, que usa uma imagem **já presente**, especificada por digest `@sha256:`, para executar apenas uma sonda Python inofensiva. A sonda verifica UID, capacidades efetivas do processo, escrita na raiz do contêiner e possibilidade de uma conexão externa. O comando é explícito e usa `--pull never`.

[Workflow real #40098567923](https://github.com/oigorbrito/local/actions/runs/40098567923): **PASS**. Observações: `uid=65534`, `cap_eff=0000000000000000`, `root_writable=false`, `outbound_network=BLOCKED`. O workflow obteve a imagem pública `python:3.12-slim` e **fixou o digest obtido antes da execução**. Esta sondagem ocorre num runner Linux controlado; não valida a segurança absoluta de containers, não testa execução de patches de modelos nem avalia resolução SWE-bench.

Contratos offline também cobrem observações negativas, ausência de download implícito na sonda e construção dos argumentos Docker. A aplicação do patch e a execução de testes públicos continuam sob opt-in; para código não confiável, recomenda-se VM/host descartável, sem credenciais sensíveis, além das restrições Docker.

### Qualificação no Windows (pendente, sem patch de modelo)

Após preparar uma imagem Python local com digest íntegro e verificar que `docker image inspect <referência@sha256>` a reconhece, executar:

```powershell
python .\experiments\local07\qualify_sandbox.py `
  --image "python@sha256:<digest-exato-ja-presente-localmente>" `
  --output .\runs\local14\sandbox-windows.json
Get-Content .\runs\local14\sandbox-windows.json -Raw
```

A referência de digest acima é marcador de exemplo, **não** um hash inventado; copiar o valor verdadeiro retornado por `docker image inspect`. `qualified=true` prova somente as propriedades observadas. Nunca montar senhas, tokens, Docker socket, diretórios pessoais ou repositórios reais não isolados.

# LOCAL-17 — Um defeito real e um ensaio controlado

## Caso pré-registrado

Identificador: oigorbrito__local-evidence-symlink-001
Repositório: oigorbrito/local
Commit-base fixo: a3e80e82788d798faa1a83b5a99762412cdaf61b
Git blob fixo: bfed49f4603e6f54c240dc633acc4aaf80e7ccda
Arquivo alvo: experiments/local07/reviewed_patch.py
Perfil: principal (nemotron-3-nano:4b), política 1.0.0

O defeito existe no código do próprio projeto, não em uma fixture
fabricada: a função _external_path recebe uma referência por symlink
para arquivo externo normal e a aceita indevidamente apesar da
proibição de links simbólicos. Este caso não é SWE-bench, BugsInPy
ou uma pontuação de benchmark oficial.

O enunciado apresentado à IA descreve o comportamento observado e
esperado, sem incluir patch de referência, posição exata da correção
ou oráculo privado. Fonte de verdade = commit e blob congelados.
É proibido substituir a tarefa após observar uma tentativa
malsucedida: um caso, uma tentativa, inclusive se a recuperação falhar.

## Windows: preparar sem inferência e sem alterar a main

Utilizar o worktree da PR #25 como runner e a cópia original do LOCAL
apenas para criar um checkout Git descartável no commit congelado:

~~~powershell
$ErrorActionPreference = "Stop"
$runner = "D:\projetos\local16-validacao-0b40a348"
$origin = "D:\projetos\local"
$trialId = [guid]::NewGuid().ToString("N").Substring(0, 8)
$trial = "D:\projetos\local17-issue-$trialId"
$session = "D:\projetos\local17-session-$trialId"
$baseCommit = "a3e80e82788d798faa1a83b5a99762412cdaf61b"

if ((git -C $runner status --porcelain)) { throw "RUNNER_WORKTREE_NOT_CLEAN" }
git -C $runner fetch origin feat/local16-model-profiles
if ($LASTEXITCODE -ne 0) { throw "RUNNER_FETCH_FAILED" }
git -C $runner switch --detach FETCH_HEAD
if ($LASTEXITCODE -ne 0) { throw "RUNNER_UPDATE_FAILED" }

git -C $origin fetch origin feat/local16-model-profiles
if ($LASTEXITCODE -ne 0) { throw "LOCAL_FETCH_FAILED" }
git -C $origin worktree add --detach $trial $baseCommit
if ($LASTEXITCODE -ne 0) { throw "PINNED_WORKTREE_CREATION_FAILED" }

python "$runner\experiments\local07\local17_real_issue_trial.py" --repo "$trial" --session "$session"
if ($LASTEXITCODE -ne 0) { throw "REAL_ISSUE_PREPARATION_FAILED" }
Write-Host "Pinned checkout: $trial"
Write-Host "Frozen session: $session"
~~~

Resultado esperado: REAL_ISSUE_PREPARED, caminho alvo entre os
dois primeiros da recuperação, nenhuma inferência e nenhum código
candidato executado. Bloqueia versão, Git blob, checkout sujo,
alvo divergente e recuperação sem o arquivo real.

## Geração única, em comando separado

Após revisar issue.json e request.json na sessão, executar uma
única tentativa real com o Ollama já instalado:

~~~powershell
python "$runner\experiments\local07\local16_workflow.py" generate --session "$session" --timeout 180
python "$runner\experiments\local07\local16_workflow.py" check --session "$session"
~~~

A geração é explicitamente opcional e registrada antes do envio ao
modelo; a sessão bloqueia repetição e concorrência. O comando check
avalia aplicabilidade e integridade do patch, sem executar código
gerado e sem aplicar qualquer alteração ao repositório.

**Não executar apply nem testes que importem código gerado no host.**
Um oráculo independente ainda deve avaliar, em ambiente isolado
aprovado, pelo menos três comportamentos: link simbólico externo
(deve recusar), arquivo comum externo (deve permitir), caminho interno
(deve recusar), além de preservar as interfaces existentes.

Sem ambiente de execução de candidato qualificado, o resultado
funcional permanece NOT_EVALUATED. Patch aplicável não é issue
resolvida e uma única amostra não sustenta taxa de acerto geral.
Não fazer merge ou release automático.

Enviar as saídas JSON do PREPARE, GENERATE e CHECK para reconciliar
as etapas. O response.json pode conter código privado e não deve ser
divulgado sem revisão.

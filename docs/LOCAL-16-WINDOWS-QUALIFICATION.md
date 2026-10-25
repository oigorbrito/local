# LOCAL-16 — Homologação Windows: consolidação pós-execução

## Evidência reportada pelo operador, 2026-10-24

Windows com Ollama 0.40.7; modelos instalados:
- nemotron-3-nano:4b (principal)
- qwen3.5:4b (alternativo)
- qwen3.5:2b (economico)

O console informou AUDIT_PASS sem geração e PASS_LIVE_FIXTURE para o
principal com uma única inferência e timeout 180. A evidência está sob
D:\projetos\local16-evidencias-0b40a348\ (subdiretórios audit e principal).

Classificação: USER_CONSOLE_REPORTED_PASS. Ainda não equivale a exame
independente dos arquivos JSON; não repetir inferência desnecessariamente.

## Verificador offline, sem modelo e sem execução de candidato

O módulo experiments/local07/local16_evidence_gate.py cruza os arquivos:
- audit/local16-acceptance.json
- principal/local16-acceptance.json
- principal/fixture-issue.json
- principal/adapter-report.json
- principal/model-response.json
- principal/candidate.patch

Confere as três identidades nativas e versões/políticas, digests, status
de transporte, integridade do checkout reportada, commit-base, escopo
do patch e reexecuta somente o interpretador AST do LOCAL-12 para os
quatro casos já definidos. Não faz chamadas ao Ollama, não executa
código gerado e não executa comandos do candidato.

Execute no PowerShell a partir do worktree atualizado da PR #25:

~~~powershell
$worktree = "D:\projetos\local16-validacao-0b40a348"
$base = "D:\projetos\local16-evidencias-0b40a348"

if ((git -C $worktree status --porcelain)) {
    throw "WORKTREE_COM_ALTERACOES_LOCAIS"
}
git -C $worktree fetch origin feat/local16-model-profiles
if ($LASTEXITCODE -ne 0) { throw "FETCH_FALHOU" }
git -C $worktree switch --detach FETCH_HEAD
if ($LASTEXITCODE -ne 0) { throw "WORKTREE_UPDATE_FALHOU" }

python "$worktree\experiments\local07\local16_evidence_gate.py" `
    --audit-dir "$base\audit" `
    --live-dir "$base\principal" `
    --output "$base\local16-gate-verdict.json"

if ($LASTEXITCODE -ne 0) { throw "VERIFICACAO_DE_EVIDENCIAS_BLOQUEADA" }
~~~

O resultado qualificado é WINDOWS_FIXTURE_EVIDENCE_CONSISTENT, com
fixture_cases_independently_checked=4 e inference_calls_reported=1.
A saída resumida local16-gate-verdict.json contém hashes e status,
nunca o texto do modelo. O programa recusa sobrescrever a saída; usar
outro nome se já existir.

O SHA-256 dos arquivos dá consistência interna, NÃO autentica o host
contra um adversário que altere todos os artefatos. O estado de
identidade pós-geração foi reportado pelo próprio runtime anterior
sem salvar um segundo snapshot; será marcado
REPORTED_BY_LOCAL_ACCEPTANCE, não uma comprovação criptográfica.
Conclusão não extrapola para SWE-bench, taxa geral de resolução,
velocidade/VRAM, segurança de execução ou autorização de merge.

## Próximo gate

Avaliar uma tarefa Python real, única e reproduzível em checkout Git
descartável, com caso funcional e oráculo definidos previamente sem
mostrar o patch esperado para o modelo. Distinguir patch aplicável de
bug resolvido. O candidato não pode ser executado no host e a PR fica
em draft até revisão manual.

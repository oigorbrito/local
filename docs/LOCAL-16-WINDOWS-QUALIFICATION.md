# LOCAL-16 — Homologação Windows: consolidação pós-execução

## Evidência reportada pelo operador, 2026-10-24

Windows com Ollama 0.40.7; modelos instalados:
- nemotron-3-nano:4b (principal)
- qwen3.5:4b (alternativo)
- qwen3.5:2b (economico)

O console informou AUDIT_PASS sem geração e PASS_LIVE_FIXTURE para o
principal com uma única inferência e timeout 180. A evidência está sob
D:\projetos\local16-evidencias-0b40a348\ (subdiretórios audit e principal).

Classificação atual: OPERATOR_OFFLINE_EVIDENCE_VERIFIED. Em 2026-10-24,
o operador executou local16_evidence_gate.py sobre os arquivos no Windows e
encaminhou a saída compacta WINDOWS_FIXTURE_EVIDENCE_CONSISTENT,
com os 3 perfis verificados, 4/4 casos do oráculo AST e 1 inferência.
O verificador processou os dados **no computador do operador**; os JSONs
de entrada e o texto da resposta não foram recebidos nesta sessão nem
armazenados no repositório. Não repetir inferência desnecessariamente.

Identificadores SHA-256 divulgados pelo verificador local:
- modelo Nemotron nativo: d94b6dfae26d340fd16599d8cd5301945bb42b6bd7a7c70f2078559562f60cbe
- política do perfil principal: dfd3cf5ae7d667c7f819164a9a081c8de8db538d27fec43c155a8639dbe15886
- patch: 4cf3a8c044796e82f3ae1a56e08f4827f22886e4571f2c98c05b9e6ffdaaf913
- resposta: 774079098d0e0383c0d19819046e2e5b3205a61e6d3783
- audit: 5070b57f6f63331fd55ec0ec70472dc4d69abefd290834dcdf1bc58222f82f9e
- live: c5b3ad27a8e1f6ac48e06861ee93ffa37b4545d91f74b51dd91ad27187684f91
- adapter: 4a69b413c5b4dcb19965c449e277ccee4132cac5681629ff446a517f18cb65f8

O verificador e os testes agora suportam **dois contratos** de identidade
pós-geração: relatórios antigos com declaração booleana, aceitos como
REPORTED_BY_LOCAL_ACCEPTANCE; novos relatórios que preservam o
native_evidence_after, verificáveis por comparação entre os snapshots
sanitizados pré e pós-geração. A execução real informada pertence ao
primeiro contrato; não promover retroativamente sua classificação.

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

Foi pré-registrado um defeito real de validação de evidências por
symlink no arquivo experiments/local07/reviewed_patch.py, com commit-base
Git e hash do blob congelados. A preparação offline e os comandos
Windows estão em docs/LOCAL-17-REAL-ISSUE-TRIAL.md. Distinguir patch
aplicável de bug resolvido: o modelo ainda **não** foi executado neste
caso; a avaliação funcional de seu candidato depende de isolamento
independente. O candidato não pode ser executado no host e a PR
permanece draft, com revisão/merge manuais.

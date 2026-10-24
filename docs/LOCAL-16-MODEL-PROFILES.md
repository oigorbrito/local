# LOCAL-16 — Executores locais promovidos: perfis versionados

**Situação:** implementação do contrato e do runtime. Os perfis são políticas de
invocação dos modelos nativos já instalados, **não** novos pesos ou Modelfiles
derivados. A seleção exploratória encerrou: não reabrir disputa de modelos.

## Perfis canônicos

| Nome CLI | Modelo nativo Ollama | Política | Versão |
| --- | --- | --- | --- |
| `principal` | `nemotron-3-nano:4b` | correção restrita ao contexto | 1.0.0 |
| `alternativo` | `qwen3.5:4b` | preservar interfaces | 1.0.0 |
| `economico` | `qwen3.5:2b` | edições pequenas | 1.0.0 |

As políticas estão em `experiments/local07/model_profiles.py`, cada uma com
`version`, `base_model`, opções explícitas, instrução de sistema e fingerprint
SHA-256 determinístico. A personalização é somente de instrução de sistema,
com limites de inferência **mantidos exatamente iguais à baseline LOCAL-09**:
`temperature=0`, `num_ctx=4096`, `num_predict=2048`. Diferenças de política
não são alegações de melhoria quantitativa; não houve fine-tuning ou modificação
dos templates nativos.

## Operação no Windows (PowerShell)

Na raiz do clone `D:\projetos\local`:

```powershell
python experiments/local07/profile_cli.py --list
python experiments/local07/inspect_profiles.py --output local16-native-audit.json
```

O segundo comando só consulta `POST /api/show` no Ollama em `127.0.0.1:11434`.
Não carrega modelos para geração, não altera pesos ou configurações e não executa
fonte recebida do modelo. O relatório usa hashes das definições nativas;
não exporta texto bruto de Modelfile, template ou instruções internas.
Falha com exit code 2 e indica qual perfil ficou bloqueado quando um dos
três modelos não está acessível. O hash nativo prova identidade do que o Ollama
declarou naquele momento, **não** sua imutabilidade posterior ou a eficácia.

Executar um único caso de edição, com inferência real **somente se explicitamente
desejada**:

```powershell
python experiments/local07/profile_cli.py --profile principal --repo D:\caminho\checkout-limpo --issue-json issue.json --report local16-report.json --patch local16.patch --response-json-path local16-response.json
```

`issue.json`: objeto JSON com `problem_statement` texto. Use `--profile
alternativo` ou `--profile economico` sem modificar comandos no adaptador.
`--timeout` aceita de 1 a 420 segundos (padrão 180).

Reexecutar uma resposta salva **sem inferência Ollama**:

```powershell
python experiments/local07/profile_cli.py --profile principal --repo D:\caminho\checkout-limpo --issue-json issue.json --offline-response-json local16-response.json --report replay-report.json --patch replay.patch
```

Em replay, `model_invoked=false`; selecionar perfil **não** atribui a resposta
salva àquele modelo. Isso evita atribuição falsa de origem.

## Gate único de aceitação operacional (LOCAL-16)

O comando de auditoria é read-only e consulta os três modelos sem inferência:

```powershell
python experiments/local07/local16_acceptance.py --mode audit --output-dir D:\\projetos\\local16-audit
```

A execução **explícita** do executor principal para uma única fixture
descartável, com inspeção nativa antes/depois, contrato completo e oráculo
sem executar código gerado:

```powershell
python experiments/local07/local16_acceptance.py --mode live --profile principal --output-dir D:\\projetos\\local16-primary-acceptance
```

Esse segundo comando autoriza **uma tentativa de geração**, não um benchmark
repetitivo. A integração nunca altera o repositório de trabalho: inicializa um
Git descartável e usa a mesma fixture de `LOCAL-11` e o oráculo AST de
`LOCAL-12` (4 casos). Pode-se escolher `alternativo` ou `economico` em
uma execução deliberadamente separada; nenhum fallback/loop automático.

O mesmo gate pode ser reproduzido **sem Ollama** com resposta salva:

```powershell
python experiments/local07/local16_acceptance.py --mode replay --profile principal --response-json D:\\projetos\\local16-primary-acceptance\\model-response.json --output-dir D:\\projetos\\local16-replay
```

`--output-dir` precisa usar destino novo (a rotina não sobrescreve evidência).
O arquivo `local16-acceptance.json` tem estágio de inspeção, quantas chamadas
foram tentadas, integridade do checkout, SHA do candidato, estado do oráculo
e status global. `PASS_LIVE_FIXTURE` significa **somente** que 4 casos da
fixture restrita foram interpretados corretamente, que o patch é aplicável e
que não houve drift detectado nas definições do modelo instalado.

A auditoria lê `GET /api/tags` para registrar o digest SHA-256 **informado
pelo Ollama para o modelo instalado** e `POST /api/show` para hashes da
definição, parâmetros e template. O modo live repete a inspeção depois da
geração e bloqueia `NATIVE_MODEL_DRIFT` ou `POST_INSPECTION_BLOCKED`.
Não equivale à verificação criptográfica independente dos arquivos GGUF.
Os endpoints usados são somente de leitura, sem pulls ou criação de modelos.
A saída não armazena Modelfiles, template bruto nem paths de blobs locais.

Status finais: `AUDIT_PASS`, `AUDIT_INCOMPLETE`,
`PASS_LIVE_FIXTURE`, `PASS_REPLAY_FIXTURE`, `FIXTURE_NOT_SOLVED`,
`EXECUTOR_FAILED`, `BLOCKED_NATIVE_INSPECTION`,
`NATIVE_MODEL_DRIFT`, `POST_INSPECTION_BLOCKED`,
`SOURCE_INTEGRITY_FAILURE`, `INFRA_FAILURE`.
Somente as três condições de passagem retornam exit code 0.

Este gate não afirma taxa geral de sucesso, segurança de executar patches
em ambiente host ou resolução oficial de benchmarks. Os metadados da
instalação do usuário continuam `NOT_OBSERVED` enquanto o gate real não
for executado naquele Windows.

## Invariantes verificáveis

1. O checkout fonte precisa ser um repositório Git limpo. HEAD e limpeza
   são verificados antes e depois da geração; qualquer drift bloqueia a saída.
2. O adaptador usa somente HTTP loopback, `/api/generate`, `format=json`,
   `stream=false`, com limites de tamanho, tempo e opções aceitas.
3. O JSON retornado é validado contra `schema=1` e a allowlist de arquivos
   recuperados do contexto. Resultado passa pelo LOCAL-07 no worktree
   descartável com AST, `git diff --check` e `git apply --cached --check`.
4. O executor não aplica patches ao checkout nem executa código produzido pelo
   modelo. `PATCH_APPLICABLE_NOT_GRADED` não é resolução de issue.
5. A saída registra versão/fingerprint da política, SHA-256 do patch,
   commit de origem e modo de execução. JSON de replay também tem limites.
6. Entradas e saídas não podem compartilhar um mesmo caminho resolvido.
7. A auditoria do Modelfile não é uma auditoria de segurança do template e
   nem garante a capacidade efetiva de tool calling; capacidades retornadas
   pelo Ollama são apenas **declaradas**.

## Evidência, testes e gates

- `test_model_profiles.py` — seleção.
- `test_profile_runtime.py` — versão e fingerprint, políticas enviadas pelo
  adaptador, restrições de transporte, digest do modelo instalado, auditoria
  sanitizada, respostas inválidas, replay funcional em repositório Git real e
  ausência de mutações.
- `test_local16_acceptance.py` — oráculo de semântica funcional limitado à
  fixture, auditoria dos três modelos, geração mockada limitada a uma tentativa,
  replay offline, detecção de drift de digest/template, ausência de alteração
  no checkout e prevenção de sobrescrita de evidências.
- Regressões reutilizadas de LOCAL-07/09.
- `.github/workflows/local16-profiles.yml` — compilação e testes offline
  agrupados em Linux e Windows, incluindo validação de patches sem executar
  sua fonte, CLI de aceitação e oráculo AST.
- Não há teste de inferência real no runner GitHub; depende do Windows com
  Ollama local. A inspeção nativa **não** pode ser atestada remotamente.
- Não fazer merge automático. O gate da PR permanece draft até revisão manual.

## Fronteiras de evolução

Alterar `SYSTEM`, opções ou vínculo com modelo requer **nova versão e
fingerprint**; mudar pesos, `TEMPLATE` ou criar um `Modelfile` derivado
exige inspecionar e registrar primeiro o modelo nativo. Não substituir o
template por suposição nem fazer tuning sem medidas reproduzíveis.
A execução de código não confiável continua bloqueada; LOCAL-16 não promove
as PRs experimentais de Docker/host attestation à condição de isolamento seguro.

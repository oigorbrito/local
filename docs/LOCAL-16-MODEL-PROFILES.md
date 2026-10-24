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
  adaptador, restrições de transporte, auditoria sanitizada, respostas inválidas,
  replay funcional em repositório Git real e ausência de mutações.
- Regressões reutilizadas de LOCAL-07/09.
- `.github/workflows/local16-profiles.yml` — compilação e testes offline,
  incluindo aplicação reversível do patch (sem executar sua fonte).
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

# LOCAL — Decisão de adoção de benchmark publicado (23/10/2026)

## Escopo e princípio
Reutilizar um projeto externo de avaliação de **harness** sem afirmar paridade ou desempenho antes da validação. Esta decisão NÃO integra código de terceiros, NÃO reexecuta modelos, NÃO altera main e NÃO declara vencedor.

## Fontes públicas (verificadas)
- Harness-Bench acadêmico: https://www.harness-bench.ai/ e https://arxiv.org/abs/2605.27922 — referência metodológica; fixa entradas, avaliadores e orçamento de execução por configuração modelo–harness; enfatiza avaliação por artefatos, sem julgador LLM.
- **ya5h-P/harnessbench**: https://github.com/ya5h-P/harnessbench — candidato prioritário à implementação. Inspeção via GitHub em 23/10/2026: contém `engine/preflight.sh`, `engine/metrics_delta.py`, `run_one.sh`, `run_matrix.sh`, `score.py`, `adapters/pi.sh`, `adapters/opencode.sh`, `adapters/hermes.sh`, `adapters/mock.sh`. **Não contém adapters Aider ou Little-Coder** no diretório verificado.
- llama-bench oficial: https://github.com/ggml-org/llama.cpp/blob/master/tools/llama-bench/README.md — medição de processamento e geração; **não** mede sucesso de reparos nem substitui benchmark de harness.
- Aider Polyglot: https://github.com/Aider-AI/aider/tree/main/benchmark — avaliação funcional separada, não intercambiável com suite HarnessBench.

## Escolha, com escopo explícito
1. **HarnessBench ya5h-P = candidato de execução**, condicionado à auditoria dos validadores, licenças, versão pinned, adaptadores e preflight em modo mock. Seu README anuncia 200 tarefas, validadores ocultos, controle de runaway por tokens, estatística pareada e endpoint local compatível. Tais reivindicações são documentais e ainda NÃO foram reproduzidas no LOCAL.
2. **Harness-Bench acadêmico = método de referência**, não é assumir que ambas as bases de tarefas são idênticas. A comparação principal deve isolar harness mantendo modelo, quantização, endpoint, tarefa, ambiente, orçamento de tokens/tempo, aleatoriedade e critério de aprovação. Preservar o comportamento nativo dos agentes.
3. **llama-bench = gate de hardware** executado no Windows-alvo; comparar t/s, RAM, VRAM, contexto e estabilidade. Resultados de GitHub-hosted Ubuntu runners NÃO provam viabilidade no computador Windows 16GB RAM/4GB VRAM.
4. Aider e Little-Coder exigirão **adapters específicos** antes da comparação HarnessBench. Não considerar um adaptador existente como suporte automático a esses executores.

## Gates sem inferência, antes de qualquer ensaio adicional
- Pin SHA do benchmark e dos agentes. Revisar executabilidade real de 200 validadores, isolamento dos testes ocultos, funcionamento de `preflight.sh` e `mock`; verificar que solução de referência passa e estado inicial falha. Registrar casos não auditáveis.
- Inspecionar esquema de CSV/eventos, medição de tokens junto ao servidor, watchdog, classificação de timeout/erro de infraestrutura/runaway e fórmula estatística. Rejeitar automações com relatório de sucesso sem testes executados.
- Validar CLI, transporte Ollama/OpenAI, ferramentas/permissões e número máximo de turnos dos agentes; escrever apenas adapters mínimos, não reimplementar o avaliador.
- Predefinir tarefas idênticas e ordem determinística, uma concorrência por endpoint, limite uniforme, orçamento e critérios de desistência. Modelo diferente ou lista de tarefas embaralhada = não pareado.
- Preservar logs brutos, patches, exit code, test oracle, tokens e uso de memória, versão exata do modelo e ambiente. Resultado sem verificador executado = INVALID_HARNESS; estouro de prazo = TIMEOUT_CENSORED; falha de API = INFRA_ERROR; nunca incluir esses como 0 de competência.

## Dados históricos (não repetir)
- 14 variantes tiveram triagem sintética de 6 tarefas; esse conjunto é insuficiente para eliminação por eficácia.
- Aider antigo, 12 exercícios por configuração, seleção embaralhada: Ministral 3B 0/12, Qwen2.5-Coder 7B 1/12; **não é comparação pareada**.
- Little-Coder Nemotron 4B affine-cipher: falha após ~902.57 s; beer-song: timeout a 420 s, não é reprovação do modelo.
- Aider Nemotron 4B affine-cipher: timeout de comunicação Ollama e saída 124 após 1500 s; não houve validação funcional. Não repetir automaticamente.
- Antes desta mudança, PRs #15 e #16 permaneciam drafts; nenhuma está autorizada a merge automático.

## Decisão de parada
Não iniciar nova matriz de inferência até satisfazer os gates de instrumentação, preflight e viabilidade no hardware-alvo. Uma vez satisfatórios, piloto pareado pré-registrado e mínimo; só ampliar se houver sinal válido. Critério de promoção: relatório independente com tarefas e orçamento iguais, oracle funcional verificável, custos e intervalos de incerteza. Nenhuma preferência antecipada por Pi/Aider/Little-Coder.

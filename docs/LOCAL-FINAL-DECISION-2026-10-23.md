# LOCAL — decisão consolidada baseada nos experimentos existentes (23/10/2026)

**Não reexecutar as tarefas já medidas. Não executar as 200 tarefas do HarnessBench. Não promover modelo ou executor a produção sem evidência de correção real e estabilidade.**

Alvo: Windows 11, i5-10300H, 16 GB RAM, GPU NVIDIA 4 GB VRAM, Ollama. Inferência remota paga fora do escopo.

## Conclusão operacional por finalidade

| Finalidade | Referência escolhida | Evidência | Limite |
|---|---|---|---|
| Programação local com múltiplos turnos/reparos **sintéticos** | **Nemotron 3 Nano 4B** | Windows V2 4/4, V3 4/4; V2 19 chamadas, 15.481 tokens, 18,06 min | Resultados V2/V3 preservados em handoff, não em artefatos brutos homologados; não resolveu issues oficiais |
| Velocidade em tarefas Python curtas | **Qwen3.5 2B** | Windows controlled-v1 3/3, soma 23,348 s, 23,09–27,61 tokens/s | n=3, sem teste equivalente V2/V3; não prova autonomia em repositório |
| Alternativa de qualidade local | **Qwen3.5 4B** | Windows V2 3/4, V3 4/4; controlled-v1 3/3 | Maior tempo V2 (47,98 min) e controlled-v1 (97,801 s); offload parcial CPU/GPU |
| Opção rápida secundária | **LiquidAI LFM2.5 2.6B** | Windows Python 3/3, ~55 s; V2 2/4; PILOT02 276,79 s para 3 issues | Patches estruturais 0/3 e truncamento 3/3 no PILOT02; não equiparar a competência em reparo |
| Baseline codificador | **Qwen2.5-Coder 3B** | Windows controlled-v1 2/3; GitHub CPU 5/6; 0/3 issues SWE-bench agente experimental | Erro sintático em balanced; reparos oficiais não aprovados; não comparar GitHub timing com Windows |
| Gargalo já observado | **Qwen3.5 9B Q4** | Windows V3 1/4, três timeouts | Não é prioridade neste hardware sem necessidade; não provar inviabilidade universal |

O ranking **não** é pontuação universal. O Nemotron 4B está primeiro para o objetivo de manutenção *sintética*; o Qwen3.5 2B é referência de velocidade numa suíte separada. Não existe prova de vencedor para correção autónoma de bugs reais.

## Reconciliação dos dados

- Windows controlled-v1: os mesmos três exercícios (balanced, deduplicate, word_count): Qwen3.5 2B 3/3, 23,348 s; Qwen3.5 4B 3/3, 97,801 s; Qwen2.5-Coder 3B 2/3, 250,725 s. Há transcrição do JSON impresso em PowerShell, contendo `wall_seconds`, `generation_tok_s`, contagens de pytest, casos por modelo. Arquivos brutos e digests completos ainda não foram acessados diretamente.
- Windows V1/V2/V3: dados recuperados dos handoffs. V2 Nemotron 4/4 e Qwen3.5 4B 3/4; V3 ambos 4/4. Não somar V1/V2/V3 com controlled-v1 por tarefas e protocolos diferentes.
- Windows LOCAL-BENCH-04: Nemotron e LFM foram avaliados nos **mesmos três issues reais**, duas vezes, e não produziram patches estruturalmente válidos. Truncamento/recuperação de arquivo incorreto/pipeline invalidam a leitura como reprovação isolada de modelo. Targeted Edit V3 teve 12/12 testes de contrato, **não** 12/12 issues resolvidos.
- GitHub Actions CPU: 14 modelos numa suíte de 6 exercícios Python; resultados 5/6 não criam ranking Windows. Qwen3.5 2B/4B com saída vazia nessa infraestrutura: incompatibilidade de coleta, invalidada como evidência de baixa qualidade pela execução local 3/3. Aider: Qwen2.5-Coder 7B 1/12, Ministral 3B 0/12, com seleções embaralhadas e sem comparação pareada. Nemotron/Aider/Little-Coder: timeout e erro de API; não declarar vencedor por executor.

## Decisões de engenharia

1. **Fixar três referências operacionais com objetivos diferentes**: Nemotron 4B (manutenção), Qwen3.5 2B (baixa latência), Qwen3.5 4B (alternativa). LFM2.5 e Qwen2.5-Coder 3B permanecem baselines documentados. Não instalar automaticamente nem alterar padrões de outros projetos.
2. **Congelar benchmarks redundantes**: nenhuma nova execução V1/V2/V3, 6-tarefas, três issues repetidos com o mesmo pipeline ou varredura de 200 tarefas.
3. **Sem ranking de harness**: Aider vs Little-Coder inconclusivo sob mesmo modelo/tarefa/orçamento por limites de inferência e captura. Não transferir essa conclusão para FineCore/FineCode.
4. **Evidência Windows faltante**: hashes de resultados V2/V3, modelo+quantização exatos, picos RAM/VRAM e avaliação oficial do Targeted Edit V3 nos repositórios reais. Preservar a lacuna e não substituí-la com inferências.
5. **PR #15** contém workflow Aider ainda experimental, não autorizar merge. **PR #16** contém workflows experimentais além da documentação, não autorizar merge integral. Manter drafts e promover apenas dados verificados por revisão seletiva futura.
6. **Gate eliminatório**: nunca tratar timeout, `MODEL_OUTPUT_EMPTY`, erro de API, patch inválido por retrieval incorreto ou contrato verde como falha funcional do modelo. Qualidade e velocidade são medidas separadas; não extrapolar perfis de CPU-hosted CI para GPU doméstica.

## Proveniência

- Histórico de experimentos e regras: `docs/WINDOWS-LOCAL-EVIDENCE-RECONCILIATION-01.md`, `docs/LOCAL-RESTART-PROTOCOL-01.md` nesta branch.
- Resultados GitHub na main: `ci/BREADTH-01-RESULTS.md`; run 40017286253.
- Windows controlled-v1: transcrição da saída `scored-results.json` do PowerShell em conversa anterior; caminhos preservados na reconciliação.
- Windows V2/V3 e SWE-bench: handoffs prévios e transcrição de pilot02. Não inventar hashes ausentes.

**Status: DECISÃO DOCUMENTAL CONCLUÍDA; HOMOLOGAÇÃO DE REPARO REAL PENDENTE.** Nenhuma inferência nova foi necessária.

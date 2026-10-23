# LOCAL — Reconciliação de evidências executadas no Windows (23/10/2026)

## Escopo e proveniência
- Equipamento informado nos logs originais: Windows 11, Intel Core i5-10300H, 16 GB RAM, GPU NVIDIA 4 GB VRAM, Ollama.
- **Dados desta seção recuperados de registros previamente compartilhados pelo usuário na conversa**, incluindo saída do PowerShell e resumos de execução. Os arquivos brutos permanecem no computador e **não foram lidos diretamente nesta auditoria**. NÃO classificar esses valores como nova execução ou medição verificada no GitHub.
- Campanhas do GitHub Actions usaram runners Ubuntu CPU e não comprovam performance de Windows/4GB GPU.

## Ensaios Windows já realizados; não repetir
| Série e evidência | Modelo | Resultado | Tempo/observações | Classe |
|---|---|---|---|---|
| controlled-v1: `C:\\Users\\igorb\\Downloads\\results-controlled-v1\\results.json` | qwen3.5:2b | 3/3 | 23,35 s total | sintético local |
| idem | qwen3.5:4b | 3/3 | 97,80 s total | sintético local |
| idem | qwen2.5-coder:3b | 2/3 na rodada registrada | 250,73 s total; carregamento afetou duração | sintético local |
| LOCAL-BENCH-04: `C:\\Users\\igorb\\Downloads\\local-bench-04\\local-bench-04` | nemotron-3-nano:4b | 0/6 observações | no pilot02, 698,14 s total / 232,71 s média | SWE-bench issue repair |
| idem | LiquidAI/lfm2.5-2.6b:q4_k_m | 0/6 observações | no pilot02, 276,79 s total / 92,26 s média | SWE-bench issue repair |
| Ollama diagnostic: `C:\\Users\\igorb\\Downloads\\qwen35-diagnostic.json` | qwen3.5:4b Q4_K_M | geração ~12,54 tokens/s no caso observado | `ollama ps`: 3,8 GB, 52% CPU / 48% GPU, contexto 4096 | diagnóstico de runtime |

A rodada LOCAL-BENCH-04 observou três issues oficiais: `marshmallow-code__marshmallow-1343`, `marshmallow-code__marshmallow-1359`, `pvlib__pvlib-python-1072`. O denominador 6 inclui repetições/tentativas, não seis issues independentes. Patches/saídas estruturais não devem ser confundidos com sucesso em teste funcional.

## Conflitos a reconciliar contra arquivos brutos, sem inferência nova
- Há menção a uma rodada reparada do `controlled-v1` na qual Qwen2.5-Coder 3B chega a 3/3; **não misturar** com 2/3 na rodada anterior. Guardar `run_id`, teste e scorer para distinguir.
- Outro conjunto local `local-code-benchmark-v2` foi discutido em conversas distintas e o usuário assinalou contexto de chat incorreto. Não somar automaticamente seus números à campanha `local-bench-04` sem conferir manifesto e origem.
- O campo `3,8 GB` do Ollama não é medição de pico de VRAM. Percentual CPU/GPU não equivale à fração de VRAM total disponível ou em uso.
- Não há registro recuperado de picos independentes de RAM/VRAM, potência ou ocupação temporal. **Viabilidade medida: execução e offload parcial observados para Qwen3.5 4B; estabilidade generalizada não demonstrada.**

## Regras para próximos passos
1. **Sem repetição de modelos/tarefas já testados** para preencher planilhas; obter primeiro os JSON/logs existentes e preservar hashes.
2. Distinguir `OFFICIAL_RESOLVED`, `PATCH_APPLIED`, `SYNTAX_VALID`, `TIMEOUT`, `INFRA_ERROR` e `MODEL_OUTPUT_EMPTY`. É incorreto transformar timeout ou falha de captura em reprovação funcional.
3. Para elegibilidade Windows, prioridade aos modelos **efetivamente rodados localmente**, não aos maiores números do GitHub Actions.
4. Reconciliar resultados divergentes por `run_id`, parâmetros (`num_ctx`, `num_predict`, temperature), nome+digest do modelo, hardware e arquivos brutos antes de qualquer ranqueamento.
5. O benchmark de 200 tarefas externo **não está autorizado como campanha inteira**; qualquer novo teste exige pergunta nova e evidência de que dados antigos não respondem.

## Complemento documental — histórico V1/V2/V3 recuperado
Fonte secundária: handoff anterior do projeto LOCAL (arquivo de conversa `Texto colado (2).txt`); **não são novos resultados** e os JSONs originais dessas baterias não foram homologados nesta leitura.

| Série local | Nemotron 4B | Qwen3.5 4B | LFM2.5 2.6B | Qwen3.5 9B Q4 |
|---|---|---|---|---|
| V1 (4 tarefas Python) | 3/4 | 3/4 | não informado | não informado |
| V2 (4 tarefas, até duas oportunidades de reparo) | 4/4 | 3/4 | 2/4 | não informado |
| V3 (pagination, money, config, cache) | 4/4 | 4/4 | não informado | 1/4; três timeouts |
| Bateria Python local adicional (3 tarefas) | 3/3; ~44s | 2/3; ~952s | 3/3; ~55s | não informado |

- V2: Nemotron 4/4, 19 chamadas, 15.481 tokens de saída, 18,06 min; Qwen3.5 4B 3/4, 27 chamadas, 26.970 tokens, 47,98 min. **Comparação de tarefa e protocolo V2, não agregável ao GitHub Actions.**
- Os resultados do `results-controlled-v1` (3/3 para Qwen3.5 4B e 2B, ~97,80s e ~23,35s) **não são a mesma bateria** que o 2/3 e ~952s da tabela acima. Não resolver divergências por média ou escolha de uma das séries; recuperar metadados de ambos os runs.
- LOCAL-BENCH-04: no método diff direto, Nemotron e LFM não produziram patches válidos (0/3 cada). No método de substituição integral, houve seleção incorreta de arquivos pelo recuperador, limite de 2048 tokens no LFM, alterações não relacionadas e erros sintáticos do Nemotron. **Isso não comprova incapacidade geral de reparo dos modelos.**
- Targeted Edit V3: testes de contrato publicados como 12/12, porém **sem homologação real de inferência nas três issues**. Proibido registrar como resultado de resolução SWE-bench.

**Decisão de reutilização:** Nemotron 4B, Qwen3.5 4B, LFM2.5 2.6B e Qwen2.5-Coder 3B já têm múltiplas baterias executadas. Qwen3.5 9B já mostrou gargalo relevante. Não repetir V1/V2/V3 nem SWE-bench sobre o mesmo método; auditar arquivos brutos e protocolo antes de desenhar qualquer nova tarefa. Não converter essas observações em ranking universal ou excluir modelos sem validação do runtime alvo.

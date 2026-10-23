# LOCAL-05 — Homologação Targeted Edit V3 (auditoria sem inferência)

Data: 23/10/2026. Projeto: oigorbrito/local. Gate atual: **BLOCKED_SOURCE_UNAVAILABLE**, não homologado.

## Evidências realmente inspecionadas
- Inventário completo da árvore Git da branch `experiment/local-restart-protocol-01`: nenhum runner, pacote, fixture ou resultado bruto do `local-bench-04` ou `Targeted Edit V3` está versionado. A árvore contém documentação de reconciliação e os workflows independentes.
- Busca dos arquivos de conversa/biblioteca: disponíveis transcrições PowerShell e handoffs `Texto colado (2).txt`, `Texto colado(6).txt`, `Texto colado(7).txt`. Nenhum arquivo executável do pacote V3 foi encontrado nessa busca.
- Handoff local registra pacote `LOCAL-BENCH-04 Targeted Edit V3` com **12/12 testes automatizados reportados**, mas não contém código para reproduzir nem prova de execução real com issues oficiais. Este é um reporte secundário, não um gate de eficácia.
- PILOT01/PILOT02 dos modelos Nemotron 4B e LFM2.5 2.6B usaram somente três issues SWE-bench Lite: `marshmallow-code__marshmallow-1343`, `marshmallow-code__marshmallow-1359`, `pvlib__pvlib-python-1072`. O resultado 0/3 por configuração/piloto é **validade estrutural de patch**, não resolução oficial.
- Falhas documentadas: retrieval de arquivos errados, truncamento em 2048 tokens no LFM e 2/3 do Nemotron no PILOT02, edições alheias, erros de sintaxe, normalização CRLF/LF afetando hashes. Não atribuir todos esses fenômenos à capacidade do modelo.

## Gate de homologação e resultado atual

| Gate | Evidência requerida | Estado |
|---|---|---|
| Fonte V3 | pacote, hashes, runner, dependências, fixtures disponíveis | **BLOCKED** |
| Proveniência | commit(s) base e identificadores de instâncias verificados com payload oficial | **NOT_VERIFIED** |
| Retrieval | `schema.py`, `fields.py`, `temperature.py` localizados por traceback/símbolos, sem patch-oráculo no prompt | **NOT_RUN** |
| Edição/patch | patch localizado, `git apply --check`, limites de caminho, não alteração de trechos não relacionados | **NOT_RUN** |
| Isolamento | referências-oráculo isoladas dos dados dos agentes, Docker, limite de recursos, execução sequencial | **NOT_RUN** |
| Avaliação independente | comandos oficiais realmente executados e logs PASS_TO_PASS/FAIL_TO_PASS persistidos | **NOT_RUN** |
| Integridade | artefatos byte a byte, SHA256, Unicode/newlines, ids e parâmetros | **NOT_RUN** |

## Decisão objetiva

**Não executar modelos, não repetir três issues, não chamar 12/12 de homologação real.** O bloqueio é acesso ao código e aos artefatos V3; não há uma falha funcional comprovada do runner atual porque seu executável não pôde ser inspecionado.

O próximo ato, sem inferência, é incorporar o ZIP/arquivos já existentes de `C:\\Users\\igorb\\Downloads\\local-bench-04\\local-bench-04` ou o artefato `LOCAL-BENCH-04 Targeted Edit V3` ao contexto de auditoria, mantendo cópia e hashes. A partir daí executar unicamente preflight/contratos locais, fixtures e avaliador independente com soluções-oráculo isoladas do input — sem reutilizar resultados para forçar um ranking.

PR #16 permanece draft. Não copiar esses dados para FineCore, não fazer merge/force push, não instalar modelos, não rodar inferências pagas.

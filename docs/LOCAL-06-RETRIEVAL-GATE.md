# LOCAL-06 — Recuperação determinística sem inferência

Data: 23/10/2026. Base: três issues do SWE-bench Lite dev e checkouts de código presentes nos ZIPs de local-bench-04, previamente enviados. Nenhuma chamada a modelos nem aos patches gold foi feita durante a recuperação.

## Implementação auditada (artefatos da execução)
O recuperador independente `retrieve_context.py` combina nomes de arquivos provenientes de traceback, caminhos citados na issue, símbolos presentes na issue e definições AST. Retorna fragmentos de código com números de linhas em orçamento máximo de 9000 caracteres, ranqueados deterministicamente. Evita diretórios de testes e mantém a lista `expected` **exclusivamente no avaliador** `validate_retrieval.py`, nunca no recuperador ou prompt. Não modifica repositório; não produz patches; não executa LLM.

SHA256 dos scripts:
- `retrieve_context.py`: `41fa4efd9e73f33b828ec754e06c902a7f7fddb18d6953ea64fcd635351d4cd9`
- `validate_retrieval.py`: `7b7fb9a2c59e4cfc1d1274271144bb836df1a7865110f8851b9bc2b64d69f6e4`
- `retrieval-results.json`: `d230f33f475c91d1cc1e1164069ff19ff04d5ba4c9c95a1e61bc0fd1439685a8`

## Gate único — seleção de arquivo e orçamento

| Issue | Arquivo relevante na avaliação | Rank obtido | Orçamento |
|---|---|---:|---|
| marshmallow-1343 | src/marshmallow/schema.py | 1 | ≤9000 caracteres |
| marshmallow-1359 | src/marshmallow/fields.py | 2 | ≤9000 caracteres |
| pvlib-python-1072 | pvlib/temperature.py | 1 | ≤9000 caracteres |

Resultado: **Recall@1 = 2/3**, **Recall@2 = 3/3**; sintaxe dos scripts compilou; todos os contextos ≤9000 caracteres. Histórico: recall de presença do arquivo relevante **0/18 traces** no pipeline antigo. A nova avaliação testa três **issues distintas**, não dezoito independentes.

## Limites e decisão
- Gate `RETRIEVAL_OFFLINE_PASS` para os três checkouts locais recuperados. NÃO equivale a SWE-bench resolvido, adequação do trecho gerado, correção de patch, generalização estatística ou homologação do Targeted Edit V3 perdido.
- Os checkouts dos ZIPs foram consumidos como árvores de arquivos; os hashes de commits-base não foram revalidados aqui. Não afirmar reprodução exata sem reconciliação Git por commit.
- Code+relatório devem permanecer fora de `main` até revisão; não fazer merge automático.
- Próximo bloco só deverá validar integração com diffs/isolamento em checkout descartável sem geração; não repetir modelos, 200 tarefas ou issues para ranking.

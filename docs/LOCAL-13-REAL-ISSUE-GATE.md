# LOCAL-13 — Gate de issues reais com isolamento de avaliador

Este bloco **não executa modelos nem resolve issues**. Implementa um gate mensurável para retomar a investigação de problemas reais sem confundir falhas de recuperação com qualidade do executor.

## Contratos e evidência
- Checkout de código-fonte Git **limpo** e imutável durante avaliação, fixado por SHA de commit completo.
- `issue.json` (público para recuperação/modelo): `{"schema":1,"issue_id":"...","base_commit":"<SHA do checkout>","problem_statement":"..."}`.
- `evaluator.json` (somente avaliador, nunca entregue ao modelo): `{"schema":1,"issue_id":"...","target_files":["path/to/implementation.py"]}`.
- O avaliador calcula Recall@1 e Recall@2 **após** executar a recuperação sobre issue + fonte e registra hashes, SHA-base e caminhos recuperados. Ele não produz patches, não executa testes oficiais e não gera resolução de issue.
- O alvo da avaliação é o **arquivo de implementação que realmente exigiu mudança**, definido a partir de evidência externa auditável do issue. Evitar inferir destino pela saída do recuperador.
- Sem contaminar entrada do modelo com gold patch, testes ocultos, target_files ou metadados exclusivos do avaliador.

## Limites metodológicos
Recall@K só mede localização por arquivo, não correção. Nos três casos oficiais historicamente tentados, as 18 traces antigas selecionaram arquivos incorretos; outra bateria local de recuperação anterior obteve Recall@1=2/3 e Recall@2=3/3 em snapshots offline, mas **não há resoluções SWE-bench homologadas**. Esses resultados anteriores não são reclassificados aqui.

## Comando de avaliação (offline, sem geração)
```powershell
python .\experiments\local07\real_issue_gate.py `
  --repo D:\caminho\checkout-issue-fixado `
  --issue-json D:\caminho\issue.json `
  --evaluator-json D:\caminho\evaluator.json `
  --output .\runs\local13\retrieval-gate.json
```

### Próximo gate (não implementado neste bloco)
Somente se o top-2 recuperar o destino esperado: chamada explícita ao modelo e patch em checkout isolado, verificação sintática, `git apply --check`, testes públicos/ocultos do benchmark em container desprovido de credenciais com recursos e tempo limitados. Reportar **separadamente** erro de infraestrutura, recuperação, formato, patch, teste e resolução oficial; calcular taxa de resolução apenas com denominador de issues executadas e homologadas. Não publicar tokens/senhas nem executar código gerado diretamente no Windows do operador.

O sistema atual não tem acesso aos três snapshots originais da máquina, aos testes ocultos ou a uma sandbox oficialmente homologada para medir resolução; esses gates continuam bloqueados por evidência externa, não devem ser declarados aprovados.

## Execução verificada em três issues reais — 24/10/2026
Fonte: dataset oficial `princeton-nlp/SWE-bench_Lite`, divisão **dev**, via API de linhas; três registros recuperados com commit-base e enunciado reais. CI de importação [#40097384841](https://github.com/oigorbrito/local/actions/runs/40097384841) PASS.

CI de clonagem do commit-base e recuperação efetiva [#40097465293](https://github.com/oigorbrito/local/actions/runs/40097465293) PASS. O workflow compara os caminhos selecionados pelo recuperador com os caminhos de referência separados no avaliador, sem entregar o gold patch ao modelo.

| Issue | Base commit | Recall@1 | Recall@2 | Arquivos recuperados no top-2 |
| --- | --- | ---: | ---: | --- |
| `marshmallow-code__marshmallow-1343` | `2be2d83a1a9a6d3d9b85804f3ab545cecc409bb0` | 1 | 1 | `src/marshmallow/schema.py`, `src/marshmallow/fields.py` |
| `marshmallow-code__marshmallow-1359` | `b40a0f4e33823e6d0f341f7e8684e359a99060d1` | 0 | 1 | `src/marshmallow/schema.py`, `src/marshmallow/fields.py` |
| `pvlib__pvlib-python-1072` | `04a523fafbd61bc2e49420963b84ed8e2bd1b3cf` | 1 | 1 | `pvlib/temperature.py` |

**Resultado agregado estritamente nesta amostra**: Recall@1 = 2/3, Recall@2 = 3/3. Esses três casos são do conjunto de desenvolvimento e já foram utilizados em investigações anteriores; não representam teste independente nem nova estimativa de eficácia. Nenhum patch novo nem teste de resolução oficial foi executado.

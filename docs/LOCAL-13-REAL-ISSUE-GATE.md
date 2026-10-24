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

# LOCAL-12 — Avaliação funcional independente da fixture LOCAL-11

## Objetivo
Verificar se a **resposta real já persistida** do Nemotron satisfaz o comportamento especificado na fixture `calculate_total(items) → sum(items)+1`, sem qualquer inferência adicional e sem executar diretamente código não confiável.

## Implementação efetiva
- `experiments/local07/fixture_functional_grade.py`: analisador AST de uma função Python estritamente limitada e interpretador de `sum(items)+constante`. Usa quatro entradas determinísticas: lista vazia, unitária, positiva múltipla e com números negativos. Rejeita importações, múltiplos comandos, chamadas desconhecidas, acesso a atributos e nós AST não permitidos; **não usa `eval`, `exec` nem importa a fonte gerada**. Recusa resposta com esquema diferente de `{schema:1,file:'calculator.py',content:<string>}`. Registra SHA256 do JSON avaliado.
- `experiments/local07/test_fixture_functional_grade.py`: casos corretos, incorretos, código inseguro e contrato inválido, agrupados com os contratos LOCAL-07/09/10/11.
- GitHub Actions [#40056751897](https://github.com/oigorbrito/local/actions/runs/40056751897): **21/21 PASS** na branch `experiment/local11-windows-smoke`, sem Ollama.

## Homologação da resposta real no Windows, sem modelos
Na branch `experiment/local11-windows-smoke` atualizada, usando o arquivo preservado no LOCAL-11:

```powershell
python .\experiments\local07\fixture_functional_grade.py `
    --response-json .\runs\local11-fix02\model-response.json `
    --output .\runs\local12\functional-result.json
Get-Content .\runs\local12\functional-result.json -Raw
```

**Nenhuma inferência é executada.** O verificador recusa estrutura que escape ao pequeno subconjunto AST, o que deve ser classificado como `UNSUPPORTED_AST` e não automaticamente como solução incorreta.

## Critérios, integridade e limites
- `FIXTURE_PASS` = os quatro casos receberam o valor esperado **sob a semântica restrita do interpretador AST**, e o SHA256 da resposta coincide com o arquivo esperado.
- `FIXTURE_FAIL` = uma expressão suportada produziu resultado errado.
- `UNSUPPORTED_AST` = resultado não avaliado por desenho do gate; não é falha comprovada do modelo.
- A origem observada no LOCAL-11 anterior tem SHA256 `774079098d0e0383c0d19819046e2e5c0be8b7f20dc45b3e5b3205a61e6d3783`, confirmado pelo usuário. O relatório real do Windows confirmou **FIXTURE_PASS (4/4)** com hash idêntico; saída esperada e obtida: `[1,2,6,6]`. O avaliador AST não executou código gerado e não constitui prova de resolução de issues reais.
- **Não** demonstra execução real do código candidato, resolução de issue SWE-bench, generalização a outros códigos ou segurança de aplicações arbitrárias.
- Nenhum benchmark anterior foi repetido; a PR #20 permanece draft e não deve ser integrada antes da revisão de segurança e evidência real.

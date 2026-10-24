# LOCAL-09 — Contrato de executor e adaptador Ollama (offline)

## Componentes implementados
- `experiments/local07/executor_bridge.py`: protocolo JSON v1 de resposta de executor (`schema,file,content`), allowlist de caminhos vindos do retriever, limite de 256 KiB de resposta e 160 mil caracteres de fonte, replay determinístico através de `integrated_edit.assess`. Recusa esquema extra ou incompatível.
- `experiments/local07/ollama_adapter.py`: adaptador para `/api/generate` do Ollama **apenas por invocação explícita da CLI**. Restringe host a loopback, define stream=false, format=json, temperatura=0, num_ctx=4096 e num_predict=2048. Limita bytes recebidos e tempo de conexão. Nenhuma execução automática, nenhuma chave externa e nenhuma chamada no CI.
- `test_executor_bridge.py` e `test_ollama_adapter.py`: testes sobre repositório Git temporário e transporte HTTP simulado, sem rede.
- `.github/workflows/local07-offline.yml`: um gate compilação + contratos agrupados.

## Gate observado
GitHub Actions [#40044808501](https://github.com/oigorbrito/local/actions/runs/40044808501): **8/8 testes PASS, saída exit 0**. Inclui o LOCAL-07 existente, contratos inválidos, origem suja, edição permitida e transporte Ollama simulado. Não mede desempenho, qualidade do modelo ou resolução SWE-bench.

## Limites de segurança e eficácia
- O conteúdo que sai de um LLM não é executado nesta etapa: a ponte gera apenas diff aplicável em worktree descartável, com validação de sintaxe e escopo. A classificação é `PATCH_APPLICABLE_NOT_GRADED`, jamais issue resolvida.
- Textos de issue e conteúdo do repositório são entradas potencialmente não confiáveis; a ponte não interpreta comandos que apareçam nesses textos, mas os envia como dados ao modelo quando invocado explicitamente.
- A requisição usa HTTP local sem TLS, logo não deve ser exposta em interface pública ou endpoint remoto. Host loopback explícito.
- Política de não repetição: modelos Nemotron/Qwen/LFM e issues já avaliados não foram reexecutados.
- Os testes **não** provam que o servidor Ollama real esteja disponível nem que algum modelo produza JSON válido. Gate da integração de rede real é `NOT_RUN` por política de não executar novas inferências sem justificativa.
- Os testes **não** provam segurança de executar os patches resultantes. Testes oficiais de resolução continuam requerendo ambiente isolado e avaliação independente.

## Uso somente opt-in
```powershell
python experiments/local07/ollama_adapter.py --repo C:\path\to\checkout --issue-json issue.json --model nemotron-3-nano:4b --report result.json --patch candidate.patch
```

Esse comando **efetivamente gera uma resposta de modelo**; não foi executado nesta campanha. Para replay sem chamadas, use `executor_bridge.py --repo ... --issue-json ... --response-json previously_saved_response.json --report ... --patch ...`.

## Política de merge
Branch experimental, PR draft, revisão e merge manuais. Nenhuma mudança automática na main.

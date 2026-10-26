# LOCAL-WINNER — caminho mínimo para escolher o melhor pontuador

Objetivo: **classificar relativamente quatro modelos locais**, não certificar excelência.
Não copiar, modificar ou incorporar o código de SWE-bench/mini-SWE-agent.
Usar os comandos oficiais instalados em ambiente Python isolado.

## Contrato (3 problemas, 4 modelos, 12 corridas)
Dataset: SWE-bench Lite, split dev. Casos previamente congelados:
- pvlib__pvlib-python-1854
- sqlfluff__sqlfluff-2419
- pyvista__pyvista-4315

Candidatos: Nemotron 4B, LFM2.5 2.6B, Qwen3.5 2B, Ministral 3 3B.
Resolver tags concretas e digests pelo `ollama list` antes da execução.
Executar cada modelo uma vez por caso, sob o mesmo orçamento, temperatura e ambiente.
Manter serial (`--workers 1`) porque o notebook possui 16 GB RAM e GTX 1650 4 GB.

## Dependências
- Ollama local disponível em loopback, com os modelos já instalados.
- Docker Desktop Linux containers funcionando; execução do SWE-bench em contêineres isolados.
- Ambiente Python separado: `python -m venv .venv-winner` e instalar o pacote oficial `swebench`, que oferece `swebench infer` e avaliação. Congelar versões com `pip freeze`; não usar modelo ou tag `latest` sem digest.
- Verificar `swebench infer lite --help` antes de executar; a interface pode evoluir.

## Execução mínima oficial
Para cada tag exata do Ollama e cada caso, executar o equivalente a:

```bash
swebench infer lite --split dev --filter '^pvlib__pvlib-python-1854$' -m ollama_chat/<TAG_REAL> --run-id lw-nemotron-pvlib -w 1
```

Trocar `--filter`, `-m` e `--run-id` pelas 12 combinações.
O prefixo `ollama_chat/` depende da configuração do LiteLLM; confirmar na configuração do mini-SWE-agent instalado antes de iniciar.
Não usar `LocalEnvironment` no host para comandos gerados pelo modelo: exigir modo Docker.
O comando produz trajetórias e previsões; NÃO constitui uma resolução validada.

Avaliar as previsões resultantes com o **avaliador oficial SWE-bench** usando o mesmo dataset/split e identificar o conjunto `resolved_ids` de cada corrida. Se Docker não executar, declarar `INFRA_BLOCKED` e não pontuar um modelo como erro.

## Classificação
- Pontuação principal = total de IDs resolvidos pelo avaliador oficial (0..3).
- Empate = menor soma do tempo de geração e avaliação nas três tarefas, comparado apenas quando todas as corridas terminaram sem falha de infraestrutura.
- Persistindo empate = **empate técnico**. Não inventar vencedor único nem usar ordem nominal como desempate.
- O modelo mais pontuador é o **vencedor relativo**, mesmo com 1/3; 0/3 para todos = empate de 0, sem vencedor isolado.
- Registrar também quantização, digest, RAM/VRAM, patches, versões, parâmetros e logs sanitizados.
- Não usar as outras cinco tarefas antes de decidir se há necessidade de desempate; elas são holdout previamente congelado. Caso o empate persista e os recursos permitam, usar esse holdout sem alterar o protocolo.

## Estado
PR #35 continua com oráculo funcional bloqueado por Docker exit 128.
Nenhuma das 12 corridas foi executada nesta sessão; vencedor **ainda não demonstrado**.
Não misturar CI dos scripts com benchmark dos modelos.

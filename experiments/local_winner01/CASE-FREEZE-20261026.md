# LOCAL-WINNER-01 | Congelamento de oito tarefas reais

Data: 2026-10-26. Status: **CASE_FREEZE_SOURCE_COMMITS_VERIFIED / FUNCTIONAL_ORACLE_PENDING**.

## Proveniência

- Dataset público canônico: `princeton-nlp/SWE-bench_Lite`, split `dev`, 23 linhas.
- SHA-256 exato da resposta JSON obtida no CI: `b82cf1a71e34f752a1870335f1f987f41256ecf2ca33b9c96a5f2aa811533627`.
- Seleção determinística: `LOCAL-WINNER-01-freeze-2026-10-26-v1`, SHA-256 de `seed:instance_id`, máximo de duas issues por repositório.
- Três casos já utilizados foram excluídos: `marshmallow-code__marshmallow-1343`, `marshmallow-code__marshmallow-1359`, `pvlib__pvlib-python-1072`.
- CI de execução e testes offline: https://github.com/oigorbrito/local/actions/runs/40377023386 — **20/20 PASS**; consulta oficial do dataset PASS; seleção/artefato PASS.
- Artefato exato: ID `12674913479`, nome `local-winner01-candidate-cases`, digest do ZIP `sha256:1a7fa8cdb93176b7726a280d77e76a4f01e2564c70f142b90de5374b89ec758c`, expiração 2026-11-25. Contém `manifest.json` e oito `issue.json`, **sem patch gold/teste de referência**.

## Instâncias congeladas

| Etapa | ID | Repositório / commit-base Git SHA-1 | GitHub commit API |
| --- | --- | --- | --- |
| Eliminatória | `pvlib__pvlib-python-1854` | `pvlib/pvlib-python` / `27a3a07ebc84b11014d3753e4923902adf9a38c0` | verificado |
| Eliminatória | `sqlfluff__sqlfluff-2419` | `sqlfluff/sqlfluff` / `f1dba0e1dd764ae72d67c3d5e1471cf14d3db030` | verificado |
| Eliminatória | `pyvista__pyvista-4315` | `pyvista/pyvista` / `db6ee8dd4a747b8864caae36c5d05883976a3ae5` | verificado |
| Final | `sqlfluff__sqlfluff-1625` | `sqlfluff/sqlfluff` / `14e1a23a3166b9a645a16de96f694c77a5d4abb7` | verificado |
| Final | `pydicom__pydicom-1256` | `pydicom/pydicom` / `49a3da4a3d9c24d7e8427a25048a1c7d5c4f7724` | verificado |
| Final | `pylint-dev__astroid-1196` | `pylint-dev/astroid` / `39c2a9805970ca57093d32bbaf0e6a63e05041d8` | verificado |
| Final | `pvlib__pvlib-python-1707` | `pvlib/pvlib-python` / `40e9e978c170bdde4eeee1547729417665dbc34c` | verificado |
| Final | `pydicom__pydicom-901` | `pydicom/pydicom` / `3746878d8edf1cbda6fbcf35eec69f9ba79301ca` | verificado |

**Verificação do commit-base:** cada SHA foi consultado no endpoint Git Database Commit do respectivo repositório por GitHub connector, retornou o mesmo SHA e confirmou um commit com um pai. Isso prova existência e identidade remota, **não** prova que o checkout, importação de testes, baseline ou gold patch funcionem no Windows.

## Gates antes de inferência

1. Conciliar inventário de evidências do Windows: `reconcile.py` deve informar `history_complete=true`, sem vínculos ausentes, falsos `PASS` ou evidência sobrescrita. Ainda pendente.
2. Baixar/fixar checkouts dos oito commits em ambiente isolado. Verificar baseline falhar nos testes oficiais independentes e correção de referência passar, sem expor patch gold aos modelos. Ainda pendente.
3. Congelar digests e orçamento da competição antes da primeira chamada. Somente então executar 4 modelos x 3 tarefas inéditas, depois os 2 melhores x 5 tarefas holdout com até um reparo por tarefa. Não reutilizar nenhum caso histórico, nem misturar protocolos.

**Nenhum modelo foi chamado neste bloco.** A PR é Draft, merge manual, `main` intocada. Não existe vencedor demonstrado.

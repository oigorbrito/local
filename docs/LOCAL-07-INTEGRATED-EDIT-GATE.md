# LOCAL-07 — Gate integrado de recuperação + diff seguro (2026-10-23)

## Escopo efetivamente executado
Implementação `integrated_edit.py` liga o recuperador determinístico `retrieve_context.py` a edições **externamente fornecidas** (sem geração por LLM). A seleção do arquivo editável é limitada aos dois primeiros resultados do recuperador, com controle de caminho, symlink, `ast.parse`, checkout Git limpo, SHA256 de origem, worktree temporária e `git diff --check` + `git apply --check`. O checkout original não é editado. Patches gold e testes oficiais não entram no prompt ou no recuperador. Não houve inferência.

## Testes e evidências
- Contratos integrados: `python -m unittest -q test_integrated_edit` → **2 testes PASS**, cobrindo patch aplicável, isolamento, rejeição de caminhos indevidos, sintaxe inválida e origem suja.
- `python -m py_compile retrieve_context.py integrated_edit.py real_checkout_gate.py` → PASS.
- Execução integrada adicional em **três commits-base reais recuperados dos ZIPs fornecidos**; modificações sintéticas reversíveis (comentário), explicitamente **não são soluções das issues**:
  - `marshmallow-code__marshmallow-1343`, `src/marshmallow/schema.py`: recall rank 1; diff aplicável; fonte preservada.
  - `marshmallow-code__marshmallow-1359`, `src/marshmallow/fields.py`: recall rank 2; diff aplicável; fonte preservada.
  - `pvlib__pvlib-python-1072`, `pvlib/temperature.py`: recall rank 1; diff aplicável; fonte preservada.
- Conjunto: **3/3 diffs sintéticos verificáveis**, **3/3 checkouts originais inalterados**, Recall@2 3/3. Isso é gate de integração, **não uma taxa de resolução SWE-bench**.
- Instrumentação: `local07-real-gate.json` inclui commits-base, ranks, hashes de patches e limites de contexto.

## SHA256 dos artefatos
- `retrieve_context.py`: `41fa4efd9e73f33b828ec754e06c902a7f7fddb18d6953ea64fcd635351d4cd9`
- `integrated_edit.py`: `10e1e219160600f3dcd6826a5d03a0bdfe44680882754007a15a0f627a0464c4`
- `test_integrated_edit.py`: `b38a2f97b000a30ee217f003447a6d18ff8fd901810f6dafa81ea60e8ffd4695`
- `real_checkout_gate.py`: `6f476b3e2528535f35915f2871c4a06d0d916203acef8bbda0ff497111213f34`
- `local07-real-gate.json`: `b50f4b1179fc8f12cb8eb350483cc537248ea70159b14a9e73c1a0df1ba69c97`

## Fronteira de confiança e estado
Os scripts completos e JSON estão no artefato `LOCAL-07-integrated-edit.zip` anexado à conversa, **não no GitHub nesta mudança**. Esta PR contém o relatório e seu inventário de hashes; para executar no repositório será necessário incorporar os arquivos sob revisão em commit posterior. Não registrar um teste como aprovado no CI sem que código e fixtures estejam presentes lá.

Estado: `OFFLINE_RETRIEVAL_AND_PATCH_GATE_PASS`. Permanecem pendentes: revisão independente, integração a um executor real sem exposição de oráculos, e avaliação oficial sobre patches efetivamente produzidos por modelos. Não houve novas inferências, merges ou alteração da main.

# HarnessBench — filtro de hardware do LOCAL (23/10/2026)

Hardware-alvo: Windows 11, 16 GiB de RAM, GPU com 4 GiB de VRAM, inferência local sequencial.

## Inventário verificado
Árvore do upstream ya5h-P/harnessbench main: 200 diretórios ativos contendo task.json; SHA da árvore 2eabe3c9732ec412464219bf84ab6750f66298f8. Soma dos blobs desses 200 diretórios aproximadamente 2,80 MB. Maior diretório bigfile_12 ~154 KiB; nenhum diretório ultrapassa 1 MB. A simples dimensão das fixtures NÃO demonstra custo de inferência ou viabilidade do modelo.

## Exclusão e quarentena
- EXCLUÍDAS POR INCOMPATIBILIDADE MATERIAL COM HARDWARE: **0 confirmadas**. Nenhuma tarefa contém, no inventário de arquivos e metadados inspecionados, prova de requisito de GPU com mais de 4 GiB ou RAM acima de 16 GiB.
- **QUARENTENA PREVENTIVA, NÃO EXECUTAR NA PRIMEIRA CAMPANHA (7)**: bigfile_09, bigfile_10, bigfile_11, bigfile_12, needle_10, needle_11, needle_12. Justificativa: maior volume de contexto ou busca multi-arquivo, com risco de latência/limite de contexto. Exige medida do prompt real e memória residente; NÃO inferir inviabilidade apenas pelo número de arquivos. needle_12 traz descrição de 320 arquivos e timeout_s 900.
- **CANDIDATAS À PRÉ-VALIDAÇÃO SEM INFERÊNCIA: 193**. Ainda não são declaradas compatíveis; dependem do runtime, do quant, do tamanho de contexto efetivo e do budget.

## Critério objetivo de corte após medições
A unidade elegível é tarefa + harness + modelo + quantização + runtime (não tarefa isolada). O gate mede pico de RAM do processo, VRAM, prompt tokens, contexto aceito, tempo de pré-processamento, consumo durante inferência e health do servidor. Exclusão só após falha reproduzível de recursos em condições controladas, não por timeout isolado, saída errada, falha de API ou dificuldade nominal. Um modelo com offload parcial pode executar tarefa que não caiba inteiramente na VRAM. A campanha usa uma concorrência, hardware-alvo e logs brutos. Nenhuma inferência nova foi acionada nesta triagem.

## Não repetir
A tarefa balanced_parens tem sobreposição temática com a triagem sintética anterior mas não é execução idêntica confirmada. Manter esse identificador em revisão semântica separada do corte de hardware.

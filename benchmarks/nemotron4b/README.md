# Nemotron 3 Nano 4B — comparação funcional no Windows

Duas alternativas reais, mesma GPU do Windows e mesmo Ollama: executor
LOCAL-09 já integrado em main versus Cloi 2.1.0 fixado no commit
1da62db7aa3aed8b1e65f1e3fb69a89cf00707b9.

Requisitos: Windows 11, Python 3, PowerShell, Docker Desktop com Engine Linux
ativo, Ollama ouvindo APENAS em 127.0.0.1:11434 e o modelo
nemotron-3-nano:4b quantizado Q4_K_M.

No PowerShell, na raiz do repositório:

    ollama pull nemotron-3-nano:4b
    ollama show nemotron-3-nano:4b
    .\benchmarks\nemotron4b\run.ps1 -Repeats 3

O contêiner roda com **--network none**. A ponte relay_host.py, executada
no Windows, encaminha por stdio apenas GET /api/tags e POST /api/show,
/api/chat e /api/generate para 127.0.0.1:11434. Ela recusa outro modelo,
outros endpoints e outras portas. Não é necessário host networking.
Não altere OLLAMA_HOST para 0.0.0.0. Docker Engine deve estar ativo;
o script nunca tenta iniciá-lo ou modificar configurações do Windows.

Uma fixture Git limpa é recriada para cada tentativa dentro do contêiner.
Os testes de segurança do caminho exercitam traversal, caminhos absolutos
e symlink para fora da raiz; precisam falhar no original. Apenas mudanças
em guard.py são aceitas. Um teste independente, não alterado pelo agente,
deve passar após a edição. Modelo, digest, quantização e janela de 4096
tokens são iguais. Temperatura 0; Cloi sem modelo de fallback.

Os resultados ficam fora do Git, na pasta irmã local-nemotron-comparison:
report.json, result.patch, logs por tentativa e arquivos da execução
LOCAL-09. Respostas brutas do Ollama ficam em raw-ollama-responses/,
com SHA-256 indexado em relay-request-metrics.jsonl, inclusive quando
o LOCAL-09 rejeita um JSON ou não produz patch. Não há commit nem merge automático.

LIMITAÇÕES: o broker fixa num_predict=2048, num_ctx=4096 e temperatura=0
em cada chamada do Ollama, para ambos os executores. O número de chamadas
por tarefa ainda difere; o resultado em uma única fixture não declara
vencedor geral. Métricas por chamada são retidas em relay-request-metrics.jsonl.

SEGURANÇA: Docker executa o Cloi com --yes apenas na fixture descartável,
com --network none, rootfs read-only, sem mounts de HOME/socket Docker.
Apenas fixture e módulos LOCAL-07 são montados read-only. A única
comunicação com o Windows é o proxy de quatro endpoints Ollama por stdio.
Isso não prova segurança absoluta contra exploração de contêiner ou Docker.
Não execute conteúdo não confiável se o runtime do Docker estiver comprometido.

A fixture nova é uma reprodução de escape por symlink. Não afirmamos
que corresponde byte a byte à antiga tarefa congelada do LOCAL-19.

Verificação offline da ponte (não exige Docker Engine nem inferência):

    python -B -m unittest discover -s .\benchmarks\nemotron4b -p test_relay_*.py -v

O script run.ps1 executa esse gate antes de iniciar o contêiner.
Para sair do bloqueio atual, inicie o Docker Desktop e confirme que
`docker info --format '{{.ServerVersion}}'` apresenta a versão do servidor.

## LOCAL-27: perícia determinística de tentativas reprovadas

Duas medições reais realizadas em 25/10/2026 e 26/10/2026 tiveram 0/3
aprovações por executor, com falhas de aplicação de patch do LOCAL-09 e
timeout/conectividade no Cloi. Estes registros **não** classificam
superioridade entre executores. O digest registrado foi
`d94b6dfae26d340fd16599d8cd5301945bb42b6bd7a7c70f2078559562f60cbe`
(Q4_K_M).

Não repetir geração para diagnosticar um erro cujo JSON já está persistido.
Após atualizar a branch experimental, com Docker Engine ativo e a imagem
`local-nemotron4b-comparison:cloi-2.1.0` construída, executar no PowerShell:

    .\benchmarks\nemotron4b\audit.ps1

O script monta os dois diretórios de evidência anteriores **somente leitura**,
sem rede e sem chamada a Ollama. Para o `r01-local09` de cada rodada, verifica
o hash SHA-256 da resposta bruta do relay e confere os bytes do JSON recebido;
reexecuta o validador original em fixture Git descartável; e, separadamente,
materializa a fonte candidata em outra fixture para aplicar o oráculo de seis
testes sem alterar resultados antigos. Os relatórios e patches diagnósticos
ficam em um novo `local-nemotron-audit-AAAAMMDD-HHMMSS` e incluem
`offline-audit.json`, `candidate.patch`, `independent-tests.log` e, quando
houver falha, `replay-trace.log`.

Se `replay=REJECTED` e `direct.functional_passed=true`, investigar uma
divergência do validador antes de mudar a geração; se
`direct.functional_passed=false`, o candidato ainda não resolveu os testes.
Esse ensaio **não** contorna validação em produção nem prova o comportamento
com outras tarefas. Como o conteúdo fornecido pelo modelo é executado como
código Python, a análise é restrita ao contêiner descartável sem rede e com
limites de recursos; não executar a fonte no host Windows.

O benchmark agora reporta qualidade funcional independentemente do exit code
do executor, e aborta novas tentativas após timeout/indisponibilidade de Ollama,
evitando contaminar as rodadas seguintes. `summary.total` é o número de
tentativas realmente executadas; `summary.requested` é a meta inicial.
Métricas de transporte passam a registrar conclusão de resposta e tempo por
requisição, para não tratar HTTP 200 como prova de resposta efetivamente
recebida.


## Resultado observado no Windows — auditoria de 26/10/2026

As duas execuções anteriores usaram o mesmo `nemotron-3-nano:4b`,
digest `d94b6dfae26d340fd16599d8cd5301945bb42b6bd7a7c70f2078559562f60cbe`.
A perícia sobre `r01-local09` em cada diretório encontrou **o mesmo**
JSON de resposta (`d5ae735b366616bdfec1fdaffcbfdde86ffdc1247008d06c84f251dfea39bf1f`)
e o mesmo candidato Python (`fe3e34bb16bcbc66b51c9d7dcb8361ee9200e02f5b54e1f18ed71119b16ce81a`).
Os bytes da resposta bruta corresponderam ao JSON persistido.

Na versão antiga do validador, `replay` rejeitou esse candidato com
`GIT_APPLY_CHECK_FAILED: guard.py:1`, mas a materialização direta em
checkout Git descartável gerou um patch de **954 bytes**, aplicável ao
índice e aprovado por **6/6 testes independentes**. É um único candidato
funcional observado duas vezes, não dois sucessos amostrais independentes.

A correção posterior de `integrated_edit.py` preserva os bytes integrais
do `git diff` na checagem do índice, com testes de regressão incluindo
CRLF. Esse comportamento está validado pelo CI offline, mas a resolução
da rejeição do **candidato original específico** exige nova execução
de `audit.ps1` sobre os diretórios preservados; não reexecutar a inferência
para realizar essa perícia.

Se o validador continuar rejeitando, a auditoria grava também
`rejected-validator.patch`, com SHA-256 e resultado de uma nova
verificação contra o mesmo índice, para investigar o motivo exato
sem contornar a checagem de segurança.

O Cloi não produziu patch aprovado nas duas execuções. A instrumentação
do relay foi reforçada para diferenciar requisição HTTP aceita, resposta
integralmente transferida e estatísticas de geração; HTTP 200 sozinho
não prova que o cliente terminou de receber a resposta.


## Pós-perícia: experimento contrabalançado com Cloi primeiro

O replay histórico realizado em `D:\projetos\local-nemotron-audit-20261026-004733`
confirmou `replay.status=ACCEPTED` e `direct.functional_passed=true` nos
dois registros do mesmo candidato, com patch de 954 bytes e os seis testes
PASS. A falha de aplicação do patch está resolvida nesse caso concreto.

As tentativas anteriores de Cloi sofreram timeout da execução e, nas
repetições posteriores já contaminadas, falha no preflight de conectividade.
O CI offline não prova a causa da lentidão. O próximo ensaio começa com
**Cloi primeiro**, permitindo observar o braço que não teve um patch
validado antes de executar LOCAL-09. Isso NÃO muda o modelo, o hardware,
a temperatura, o contexto, os testes nem os limites por tentativa:

    .\benchmarks\nemotron4b\run.ps1 -Repeats 3 -FirstExecutor cloi -OutputDir D:\projetos\local-nemotron-comparison-cloi-first

A ordem continua alternada: `R1 Cloi→LOCAL-09`, `R2 LOCAL-09→Cloi`,
`R3 Cloi→LOCAL-09`. Falha de transporte/timeout interrompe a matriz
imediatamente, mantendo o relatório parcial sem calcular rankings
enganosos. Cada arm possui seu diretório e métricas de geração
separadas das chamadas de preflight.

Interpretar 2s de saída por preflight como falha de disponibilidade,
não velocidade de resolução. Em `relay-request-metrics.jsonl`, verificar
`path`, `elapsed_seconds`, `response_complete`, `error_type`,
`usage_available` e as respostas brutas por SHA-256 para distinguir
um HTTP 200 de geração efetivamente concluída. Não escolher vencedor
a partir de uma única fixture.


## Cloi-first real: timeout após 420,175 s

Rodada real iniciada em 26/10/2026 com `-FirstExecutor cloi -Repeats 3`
e resultados em
`D:\projetos\local-nemotron-cloi-20261026-010735`.
A tentativa `r01-cloi` atingiu 420,175 segundos e foi encerrada por
`EXECUTOR_WALL_TIMEOUT`, sem patch aprovado. A política fail-closed
interrompeu a matriz; LOCAL-09 não foi executado nessa rodada.
A ordem inicial agora descarta a explicação de que Cloi só falhava
por ter sido executado depois de LOCAL-09. A causa exata do timeout
ainda não foi estabelecida: pode envolver geração, transporte ou loop
do executor; o relógio de 420 s, sozinho, não permite distinguir.

Para diagnosticar **sem GPU e sem Docker**, depois de atualizar a
branch, execute em PowerShell:

    python -B .\benchmarks\nemotron4b\diagnose.py --results "D:\projetos\local-nemotron-cloi-20261026-010735"

O comando imprime somente estados, contagens, hashes, latências e
integridade de respostas brutas, sem divulgar o texto dos prompts,
código gerado ou conteúdo das respostas. As execuções antigas não
registravam o início de cada requisição: se uma thread do relay
continuava pendente ao fechar o contêiner, **não há como inferir seu
endpoint apenas pela ausência da métrica final**. A partir da
instrumentação atual, o host grava também
`relay-request-starts.jsonl` antes de iniciar cada worker e
`diagnose.py` relaciona requisições iniciadas às finalizadas.
O arquivo de eventos não contém corpo de requisição nem prompts.

O ensaio original `r01-local09`, preservado em dois diretórios,
produziu um único patch de 954 bytes, cujo replay final no Windows
foi `ACCEPTED` e passou 6/6 testes independentes. Essa evidência
é separada da rodada Cloi-first bloqueada por tempo.


## LOCAL-27: Cloi-first após o timeout — limites do diagnóstico

A execução `local-nemotron-cloi-20261026-010735` foi diagnosticada
offline: o preflight `/api/tags` retornou HTTP 200 em 0,141 s;
no braço `r01-cloi`, duas chamadas `GET /api/tags` retornaram
200 em 0,141 s e 0,125 s; `POST /api/show` retornou 200 em
0,015 s. Todas essas quatro respostas foram integralmente transferidas,
e o timeout de parede foi 420,175 s, sem patch. Nenhuma requisição
`/api/chat` chegou a registrar métrica terminal; **isso não prova
que a requisição não tenha começado**, pois as versões antigas não
persistiam requisições iniciadas nem progresso antes da conclusão.

Para retirar o último sinal disponível desses mesmos arquivos sem
gerar novos tokens, o `diagnose.py` também consulta uma **cópia
temporária** do banco SQLite `r01-cloi/cloi-data/cloi.db`, junto
com os arquivos WAL/SHM disponíveis. Ele devolve apenas totais de
sessões, mensagens por papel e ferramentas utilizadas; nunca imprime
mensagens, código ou prompts. Assim distinguimos uma sessão que
gravou somente o pedido inicial de uma sessão que concluiu turnos e
executou ferramentas. Ausência do banco ou falha de leitura é
reportada explicitamente, sem dedução de resultado funcional.

Nas próximas execuções, `relay-request-starts.jsonl` e
`relay-request-events.jsonl` registram início e fases de cada
chamada `/api/chat` antes de a geração terminar: pedido encaminhado
ao host, cabeçalhos recebidos, primeiro chunk, progresso de streaming
a intervalos de pelo menos 15 segundos de tempo monotônico, frame
`done` e envio integral ao contêiner. Somente IDs, tempos, número
de bytes e códigos HTTP são incluídos nos eventos. A alteração não
muda temperatura, modelo, contexto, limites ou fluxo de ferramentas.
Esses eventos **não estão retroativamente disponíveis** na rodada
histórica e não justificam reexecução de 420 s sem uma hipótese nova.

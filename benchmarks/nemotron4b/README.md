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


## LOCAL-27: Cloi provider preflight sem inferência

A perícia histórica encontrou resposta completa de `POST /api/show`
(22.704 bytes) no host, mas nenhum `cloi.db` em
`r01-cloi/cloi-data`. No commit fixado de Cloi, o banco é criado
por `Session.create()` **depois** de `supportsTools(model)`,
que aguarda `fetch('/api/show').json()`. Assim, as observações
são compatíveis com um bloqueio no preflight do cliente Node,
mas não provam em qual lado da ponte o fluxo parou.

Antes de repetir a geração, executar na branch experimental:

    .\benchmarks\nemotron4b\run.ps1 -ProbeOnly -OutputDir "D:\projetos\local-nemotron-cloi-preflight"

O modo usa as **funções reais do fornecedor Cloi 2.1.0**
(`isReachable`, `listModels` e `supportsTools`) para validar
a leitura integral dos metadados e suporte à capacidade `tools`,
no mesmo contêiner sem rede e através do mesmo relay. Não invoca
`/api/chat` ou `/api/generate`. O subprocesso Node tem
timeout de **15 segundos**, com etapas duráveis em
`cloi-preflight-probe/stderr.log`, métricas de início/progresso/fim
no relay e `report.json` com `PROBE_PASS` ou `PROBE_BLOCKED`.

Se parar após `PROBE_SHOW_REQUEST_BEGIN`, confrontar
`relay-request-events.jsonl` para distinguir envio ao upstream,
recebimento de cabeçalhos, primeiro chunk e conclusão de transmissão.
Se houver `PROBE_SHOW_JSON_PARSED`, o cliente Node concluiu
esse preflight específico e a investigação deve seguir para o
ciclo de início de sessão, sem atribuir um bug ao transporte.
Esse teste ainda não executa o agente nem garante qualidade de
correção. Não iniciá-lo com uma pasta que já contém um relatório.


## LOCAL-27: teste controlado do executável Cloi, sem gerar tokens

O ensaio real no Windows `-ProbeOnly` concluiu em **0,709 s**:
`PROBE_TAGS_HTTP_OK`, `PROBE_TAGS_JSON_PARSED`,
`PROBE_SHOW_JSON_PARSED` e `PROBE_PREFLIGHT_PASS`.
Esse resultado refuta que a ponte do provedor esteja
sistematicamente impedida de completar a leitura dos metadados.
Entretanto, a sonda não criou sessão nem iniciou o executável principal.

Foi acrescentado `-StartupProbe`, que executa o **Cloi CLI fixado
em 1da62db7**, com o mesmo arquivo de configuração, `CLOI_DATA_DIR`,
contêiner sem rede e fixture independente, mas concede somente
**20 s** para a inicialização do processo. O relay intercepta e
**recusa qualquer POST /api/chat ou /api/generate antes do upstream**,
retornando `DIAGNOSTIC_GENERATION_BLOCKED`; nenhuma geração
é encaminhada ao Ollama. O probe termina positivamente quando
a sessão SQLite foi criada e o próprio Cloi observou essa
recusa deliberada, demonstrando que alcançou a primeira
solicitação ao modelo:

    .\benchmarks\nemotron4b\run.ps1 -StartupProbe -OutputDir "D:\projetos\local-nemotron-cloi-startup"

Em `report.json`, `STARTUP_REACHED_GENERATION_GATE`
significa que o CLI passou pelo preflight, iniciou sessão e
alcançou `/api/chat` (bloqueado intencionalmente); **não é**
êxito em correção de código. `STARTUP_BLOCKED` conserva
timeout de 20 s, ausência ou erro SQLite, stdout/stderr,
estágios e eventos do relay para a investigação seguinte.
Não confundir a recusa esperada `DIAGNOSTIC_GENERATION_BLOCKED`
com falha real do Ollama. O teste não modifica o modelo,
a qualidade avaliada, os seis testes independentes nem a
configuração das comparações.


## LOCAL-27: diferenciação SQLite bind mount vs tmpfs

Na execução real do `-StartupProbe` (26/10/2026, evidências em
`D:\projetos\local-nemotron-cloi-startup-20261026-014944`), os
31 testes offline passaram, mas o CLI original Cloi 2.1.0 atingiu o
timeout de **20,022 s** sem criar `cloi-data/cloi.db` e sem chegar à
recusa deliberada de `/api/chat`. O `-ProbeOnly` do próprio
provedor Node já havia concluído `/api/tags`, `/api/show` e
capacidade de ferramentas em **0,709 s**. Isso direciona a perícia para
os passos entre o preflight e a criação da sessão, mas não demonstra
isoladamente falha do SQLite ou do volume.

O Cloi fixado usa `Session.create()`, que abre `node:sqlite` e
configura `PRAGMA journal_mode=WAL`. Para isolar o comportamento do
filesystem, executar no Windows, a partir desta branch:

    .\benchmarks\nemotron4b\run.ps1 -SqliteProbe -OutputDir "D:\projetos\local-nemotron-cloi-sqlite"

A sonda usa exatamente o módulo de persistência **upstream fixado**
e testa a criação de sessão/mensagem em dois `CLOI_DATA_DIR`:
(1) subdiretório novo de `/results` montado do Windows e
(2) diretório descartável em `/tmp` do contêiner.
Cada subprocesso Node possui timeout de **8 segundos**.
Nenhum endpoint de geração é chamado e nenhuma alteração é realizada
no projeto de origem ou no Cloi doador.

O relatório JSON contém os estágios e status de ambos os ambientes:

- `SQLITE_MOUNT_SUSPECTED`: somente o teste no volume montado falhou,
  enquanto `/tmp` passou; investigar SQLite/WAL/driver de montagem
  do Windows antes de mudar o modelo ou o agente.
- `SQLITE_BOTH_PASS`: o SQLite isolado não reproduziu o travamento;
  continuar investigando o percurso integrado do CLI original.
- `SQLITE_NOT_ISOLATED`: `/tmp` também falhou; não atribuir
  causalidade exclusiva ao volume montado.

`cloi-sqlite-probe/mounted-results.stderr.log` e
`cloi-sqlite-probe/tmpfs.stderr.log` contêm somente marcos como
`SQLITE_STAGE_SESSION_CREATE_BEGIN`, sem código de usuário ou
conversa. Os relatórios anteriores não são alterados.

## LOCAL-27: SQLite isolado PASS; observação da inicialização integrada

Resultado real no Windows (26/10/2026): SQLITE_BOTH_PASS.
Persistência upstream node:sqlite/WAL no volume Windows: 0,207 s, PASS.
No Docker /tmp: 0,061 s, PASS. Ambos criaram cloi.db e persistiram
uma mensagem. São medições únicas e não uma comparação de desempenho.

O provedor Cloi isolado passou em 0,709 s, mas o CLI completo anterior
bloqueou por 20,022 s, sem cloi.db nem início de geração comprovado.
SQLite isolado não explica esse bloqueio. O próximo diagnóstico amplia
o modo -StartupProbe, mas continua SEM chamada efetiva de geração:

    .\benchmarks\nemotron4b\run.ps1 -StartupProbe -OutputDir D:\projetos\local-nemotron-cloi-startup-traced

O runner verifica primeiro o carregamento completo dos módulos doador
via cloi --help (timeout de 6 s); se PASS, executa o CLI com um preload
passivo de node:diagnostics_channel (timeout de 20 s) e o relay bloqueia
POST /api/chat e POST /api/generate antes do upstream. Os marcos
request_created, response_headers, response_trailers e request_error
são capturados somente para rotas Ollama permitidas, com tempo e status;
não incluem prompts, conteúdo de resposta nem arquivos privados.

Consultar em report.json: startup.cli_help, startup.request_trace e
startup.session_database_present; confrontar com relay-request-events.jsonl.
Esse ensaio distingue importação travada de fetch pendente e início de
sessão; não demonstra qualidade do modelo nem causa-raiz antes da execução.

## LOCAL-27: tags SocketError após HTTP 200 no CLI real

No Windows, a versão anterior de -StartupProbe produziu CLI --help PASS
(0,206 s), mas o CLI não criou cloi.db durante 20,009 s.
O trace Undici registrou /api/tags com cabeçalhos HTTP 200; seis
milissegundos após a segunda criação de requisição /api/tags surgiu
SocketError. O trace antigo não tinha ID por requisição: esse erro
NÃO podia ser atribuído à primeira ou à segunda conexão.

O doador fixado src/provider/ollama.js tem isReachable() que retorna
res.ok SEM consumir o corpo da resposta do primeiro GET /api/tags;
listModels() então faz novo GET e consome JSON. A ponte era HTTP/1.1
com Transfer-Encoding: chunked e keep-alive implícito. Hipótese:
reutilização/fechamento de conexão com resposta anterior não consumida.

Correção experimental no relay_guest.py: Connection: close explícito
nas respostas da ponte, encerrando o socket ao concluir cada corpo
(respostas válidas HTTP/1.1 com Content-Length ou chunked). Isso não
modifica o doador, não muda modelo, limites ou dados da tarefa.

Teste ponta a ponta sem Ollama: o próprio Bridge atende um broker
falso local e um processo Node usa fetch 4 vezes na sequência
primeiro GET sem consumir corpo -> segundo GET com JSON -> POST
/api/show com JSON de 22 KiB. Confere Connection: close e corpos;
rodado também no Windows CI. Os probes reais continuam proibindo
qualquer geração; o CI não atesta que o SocketError do Windows foi
eliminado em produção.

O trace passivo agora associa request_id a cada requisição Undici e
registra request_body_sent, response_headers, response_trailers e
request_error (nome/código seguro), permitindo apontar o erro à
conexão correta sem registrar headers, prompts, URLs externos ou
conteúdo da resposta. Repetir SOMENTE -StartupProbe no Windows
em diretório novo e exigir STARTUP_REACHED_GENERATION_GATE ou
examinar eventuais SocketError por request_id. Nenhum trial de
420 s deve começar antes desse gate.

## LOCAL-27: EOF HTTP no primeiro /api/tags (Windows real)

Na execucao Windows da sonda de inicializacao de 26/10/2026,
`D:\projetos\local-nemotron-cloi-connection-20261026-022405`,
o executavel Cloi original passou `--help` em 0,126 s, mas atingiu
20,024 s de timeout antes de criar cloi.db. O trace Undici confirmou:

- GET /api/tags #1: request_created 193ms, response_headers 200 353ms
- GET /api/tags #2: request_created 357ms, request_body_sent 361ms
- GET /api/tags #1: request_error aos 362ms, HTTPParserError
  HPE_INVALID_EOF_STATE

Isso identifica um EOF de framing na PRIMEIRA resposta HTTP, e nao
uma falha de SQLite ou de inferencia; a causa exata de por que as
frames finais nao chegaram nao foi demonstrada no log historico.
Connection: close isoladamente NAO corrigiu o caso real.

Correcao experimental: relay_guest agora bufferiza so /api/tags
e /api/show ate receber `end` do broker, aplica limite de 8 MiB,
e retorna Content-Length preciso com Connection: close. Uma falha
intermediaria responde com JSON de erro HTTP, sem enviar HTTP 200
ou corpo parcial. /api/chat e /api/generate preservam streaming.
Esse comportamento evita anunciar sucesso antes do corpo inteiro
de metadados chegar, mas ainda requer validacao no Windows real.

Regressao end-to-end sem inferencia usa o servidor guest real e
Node fetch, com body de metadados atrasado/fracionado, repetindo
4 ciclos de GET nao consumido -> GET JSON -> POST /api/show.
Outro teste injeta erro apos frame start e corpo incompleto,
exigindo resposta completa de erro e proibindo HTTP 200 parcial.
Essas provas rodam no CI Ubuntu e Windows; o modelo nao e chamado.

Proximo gate: atualizar branch e executar SOMENTE `run.ps1` com
`-StartupProbe` e uma pasta nova, mantendo /api/chat bloqueado.
Somente STARTUP_REACHED_GENERATION_GATE permite voltar a uma
comparacao real do modelo. Sem merge automatico.

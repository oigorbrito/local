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

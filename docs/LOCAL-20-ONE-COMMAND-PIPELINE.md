# LOCAL-20 — execução encadeada, um comando

O `local20_pipeline.py` automatiza uma tentativa *nova* e pré-registrada do
Nemotron local. Passar um gate inicia imediatamente o seguinte. Nenhuma
aprovação, prompt ou comando intermediário é necessário.

## Gates

| Ordem | Gate | Sucesso |
| --- | --- | --- |
| 1 | PINNED_TASK_AND_PREPARATION | Checkout limpo, Git HEAD, blob e tarefa com SHA corretos; alvo entre arquivos recuperados |
| 2 | MODEL_PREFLIGHT | Ollama acessível e identidade do modelo coerente com perfil |
| 3 | REAL_GENERATION | Uma chamada autorizada, patch produzido e aplicável |
| 4 | RESPONSE_PERSISTENCE | Resposta e patch existem e seus SHA-256 coincidem com o relatório |
| 5 | PATCH_CONTRACT_AND_STATIC_CHECK | Patch revisado no alvo autorizado; checkout original não modificado |

O relatório final em `<session>/pipeline-report.json` contém os gates,
tempos, hashes e estado, e `pipeline-events.jsonl` registra os gates já
concluídos para diagnóstico após interrupção. A execução é **fail-closed**.
Sem retry, fallback ou segundo envio ao modelo se algum gate falhar.
O registro `generation-attempt.json` é a fonte de verdade para uma chamada
autorizada, inclusive quando a resposta falha. Os artefatos do modelo
permanecem na sessão e não devem ser publicados sem revisão.

O resultado `PATCH_READY_NOT_FUNCTIONALLY_GRADED` é um PASS **somente
dos cinco gates de preparação, geração, persistência e contrato**.
NÃO é sucesso funcional, não equivale a benchmark e não autoriza
executar/aplicar o patch no host. O próximo gate é uma avaliação
funcional independente em isolamento qualificado. Sem isso,
`functional_resolution=NOT_EVALUATED`.

## Execução Windows

Pré-requisitos: Python 3.12, Git, Ollama escutando em 127.0.0.1:11434,
modelo nativo `nemotron-3-nano:4b`, uma cópia Git limpa e descartável
de um **caso novo** e arquivo de tarefa congelado fora do checkout.
**Não reutilize** `local17-session-20e1b6ed` nem renomeie o caso
`oigorbrito__local-evidence-symlink-001` para simular outra tentativa.
Esse caso já teve uma chamada e não possui resposta recuperável.

No PowerShell, atribua caminhos para um runner que contenha LOCAL-20
e para um checkout limpo em commit fixo. `$task` é uma descrição
pré-registrada do defeito (sem solução, patch de referência ou oráculo).
`$target` é o caminho relativo exato do arquivo Python do defeito:

```powershell
$runner = "D:\projetos\local20-runner"
$trial = "D:\projetos\novo-caso-fixado"
$task = "D:\projetos\nova-tarefa.txt"
$target = "experiments/local07/arquivo_com_defeito.py"
$session = "D:\projetos\local20-session-$(Get-Date -Format yyyyMMddHHmmss)"
$head = (git -C $trial rev-parse HEAD).Trim()
$blob = (git -C $trial rev-parse "HEAD:$target").Trim()
$taskSha = (Get-FileHash $task -Algorithm SHA256).Hash.ToLowerInvariant()

python "$runner\experiments\local07\local20_pipeline.py" `
    --repo $trial --session $session --task-file $task `
    --case-id "local20-novo-caso-002" --expected-head $head `
    --expected-blob $blob --expected-task-sha256 $taskSha `
    --target $target --profile principal-localizado --timeout 300

if ($LASTEXITCODE -ne 0) {
    Write-Host "Falha detectada: consulte $session\pipeline-report.json"
} else {
    Write-Host "Patch pronto para verificacao funcional isolada em $session"
}
```

O exemplo pressupõe que **o commit e a tarefa já tenham sido escolhidos
antes da execução**. Extrair hashes no próprio comando facilita o uso,
mas não substitui um registro externo prévio desses valores numa
avaliação comparativa formal.

## CI

`test_local20_pipeline.py` valida automaticamente, **sem Ollama**:
- passagem consecutiva pelos cinco gates em um Git temporário real;
- um único retorno simulado de modelo, resposta persistida e patch válido;
- falha de âncora com resposta preservada e proibição de repetição;
- preflight inválido sem chamada ao modelo;
- rejeição do commit e do identificador do caso consumido;
- recuperação que ignora o arquivo-alvo sem chamada ao modelo.

O workflow LOCAL-16 executa a suíte no Ubuntu e Windows. Só o
operador Windows com Ollama poderá produzir evidência real da nova
tentativa; a CI não produz inferência nem testes funcionais de código
gerado.

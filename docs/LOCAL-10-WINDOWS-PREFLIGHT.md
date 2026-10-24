# LOCAL-10 — Preflight real do Windows sem inferência

## Motivação e limite
O LOCAL-09 já entrou na `main` com contrato de executor, edição segura e adaptador Ollama opt-in, CI offline aprovado. Não há acesso direto ao Ollama no Windows-alvo por meio da conexão GitHub. LOCAL-10 não confunde CI Linux com medição da GPU NVIDIA local.

## Implementação
- `experiments/local07/windows_preflight.py`: CLI somente leitura; acessa estritamente `127.0.0.1:11434`, `GET /api/version`, `GET /api/tags` e `GET /api/ps`; limita respostas a 1 MiB e falha fechado em erro HTTP/JSON/esquema. Nenhum `POST /api/generate`, `pull`, instalação ou execução de modelo. Produz JSON com presença dos candidatos Nemotron 3 Nano 4B, Qwen3.5 2B e Qwen3.5 4B, versão Ollama, modelos instalados e carregados.
- `test_windows_preflight.py`: transporte simulado, lista de endpoints auditável, controles negativos de host/endpoints, corpo muito grande, erros HTTP e saída incompatível.
- `.github/workflows/local10-preflight.yml`: verificação agrupada de LOCAL-07, LOCAL-09 e LOCAL-10, sem Ollama nem modelos.

## Evidência
GitHub Actions [#40048081415](https://github.com/oigorbrito/local/actions/runs/40048081415) **PASS**. Essa execução valida contrato em runner Ubuntu, não a máquina Windows nem inferência.

## Execução no computador-alvo (sem repetir benchmarks)
A partir do clone do repositório `oigorbrito/local` em Windows com Python 3.12 e Ollama ativo:

```powershell
python .\experiments\local07\windows_preflight.py --output .\local10-preflight.json
```

Saída: `local10-preflight.json`. Somente leitura; nenhuma geração de tokens. Para atestar hardware, anexar dados separados e verificáveis do `ollama ps`, sistema e GPU, sem concluir ocupação/pico de VRAM apenas pelos nomes instalados. Não publicar caminhos privados nem chaves.

## Gate e conclusão
- `OFFLINE_CONTRACT_PASS`: validação remota.
- `WINDOWS_RUNTIME_NOT_OBSERVED`: até leitura de `local10-preflight.json` realmente produzido no alvo.
- `REAL_GENERATION_NOT_RUN`: política vigente de não repetir modelos/benchmarks; deve permanecer separada da homologação de patches reais.
- Não alterar `main` nem efetuar merge automático antes de revisão seletiva.

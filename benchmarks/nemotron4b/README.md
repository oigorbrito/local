# Nemotron 3 Nano 4B — comparação funcional no Windows

Duas alternativas reais, mesma GPU do Windows e mesmo Ollama: executor
LOCAL-09 já integrado em main versus Cloi 2.1.0 fixado no commit
1da62db7aa3aed8b1e65f1e3fb69a89cf00707b9.

Requisitos: Windows 11, PowerShell, Docker Desktop com host networking
habilitado, Ollama ouvindo APENAS em 127.0.0.1:11434 e o modelo
nemotron-3-nano:4b quantizado Q4_K_M.

No PowerShell, na raiz do repositório:

    ollama pull nemotron-3-nano:4b
    ollama show nemotron-3-nano:4b
    .\benchmarks\nemotron4b\run.ps1 -Repeats 3

Se Docker não alcançar Ollama usando --network host, o comparador bloqueia.
Não amplie OLLAMA_HOST para 0.0.0.0 para contornar essa limitação.
Em Docker Desktop, host networking depende de configuração/habilitação.

Uma fixture Git limpa é recriada para cada tentativa dentro do contêiner.
Os testes de segurança do caminho exercitam traversal, caminhos absolutos
e symlink para fora da raiz; precisam falhar no original. Apenas mudanças
em guard.py são aceitas. Um teste independente, não alterado pelo agente,
deve passar após a edição. Modelo, digest, quantização e janela de 4096
tokens são iguais. Temperatura 0; Cloi sem modelo de fallback.

Os resultados ficam fora do Git, na pasta irmã local-nemotron-comparison:
report.json, result.patch, logs por tentativa e arquivos da execução
LOCAL-09. Não há commit nem merge automático.

LIMITAÇÕES: LOCAL-09 força num_predict=2048; Cloi 2.1.0 não fixa
num_predict em seu endpoint Ollama. As rodadas de ferramentas diferem.
A comparação permite avaliar correção e tempo, mas NÃO declarar vencedor
por eficiência de tokens sem normalizar esse parâmetro e repetir tarefas.

SEGURANÇA: Docker contém o executor Cloi com --yes, mas o host networking
não isola acesso a serviços de rede do Windows. Apenas a fixture e os módulos do LOCAL-07 são montados em read-only,
não o checkout inteiro; não se monta HOME nem socket Docker. Execute apenas em
ambiente sem serviços locais sensíveis acessíveis pelo contêiner.
Não trate isso como sandbox de rede hermética.

A fixture nova é uma reprodução de escape por symlink. Não afirmamos
que corresponde byte a byte à antiga tarefa congelada do LOCAL-19.

# LOCAL-14 — Triagem estática independente

Esta entrega extrai somente a triagem offline de patches da PR experimental #22. O módulo `experiments/local07/static_patch_gate.py` **não possui chamada a Docker, execução do candidato ou modo de executar testes**.

## Escopo autorizado
- Requer checkout Git limpo fixado em commit-base e arquivo Python na allowlist previamente recuperada, sem usar o patch gold.
- Rejeita symlink, traversal, modo/rename, operação binária, diff multifile ou cabeçalhos inconsistentes.
- Verifica aplicabilidade contra o índice Git num worktree descartável (`git apply --cached --check` via bytes).
- Produz `PATCH_APPLICABLE_NOT_GRADED` ou `PATCH_NOT_APPLICABLE` e preserva o repositório original.
- Não verifica correção funcional nem solução oficial SWE-bench.

## Uso
```powershell
python .\experiments\local07\static_patch_gate.py `
  --repo D:\checkouts\issue-pinned `
  --issue-json D:\cases\triage-spec.json `
  --patch D:\outputs\candidate.patch `
  --output D:\outputs\static-report.json
```

O `triage-spec.json` deve conter `schema=1`, `base_commit` SHA-40 e `allowed_files` com 1–2 arquivos elegíveis. A PR #22 mantém o runner de testes em contêiner como área experimental; **não é dependência desta entrega**.

Critério de promoção: CI com contratos estáticos e revisão do diff, sem alegar aprovação da sandbox para código hostil.

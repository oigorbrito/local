# Template de Repositório Orientado por Evidências

Este repositório é um **harness inicial**, não uma afirmação de maturidade ou conformidade.

Seu objetivo é fazer com que um novo repositório comece com:

- instruções de projeto versionadas e evidências de engenharia;
- um comando mínimo de verificação executável;
- estado do projeto legível por máquina;
- gatilhos explícitos de maturidade/release;
- relatórios com falha fechada (`PASS`, `GAP`, `UNKNOWN_EXTERNAL`, `NOT_APPLICABLE`);
- um caminho para controles mais fortes à medida que requisitos definidos externamente se tornem aplicáveis.

## Verificação canônica

```bash
python scripts/harness.py
python -m unittest discover -s tests -v
```

## Checklist de primeiro uso

1. Substitua o nome e a finalidade do projeto abaixo.
2. Selecione uma licença real e salve-a como `LICENSE` (consulte `LICENSE-SELECT.md`).
3. Atualize `policy/project-state.json` somente com fatos observáveis.
4. Implemente o projeto em `src/` e os testes em `tests/`.
5. Configure as Regras do Repositório do GitHub / proteção de branch fora do repositório.
6. Habilite o OpenSSF Scorecard usando `.github/workflows/scorecard.yml.example` depois de fixar cada action em um SHA de commit exato.

## Finalidade do projeto

**STATUS: UNDEFINED**

Descreva o projeto aqui antes que a implementação seja considerada estabelecida.

## Uso básico

**STATUS: NOT_RELEASED**

Antes do primeiro release oficial, substitua esta seção por instruções de instalação, configuração e uso básico.

## Relato de defeitos

Use GitHub Issues para defeitos não sensíveis. Vulnerabilidades de segurança devem seguir `SECURITY.md`.

## Semântica de maturidade

`product_stage` em `policy/project-state.json` é apenas informativo. Termos como `MVP` **não** são tratados como prova de um nível de maturidade OpenSSF.

O alvo normativo de maturidade de segurança é `osps_target_level`, e toda promoção deve ser sustentada por evidências observáveis. Consulte `docs/MATURITY.md`.

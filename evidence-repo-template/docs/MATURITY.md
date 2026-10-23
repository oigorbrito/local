# Modelo de maturidade e aplicabilidade

## Base normativa

O repositório usa o **OpenSSF OSPS Baseline v2026.08.28** como referência normativa de maturidade para este harness inicial.

O OSPS define:

- Level 1: qualquer projeto de código ou não código com qualquer número de mantenedores/usuários.
- Level 2: projeto de código com pelo menos dois mantenedores e um pequeno número de usuários consistentes.
- Level 3: projeto de código com um grande número de usuários consistentes.

O harness não inventa um limite numérico para “grande número de usuários”. Portanto, a promoção exige evidência humana explícita em `policy/project-state.json`.

## Estágio do produto não é normativo

`exploration`, `prototype`, `MVP`, `mature-MVP` e `production` podem ser rótulos úteis do produto, mas não são níveis de maturidade OSPS. Eles nunca satisfazem um controle OSPS por si mesmos.

## Gatilhos observáveis

O harness reconhece estes gatilhos observáveis:

1. **Primeiro release observado** — `release.made=true` no arquivo de estado ou pelo menos uma tag Git presente.
2. **Contagem de mantenedores alterada** — usada para solicitar reavaliação, não para promoção automática.
3. **Nível-alvo OSPS alterado** — ativa os controles correspondentes verificáveis localmente.
4. **Implementação do projeto presente** — os testes específicos do projeto não devem mais permanecer vazios.

## Regra de transição de estado

Uma transição nunca significa “todos os requisitos passam”. Significa que **novos requisitos podem se tornar aplicáveis**.

Exemplo:

```text
primeiro release observado
        ↓
controles condicionados ao release tornam-se aplicáveis
        ↓
harness verifica as evidências locais disponíveis
        ↓
PASS / GAP / UNKNOWN_EXTERNAL
```

## Verificações externas

Alguns requisitos não podem ser comprovados apenas pelos arquivos, incluindo MFA, aplicação das regras do repositório, proteção contra exclusão de branches, permissões de colaboradores e algumas configurações hospedadas de CI/segurança. O harness deve reportá-los como `UNKNOWN_EXTERNAL`, a menos que sejam consultados por uma API de plataforma autoritativa.

## Regra de reavaliação

Quando os fatos do projeto não se ajustarem mais à maturidade-alvo registrada, reporte `MATURITY_REASSESSMENT_REQUIRED`. Nunca promova ou rebaixe a maturidade silenciosamente.

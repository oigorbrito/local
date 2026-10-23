# Base externa

Este template separa intencionalmente **requisitos de origem** de **adaptadores do repositório**.

## OpenSSF OSPS Baseline

- Baseline atual usado por este template: v2026.08.28
- https://baseline.openssf.org/versions/2026-08-28
- https://baseline.openssf.org/

Usado para: níveis de maturidade; orientação de contribuição; localização da licença; transparência de dependências; testes automatizados; documentação condicionada ao release; controles de SBOM/SCA/SAST; e distinção entre níveis.

## OpenSSF Scorecard

- https://github.com/ossf/scorecard
- https://github.com/ossf/scorecard-action

Usado para: avaliação automatizada recorrente da saúde de segurança do repositório. O workflow fornecido é um exemplo e deve ser fixado/configurado antes de ser habilitado.

## NIST SSDF

- https://csrc.nist.gov/projects/ssdf

Usado para: práticas de desenvolvimento seguro de software organizadas em torno de preparação, proteção, produção de software bem protegido e resposta a vulnerabilidades. Este template não afirma conformidade com o NIST.

## DORA

- https://dora.dev/capabilities/version-control/
- https://dora.dev/capabilities/continuous-integration/
- https://dora.dev/capabilities/continuous-delivery/

Usado para: suporte empírico a controle de versão abrangente, feedback automatizado de build/teste, CI, testes contínuos e versionamento de artefatos de automação/configuração/IA.

## GitHub

- https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-template-repository
- https://docs.github.com/en/copilot/reference/custom-instructions-support

Usado para: mecanismos de repositórios-template e localizações reconhecidas para instruções do Copilot/agentes.

## Adaptadores específicos do repositório (não são requisitos externos)

Os seguintes são escolhas de implementação feitas exclusivamente para operacionalizar o material externo:

- `policy/project-state.json`
- `scripts/harness.py`
- rótulos de resultado `PASS`, `GAP`, `UNKNOWN_EXTERNAL`, `NOT_APPLICABLE`
- `MATURITY_REASSESSMENT_REQUIRED`
- uso de `AGENTS.md` para instruir agentes a executar o harness
- o perfil de agente personalizado `evidence-reviewer`

Esses adaptadores não devem ser citados como se OpenSSF, NIST, DORA ou GitHub determinassem seus nomes ou formatos exatos.

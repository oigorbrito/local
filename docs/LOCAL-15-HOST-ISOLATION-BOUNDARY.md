# LOCAL-15 — Isolamento de host: contrato de bloqueio

A sonda Docker do LOCAL-14 foi aprovada no Linux e no Docker Desktop do Windows. Isso **não certifica o host** para executar código adversarial.

`host_attestation.py` valida uma declaração explícita de host descartável, dedicado, sem credenciais e sem montagens pessoais, com destruição verificada, convidado Linux e imagem fixada por digest. Não coleta segredos, não tenta inferência nem executa contêineres. Mesmo com todas as afirmações positivas, o resultado é `ATTESTATION_COMPLETE_UNVERIFIED`, com `isolation_technically_verified=false` e `untrusted_execution_authorized=false`.

Isso evita um *falso PASS*: declarações do operador não provam isolamento de VM, ausência de credenciais ou destruição do host. A qualificação efetiva exige evidência independente da criação e destruição da VM, identidade/ambiente do guest, ausência de credenciais e confirmação de que os arquivos pessoais não ficam acessíveis. Essas evidências ainda não foram coletadas.

Para ensaios do SWE-bench, escolher VM/runner descartável, não o Windows pessoal. A etapa oficial deve registrar versões de harness, base commits, dependências, imagens por digest, logs públicos e limites de tempo. O projeto **ainda não validou execução de patches não confiáveis**.

CI: [#40101334783](https://github.com/oigorbrito/local/actions/runs/40101334783) confirma somente os contratos negativos de bloqueio, não o isolamento real.

## Evidência efetiva de host hospedado (24/10/2026)
Workflow [#40101493461](https://github.com/oigorbrito/local/actions/runs/40101493461) **PASS**, sem checkout, sem Docker, sem modelo e sem código candidato. A execução observou `runner.environment=github-hosted`, `runner.os=Linux`, UID 1001 e kernel `6.17.0-1022-azure`. O workflow define `permissions: {}` e não usa secrets de repositório.
Referência oficial: https://docs.github.com/en/actions/concepts/runners/github-hosted-runners — runners Ubuntu hospedados são VMs novas por job, exceto variantes de CPU única; não foi escolhida essa variante.
Limites declarados na própria medição: `credentials_absence_proven=false`, `vm_disposal_directly_observed=false`, `untrusted_execution_authorized=false`. A observação direta do runner confirma a configuração do job, **não** o encerramento posterior de sua VM nem a ausência absoluta de credenciais internas do executor GitHub. Não desbloqueia execução adversarial.

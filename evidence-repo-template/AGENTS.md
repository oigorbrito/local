# Instruções para Agentes

Estas instruções são um adaptador do repositório construído sobre controles definidos externamente. Elas **não são, por si mesmas, um requisito do OpenSSF, NIST ou DORA**.

Antes de alterar código ou documentação:

1. Leia `policy/project-state.json`, `docs/MATURITY.md`, `docs/ARCHITECTURE.md` e `docs/TESTING.md`.
2. Execute `python scripts/harness.py` antes de afirmar que o repositório está pronto.
3. Nunca converta evidência ausente, desatualizada, inacessível ou não executada em `PASS`.
4. Use exatamente estes significados para os resultados:
   - `PASS`: a evidência foi encontrada ou executada e satisfaz a verificação local.
   - `GAP`: um requisito local aplicável não é satisfeito.
   - `UNKNOWN_EXTERNAL`: o requisito depende de um estado do repositório/plataforma que este harness não consegue comprovar localmente.
   - `NOT_APPLICABLE`: o gatilho documentado não é atualmente verdadeiro.
5. Rótulos do produto como `prototype`, `MVP` ou `production` são apenas descritivos. Eles não promovem a maturidade OSPS.
6. Se um release for observado (arquivo de estado ou tag Git), execute as verificações condicionadas ao release e relate cada nova lacuna aplicável.
7. Se o número de mantenedores ou a população de usuários mudar materialmente, sinalize `MATURITY_REASSESSMENT_REQUIRED`; não promova silenciosamente o nível-alvo.
8. Não adicione uma afirmação de segurança, release, arquitetura ou conformidade sem que a evidência de suporte seja versionada ou verificável externamente.
9. Prefira a menor alteração que feche uma lacuna documentada. Não adicione controles apenas por aparência.
10. Após alterações materiais no projeto, execute novamente o harness e os testes.

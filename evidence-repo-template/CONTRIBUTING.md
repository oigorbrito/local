# Contribuição

## Processo de contribuição

1. Abra ou referencie uma issue quando a alteração não for trivial.
2. Trabalhe em uma branch em vez de fazer commit diretamente na branch primária.
3. Mantenha as alterações delimitadas e passíveis de revisão.
4. Adicione ou atualize testes quando o comportamento mudar.
5. Execute localmente a verificação canônica:

```bash
python scripts/harness.py
python -m unittest discover -s tests -v
```

6. Abra um pull request descrevendo a alteração e as evidências executadas.
7. Não informe uma verificação como aprovada a menos que ela tenha sido executada na alteração atual.

## Contribuições aceitáveis

As alterações devem preservar interfaces e invariantes documentados, evitar a introdução de binários gerados no controle de versão e manter alterações de dependências explícitas e passíveis de revisão.

## Política de testes

No bootstrap do repositório, os testes podem ser mínimos. À medida que o projeto amadurece, o nível-alvo OSPS aplicável determina se testes automatizados em CI, a execução de testes documentada e a política de atualização de testes se tornam obrigatórios. Consulte `docs/MATURITY.md`.

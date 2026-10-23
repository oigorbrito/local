# Testes

## Verificação local canônica

```bash
python scripts/harness.py
python -m unittest discover -s tests -v
```

## Escopo atual dos testes

O template testa apenas o próprio harness. Testes específicos do projeto devem ser adicionados à medida que a implementação surgir.

## Gatilho de maturidade

- OSPS Level 2: testes automatizados devem ser executados pelo CI antes que uma alteração seja aceita quando o controle aplicável assim exigir.
- OSPS Level 3: a documentação deve explicar quando/como os testes são executados, e alterações importantes devem adicionar ou atualizar testes de acordo com a política documentada.

O harness não afirma que um repositório está no Level 2/3 apenas porque este arquivo existe.

# Sistema de Gestão de Condicional de Roupas

Aplicativo desktop (Windows) para gestão de uma loja que vende roupas na condicional: cadastro de clientes, controle de estoque por produto, motor de precificação, controle de condicional (peça por peça, com prazos e status) e registro de vendas.

## Desenvolvimento assistido por Inteligência Artificial

Este projeto foi desenvolvido com apoio de ferramentas de Inteligência Artificial, como parte de um processo de aprendizado prático de engenharia de software. A geração de código foi feita por agentes de IA (Google Antigravity/Gemini), a partir de especificações técnicas detalhadas — regras de negócio, esquema de dados, contratos de função e critérios de teste — escritas e revisadas por mim.

Cada fase do desenvolvimento passou por uma dupla verificação antes de ser considerada concluída:

1. **Implementação**: a IA de desenvolvimento (Antigravity/Gemini) implementa a fase a partir de um prompt técnico detalhado.
2. **Revisão independente**: outra IA (Claude, Anthropic) revisa o código linha por linha e roda uma bateria de testes própria — não apenas os testes que a implementação gerou — incluindo casos de borda deliberadamente não cobertos pelos testes originais, para expor falhas escondidas antes de aprovar a fase.

Essa dinâmica já encontrou e corrigiu falhas reais antes de irem para produção (por exemplo: normalização de CPF que não detectava duplicatas com formatação diferente, e uma exclusão em cascata que não gerava registro de auditoria). Documentei isso aqui porque acredito que é mais honesto — e mais interessante tecnicamente — mostrar o processo real do que apresentar o resultado como se tivesse sido escrito manualmente do início ao fim.

## Funcionalidades e status atual

| Fase | Módulo | Status |
|---|---|---|
| 0 | Fundação e Segurança (banco criptografado, autenticação, backup, auditoria) | ✅ Concluída |
| 1 | Cliente e Produto (cadastro, endereços, fornecedores, estoque) | ✅ Concluída |
| 2 | Financeiro (motor de precificação, funcionários, contas a pagar) | ✅ Concluída |
| 3 | Condicional (controle de peças em condicional, prazos, devolução) | ✅ Concluída |
| 4 | Vendas (venda direta, histórico, comportamento de pagamento do cliente) | 🔄 Em desenvolvimento |
| 5 | Relatórios e Dashboard | ⏳ Planejada |

## Arquitetura e decisões técnicas

- **Banco de dados criptografado em repouso** — o arquivo `.db` nunca fica legível em disco; é decifrado para um arquivo temporário apenas durante a execução e recriptografado ao fechar, com o temporário apagado de forma segura (sobrescrito antes da exclusão).
- **Autenticação com Argon2** para a senha mestra, e derivação de chave via PBKDF2 para a criptografia do banco — dois algoritmos diferentes para dois propósitos diferentes (verificar senha vs. gerar chave).
- **Log de auditoria** — toda operação de escrita (criar, atualizar, excluir) em qualquer entidade fica registrada: quem, o quê, quando, e o valor anterior/novo de cada campo alterado.
- **Backup automático com política de retenção** — cópias do banco (já criptografado) são mantidas em pasta separada, com limite configurável de cópias mais recentes.
- **Produto controlado por SKU + quantidade** (modelo agrupado), não por peça única — duas peças idênticas são um registro com quantidade em estoque, não dois registros.
- **Margem de lucro calculada sobre o custo** da peça (`preco_venda = custo_total * (1 + margem)`), não sobre o preço de venda.
- **Valores derivados nunca são campos editáveis** — nível de compras e comportamento de pagamento do cliente, por exemplo, são calculados a partir do histórico de vendas, não digitados manualmente.
- **Estados que dependem de tempo são sempre calculados sob demanda**, nunca armazenados — vencimento de condicional e atraso de pagamento de venda são exemplos: um campo gravado ficaria desatualizado a cada virada de dia sem uma rotina para atualizá-lo.
- **Sem ORM** — acesso ao banco via SQL puro (`sqlite3` da biblioteca padrão), para manter controle explícito sobre a camada de criptografia e auditoria.

## Stack tecnológica

- **Python 3.12+**
- **SQLite** (via `sqlite3`, biblioteca padrão)
- **PySide6** — interface gráfica (ainda não implementada; o projeto até aqui é banco de dados + lógica de negócio)
- **cryptography** — criptografia do banco de dados em repouso (Fernet)
- **argon2-cffi** — hash de senha

## Estrutura do projeto

```
condicional_app/
├── database/
│   ├── connection.py      # EncryptedDatabase — acesso criptografado ao banco
│   ├── audit.py            # log de auditoria
│   └── schema.py           # definição de todas as tabelas, por fase
├── models/
│   ├── cliente.py
│   ├── endereco.py
│   ├── fornecedor.py
│   ├── produto.py
│   ├── financeiro.py       # configuração, funcionários, contas a pagar, motor de precificação
│   ├── condicional.py
│   └── venda.py            # em desenvolvimento
├── utils/
│   ├── security.py         # autenticação e derivação de chave
│   └── backup.py            # backup automático com retenção
├── ui/                      # interface (ainda não implementada)
├── backups/
├── test_fase0_backup_auditoria.py
├── test_fase1_cliente.py
├── test_fase1_produto.py
├── test_fase2_financeiro.py
├── test_fase3_condicional.py
├── requirements.txt
└── README.md
```

## Como rodar localmente

```bash
# Clonar o repositório
git clone <url-do-repositorio>
cd condicional_app

# Criar e ativar um ambiente virtual
python -m venv venv
venv\Scripts\activate      # Windows

# Instalar as dependências
pip install -r requirements.txt
```

## Testes

Cada fase tem seu próprio script de teste, standalone (sem framework de teste — usam `assert` e imprimem cada etapa verificada). Para rodar todos:

```bash
python test_fase0_backup_auditoria.py
python test_fase1_cliente.py
python test_fase1_produto.py
python test_fase2_financeiro.py
python test_fase3_condicional.py
```

## Metodologia de desenvolvimento

O projeto é construído fase por fase, na ordem: fundação e segurança primeiro (tudo mais depende disso), depois as entidades mais simples que servem de base (Cliente, Produto), e só então os módulos com regra de negócio mais complexa (Financeiro, Condicional). Cada fase só avança para a próxima depois de:

1. Especificada em detalhe (esquema de dados, regras de negócio, contratos de função)
2. Implementada
3. Testada com uma bateria própria
4. Revisada de forma independente, com testes adicionais que provam os comportamentos mais arriscados de cada módulo (limites exatos, casos de borda, tentativas de violar uma regra de negócio)

Nenhuma fase é considerada concluída com pendências conhecidas.

## Licença

Ainda não definida.

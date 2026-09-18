# Sistema de Condicional — Roadmap de Desenvolvimento

App desktop (Windows) para gestão de venda de roupas na condicional:
cadastro de clientes, produtos, controle financeiro e controle de condicional.

## Fases

- [x] **Fase 0 — Fundação e Segurança**
  - [x] Conexão de banco de dados criptografada em repouso (`database/connection.py`)
  - [x] Autenticação por senha mestra com Argon2 + derivação de chave (`utils/security.py`)
  - [x] Testes de hash/verificação de senha e criptografia do banco (`test_fase0.py`)
  - [x] Estrutura de backup automático com política de retenção (`utils/backup.py`)
  - [x] Log de auditoria (`database/audit.py`)
  - [x] Testes de backup e auditoria (`test_fase0_backup_auditoria.py`)

- [x] **Fase 1 — Cliente e Produto (schema base)**
  - [x] Esquema de dados: 4 tabelas — cliente, endereco, fornecedor, produto (`database/schema.py`)
  - [x] Model de Cliente com CRUD, validações e auditoria (`models/cliente.py`)
  - [x] Model de Endereço com CRUD, endereço principal e auditoria (`models/endereco.py`)
  - [x] Model de Fornecedor com CRUD simples e auditoria (`models/fornecedor.py`)
  - [x] Model de Produto com CRUD, ajuste de estoque seguro e auditoria (`models/produto.py`)
  - [x] Testes de cliente e endereço — 11 cenários (`test_fase1_cliente.py`)
  - [x] Testes de produto e fornecedor — 13 cenários (`test_fase1_produto.py`)
- [x] **Fase 2 — Financeiro (motor de cálculo)**
  - [x] Schema: tabelas de configuração, funcionário e contas a pagar (`database/schema.py`)
  - [x] Motor de precificação: rateio de custos fixos, cálculo de lucro sugerido (`models/financeiro.py`)
  - [x] Testes do fluxo financeiro e motor de cálculo (`test_fase2_financeiro.py`)
- [x] **Fase 3 — Condicional (orquestração)**
- [x] **Fase 4 — Vendas**
- [ ] **Fase 5 — Relatórios e Dashboard**
- [ ] **Fase 6 — Interface Gráfica**

## Decisões de arquitetura já fechadas

- Produtos controlados por **SKU + quantidade** (modelo agrupado), não peça única
- Margem de lucro calculada **sobre o custo** da peça
- Interface em **PySide6** (não PyQt — licença LGPL permite distribuição livre do .exe)
- Banco de dados: SQLite, criptografado em repouso com `cryptography` (Fernet)
  em vez de SQLCipher, para facilitar empacotamento com PyInstaller no Windows

## Estrutura de pastas

```
condicional_app/
├── database/     # acesso e schema do banco
├── models/       # entidades (Cliente, Produto, Condicional, ...)
├── ui/           # telas PySide6
├── utils/        # segurança, validação, helpers
├── backups/      # cópias de segurança geradas pelo próprio app
└── main.py       # ponto de entrada (ainda não criado)
```

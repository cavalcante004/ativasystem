"""
database/schema.py

Definição do esquema de dados do projeto: tabelas da Fase 1 (Cliente,
Endereço, Fornecedor, Produto) e da Fase 2 (Configuração Financeira,
Funcionário, Conta a Pagar).

POR QUE UM ARQUIVO SEPARADO PARA O SCHEMA:
As instruções CREATE TABLE ficam isoladas do código de acesso ao banco
(connection.py) e da lógica de negócio (models/). Isso permite:
  1. Ler o esquema inteiro num único lugar, sem procurar em vários arquivos.
  2. Adicionar tabelas em fases futuras sem mexer no código existente —
     basta criar novas constantes aqui e chamar na função garantir_tabelas.
  3. Manter o padrão já usado para a tabela de auditoria (CRIAR_TABELA_LOG
     em database/audit.py).

DECISÕES DE DESIGN REFLETIDAS NO SCHEMA:
  - Produto é SKU + quantidade (modelo agrupado), não peça única.
  - Cliente pode ter múltiplos endereços (tabela separada com FK).
  - CPF é opcional, mas UNIQUE quando informado — evita duplicata.
  - Endereço tem campo 'principal' (0 ou 1) para indicar qual usar
    por padrão quando o cliente tem mais de um.
  - valor_venda existe e é editável manualmente, mas agora o motor de
    precificação da Fase 2 pode calcular e aplicar um preço sugerido.
"""

import sqlite3

from database.audit import garantir_tabela_log


# ---------------------------------------------------------------------------
# Tabela de clientes
# ---------------------------------------------------------------------------
CRIAR_TABELA_CLIENTE = """
CREATE TABLE IF NOT EXISTS cliente (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    telefone TEXT NOT NULL,
    cpf TEXT UNIQUE,
    data_cadastro TEXT NOT NULL,
    observacoes TEXT
)
"""

# ---------------------------------------------------------------------------
# Tabela de endereços — relacionamento 1:N com cliente
# ---------------------------------------------------------------------------
CRIAR_TABELA_ENDERECO = """
CREATE TABLE IF NOT EXISTS endereco (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    logradouro TEXT NOT NULL,
    numero TEXT,
    bairro TEXT,
    cidade TEXT NOT NULL,
    referencia TEXT,
    principal INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (cliente_id) REFERENCES cliente (id) ON DELETE CASCADE
)
"""

# ---------------------------------------------------------------------------
# Tabela de fornecedores
# ---------------------------------------------------------------------------
CRIAR_TABELA_FORNECEDOR = """
CREATE TABLE IF NOT EXISTS fornecedor (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    contato TEXT
)
"""

# ---------------------------------------------------------------------------
# Tabela de produtos — modelo agrupado por SKU (codigo_etiqueta)
# ---------------------------------------------------------------------------
CRIAR_TABELA_PRODUTO = """
CREATE TABLE IF NOT EXISTS produto (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_etiqueta TEXT NOT NULL UNIQUE,
    descricao TEXT NOT NULL,
    marca TEXT,
    cor TEXT,
    tamanho TEXT,
    categoria TEXT,
    fornecedor_id INTEGER,
    valor_compra REAL NOT NULL CHECK (valor_compra >= 0),
    valor_venda REAL NOT NULL CHECK (valor_venda >= 0),
    quantidade_estoque INTEGER NOT NULL DEFAULT 0 CHECK (quantidade_estoque >= 0),
    data_compra TEXT,
    data_ultima_venda TEXT,
    FOREIGN KEY (fornecedor_id) REFERENCES fornecedor (id)
)
"""


def garantir_tabelas_fase1(conexao: sqlite3.Connection) -> None:
    """
    Cria todas as tabelas da Fase 1 (e a tabela de auditoria, que é
    pré-requisito para qualquer operação auditada).

    Deve ser chamada uma vez ao abrir o banco, logo após db.open().
    É idempotente — se as tabelas já existirem, não faz nada.

    conexao: conexão sqlite3 retornada por EncryptedDatabase.open().
    """
    # A tabela de auditoria precisa existir antes de qualquer INSERT/UPDATE
    # nas demais tabelas, porque os models chamam registrar_auditoria()
    # em toda operação de escrita.
    garantir_tabela_log(conexao)

    conexao.execute(CRIAR_TABELA_CLIENTE)
    conexao.execute(CRIAR_TABELA_ENDERECO)
    conexao.execute(CRIAR_TABELA_FORNECEDOR)
    conexao.execute(CRIAR_TABELA_PRODUTO)
    conexao.commit()


# ===========================================================================
# FASE 2 — Tabelas financeiras (motor de precificação)
# ===========================================================================

# ---------------------------------------------------------------------------
# Configuração financeira — linha única com parâmetros globais do motor
# ---------------------------------------------------------------------------
CRIAR_TABELA_CONFIGURACAO_FINANCEIRA = """
CREATE TABLE IF NOT EXISTS configuracao_financeira (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    margem_lucro_padrao REAL NOT NULL CHECK (margem_lucro_padrao >= 0),
    percentual_imposto_padrao REAL NOT NULL CHECK (percentual_imposto_padrao >= 0),
    quantidade_estimada_vendas_mes INTEGER NOT NULL CHECK (quantidade_estimada_vendas_mes > 0)
)
"""

# ---------------------------------------------------------------------------
# Funcionários — salário compõe o custo fixo mensal
# ---------------------------------------------------------------------------
CRIAR_TABELA_FUNCIONARIO = """
CREATE TABLE IF NOT EXISTS funcionario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    salario REAL NOT NULL CHECK (salario >= 0),
    ativo INTEGER NOT NULL DEFAULT 1
)
"""

# ---------------------------------------------------------------------------
# Contas a pagar — contas recorrentes compõem o custo fixo mensal
# ---------------------------------------------------------------------------
CRIAR_TABELA_CONTA_A_PAGAR = """
CREATE TABLE IF NOT EXISTS conta_a_pagar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    descricao TEXT NOT NULL,
    valor REAL NOT NULL CHECK (valor >= 0),
    vencimento TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'paga')),
    recorrente INTEGER NOT NULL DEFAULT 0
)
"""


def garantir_tabelas_fase2(conexao: sqlite3.Connection) -> None:
    """
    Cria as tabelas da Fase 2 (financeiro). Deve ser chamada logo após
    garantir_tabelas_fase1 na inicialização do banco.

    É idempotente — se as tabelas já existirem, não faz nada.

    conexao: conexão sqlite3 retornada por EncryptedDatabase.open().
    """
    conexao.execute(CRIAR_TABELA_CONFIGURACAO_FINANCEIRA)
    conexao.execute(CRIAR_TABELA_FUNCIONARIO)
    conexao.execute(CRIAR_TABELA_CONTA_A_PAGAR)
    conexao.commit()


# ===========================================================================
# FASE 3 — Condicional (orquestração)
# ===========================================================================

# ---------------------------------------------------------------------------
# Tabela de condicional (cabeçalho)
# ---------------------------------------------------------------------------
CRIAR_TABELA_CONDICIONAL = """
CREATE TABLE IF NOT EXISTS condicional (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    data_entrega TEXT NOT NULL,
    data_prazo TEXT NOT NULL,
    data_retirada TEXT,
    endereco_entrega TEXT NOT NULL,
    endereco_retirada TEXT,
    quem_entregou TEXT NOT NULL,
    quem_retirou TEXT,
    status TEXT NOT NULL DEFAULT 'ativa' CHECK (status IN ('ativa', 'finalizada')),
    observacoes TEXT,
    FOREIGN KEY (cliente_id) REFERENCES cliente (id)
)
"""

# ---------------------------------------------------------------------------
# Tabela de itens da condicional
# ---------------------------------------------------------------------------
CRIAR_TABELA_ITEM_CONDICIONAL = """
CREATE TABLE IF NOT EXISTS item_condicional (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    condicional_id INTEGER NOT NULL,
    produto_id INTEGER NOT NULL,
    quantidade_retirada INTEGER NOT NULL CHECK (quantidade_retirada > 0),
    quantidade_devolvida_boa INTEGER NOT NULL DEFAULT 0 CHECK (quantidade_devolvida_boa >= 0),
    quantidade_devolvida_com_problema INTEGER NOT NULL DEFAULT 0 CHECK (quantidade_devolvida_com_problema >= 0),
    quantidade_vendida INTEGER NOT NULL DEFAULT 0 CHECK (quantidade_vendida >= 0),
    FOREIGN KEY (condicional_id) REFERENCES condicional (id) ON DELETE CASCADE,
    FOREIGN KEY (produto_id) REFERENCES produto (id),
    CHECK (quantidade_devolvida_boa + quantidade_devolvida_com_problema + quantidade_vendida <= quantidade_retirada)
)
"""

def garantir_tabelas_fase3(conexao: sqlite3.Connection) -> None:
    """
    Cria as tabelas da Fase 3 (condicional e itens). Deve ser chamada logo após
    garantir_tabelas_fase2 na inicialização do banco.

    É idempotente — se as tabelas já existirem, não faz nada.

    conexao: conexão sqlite3 retornada por EncryptedDatabase.open().
    """
    conexao.execute(CRIAR_TABELA_CONDICIONAL)
    conexao.execute(CRIAR_TABELA_ITEM_CONDICIONAL)
    conexao.commit()


# ===========================================================================
# FASE 4 — Venda
# ===========================================================================

CRIAR_TABELA_VENDA = """
CREATE TABLE IF NOT EXISTS venda (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    data_venda TEXT NOT NULL,
    forma_pagamento TEXT NOT NULL CHECK (forma_pagamento IN ('dinheiro', 'pix', 'cartao_credito', 'cartao_debito', 'outro')),
    status_pagamento TEXT NOT NULL DEFAULT 'pago' CHECK (status_pagamento IN ('pago', 'pendente')),
    data_vencimento TEXT,
    data_pagamento_efetivo TEXT,
    observacoes TEXT,
    FOREIGN KEY(cliente_id) REFERENCES cliente(id)
)
"""

CRIAR_TABELA_ITEM_VENDA = """
CREATE TABLE IF NOT EXISTS item_venda (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venda_id INTEGER NOT NULL,
    produto_id INTEGER NOT NULL,
    quantidade INTEGER NOT NULL CHECK (quantidade > 0),
    preco_unitario_praticado REAL NOT NULL CHECK (preco_unitario_praticado >= 0),
    FOREIGN KEY(venda_id) REFERENCES venda(id) ON DELETE CASCADE,
    FOREIGN KEY(produto_id) REFERENCES produto(id)
)
"""

def garantir_tabelas_fase4(conexao: sqlite3.Connection) -> None:
    conexao.execute(CRIAR_TABELA_VENDA)
    conexao.execute(CRIAR_TABELA_ITEM_VENDA)
    conexao.commit()


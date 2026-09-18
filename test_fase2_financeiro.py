"""
test_fase2_financeiro.py

Testes da Fase 2 para o Motor Financeiro: configuração financeira, funcionários,
contas a pagar, e o motor de cálculo de precificação de produtos.

Seguindo o padrão dos demais testes: script standalone, banco limpo, asserts.
"""

import os
import shutil
import sys
import json

sys.path.insert(0, os.path.dirname(__file__))

from utils.security import derive_encryption_key
from database.connection import EncryptedDatabase
from database.schema import garantir_tabelas_fase1, garantir_tabelas_fase2
from database.audit import consultar_auditoria

from models.fornecedor import criar_fornecedor
from models.produto import criar_produto, buscar_produto_por_codigo

from models.financeiro import (
    garantir_configuracao_financeira,
    obter_configuracao,
    atualizar_configuracao,
    criar_funcionario,
    listar_funcionarios,
    atualizar_funcionario,
    desligar_funcionario,
    reativar_funcionario,
    criar_conta_a_pagar,
    listar_contas_a_pagar,
    marcar_conta_como_paga,
    atualizar_conta_a_pagar,
    excluir_conta_a_pagar,
    calcular_custo_fixo_mensal,
    calcular_rateio_por_peca,
    calcular_preco_sugerido,
    aplicar_preco_sugerido,
)

def linha(titulo: str) -> None:
    print(f"\n{'=' * 60}\n{titulo}\n{'=' * 60}")

PASTA_TESTE = "backups/teste_temp_fase2"
CAMINHO_BANCO = f"{PASTA_TESTE}/loja_teste_fase2.db.enc"

if os.path.exists(PASTA_TESTE):
    shutil.rmtree(PASTA_TESTE)
os.makedirs(PASTA_TESTE)

senha = "senhaDeTesteFase2!"
chave = derive_encryption_key(senha)
usuario = "TesteFase2"

db = EncryptedDatabase(CAMINHO_BANCO, chave)
conexao = db.open()
garantir_tabelas_fase1(conexao)
garantir_tabelas_fase2(conexao)

# ---------------------------------------------------------------------------
# TESTE 1 — Configuração Financeira
# ---------------------------------------------------------------------------
linha("TESTE 1: Configuração Financeira")

garantir_configuracao_financeira(conexao, margem_lucro_padrao=0.50, percentual_imposto_padrao=0.10, quantidade_estimada_vendas_mes=100)
config = obter_configuracao(conexao)
print(f"Configuração inicial: {config}")
assert config[1] == 0.50
assert config[2] == 0.10
assert config[3] == 100

atualizar_configuracao(conexao, usuario, margem_lucro_padrao=0.40)
config_nova = obter_configuracao(conexao)
print(f"Configuração alterada: {config_nova}")
assert config_nova[1] == 0.40
assert config_nova[2] == 0.10  # Mantido
assert config_nova[3] == 100   # Mantido

# Validação: Quantidade <= 0
try:
    atualizar_configuracao(conexao, usuario, quantidade_estimada_vendas_mes=0)
    assert False, "Não deveria aceitar estimativa de vendas zero"
except ValueError as e:
    print(f"Erro esperado capturado: {e}")

print("\n[OK] Configuração financeira testada com sucesso")


# ---------------------------------------------------------------------------
# TESTE 2 — Funcionários
# ---------------------------------------------------------------------------
linha("TESTE 2: Funcionários (CRUD e Situação)")

f1 = criar_funcionario(conexao, nome="Ana Vendedora", salario=2500.00, usuario=usuario)
f2 = criar_funcionario(conexao, nome="Carlos Gerente", salario=4000.00, usuario=usuario)

funcionarios = listar_funcionarios(conexao)
assert len(funcionarios) == 2

atualizar_funcionario(conexao, f1, usuario, salario=2600.00)

desligar_funcionario(conexao, f2, usuario)
funcionarios_ativos = listar_funcionarios(conexao, somente_ativos=True)
assert len(funcionarios_ativos) == 1
assert funcionarios_ativos[0][1] == "Ana Vendedora"

reativar_funcionario(conexao, f2, usuario)
assert len(listar_funcionarios(conexao, somente_ativos=True)) == 2

desligar_funcionario(conexao, f2, usuario) # Desliga f2 novamente para os cálculos de rateio

print("\n[OK] Funcionários geridos com sucesso")


# ---------------------------------------------------------------------------
# TESTE 3 — Contas a Pagar
# ---------------------------------------------------------------------------
linha("TESTE 3: Contas a Pagar")

c1 = criar_conta_a_pagar(conexao, descricao="Luz", valor=300.00, vencimento="2026-10-10", usuario=usuario, recorrente=True)
c2 = criar_conta_a_pagar(conexao, descricao="Internet", valor=150.00, vencimento="2026-10-15", usuario=usuario, recorrente=True)
c3 = criar_conta_a_pagar(conexao, descricao="Manutenção Ar", valor=200.00, vencimento="2026-10-20", usuario=usuario, recorrente=False)

contas = listar_contas_a_pagar(conexao)
assert len(contas) == 3

marcar_conta_como_paga(conexao, c1, usuario)
contas_pendentes = listar_contas_a_pagar(conexao, apenas_pendentes=True)
assert len(contas_pendentes) == 2

atualizar_conta_a_pagar(conexao, c2, usuario, valor=160.00)

excluir_conta_a_pagar(conexao, c3, usuario)
assert len(listar_contas_a_pagar(conexao)) == 2

print("\n[OK] Contas a pagar testadas com sucesso")


# ---------------------------------------------------------------------------
# TESTE 4 — Motor de Cálculo e Rateio
# ---------------------------------------------------------------------------
linha("TESTE 4: Motor de Cálculo e Rateio")

# Salários Ativos: Ana (2600.00)
# Contas Recorrentes: Luz (300.00, mesmo paga), Internet (160.00)
# Custo Fixo Total = 2600 + 300 + 160 = 3060.00

custo_fixo = calcular_custo_fixo_mensal(conexao)
print(f"Custo fixo calculado: {custo_fixo}")
assert custo_fixo == 3060.00

# Vendas estimadas: 100
# Rateio = 3060 / 100 = 30.60
rateio = calcular_rateio_por_peca(conexao)
print(f"Rateio por peça calculado: {rateio}")
assert rateio == 30.60

print("\n[OK] Motor de rateio funcionando corretamente")


# ---------------------------------------------------------------------------
# TESTE 5 — Cálculo e Aplicação de Preço Sugerido
# ---------------------------------------------------------------------------
linha("TESTE 5: Cálculo e Aplicação de Preço em Produto")

# Cria produto para teste
forn_id = criar_fornecedor(conexao, nome="Fornecedor XYZ", usuario=usuario)
prod_id = criar_produto(
    conexao, codigo_etiqueta="TST-123", descricao="Produto Teste",
    valor_compra=50.00, valor_venda=0.00, usuario=usuario,
    fornecedor_id=forn_id
)

sugerido = calcular_preco_sugerido(conexao, prod_id)
print(f"Cálculo Sugerido Detalhado: {sugerido}")

# valor_compra = 50.00
# imposto_estimado (10%) = 5.00
# rateio = 30.60
# custo_total = 50 + 5 + 30.60 = 85.60
# preco_sugerido (com 40% margem) = 85.60 * 1.40 = 119.84

assert sugerido["custo_total"] == 85.60
assert round(sugerido["preco_sugerido"], 2) == 119.84

novo_preco = aplicar_preco_sugerido(conexao, prod_id, usuario)
produto_atualizado = buscar_produto_por_codigo(conexao, "TST-123")

print(f"Preço salvo no banco: {produto_atualizado[9]}")
assert produto_atualizado[9] == 119.84

print("\n[OK] Precificação sugerida aplicada no produto com sucesso")


# ---------------------------------------------------------------------------
# TESTE 6 — Verificação de Auditoria
# ---------------------------------------------------------------------------
linha("TESTE 6: Verificação de Auditoria do Financeiro")

auditorias_config = consultar_auditoria(conexao, tabela="configuracao_financeira")
auditorias_func = consultar_auditoria(conexao, tabela="funcionario")
auditorias_conta = consultar_auditoria(conexao, tabela="conta_a_pagar")

print(f"Eventos de config: {len(auditorias_config)}")
print(f"Eventos de func: {len(auditorias_func)}")
print(f"Eventos de conta: {len(auditorias_conta)}")

assert len(auditorias_config) == 1 # UPDATE da margem_lucro_padrao
# Func: 2 INSERTs + 1 UPDATE + 2 DESLIGAR + 1 REATIVAR = 6
assert len(auditorias_func) == 6
# Conta: 3 INSERTs + 1 MARCAR PAGA + 1 UPDATE + 1 DELETE = 6
assert len(auditorias_conta) == 6

print("\n[OK] Auditoria dos eventos financeiros registrando corretamente")

# ---------------------------------------------------------------------------
# Limpeza
# ---------------------------------------------------------------------------
db.close()
shutil.rmtree(PASTA_TESTE)

linha("TODOS OS TESTES DA FASE 2 PASSARAM")

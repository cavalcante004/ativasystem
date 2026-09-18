"""
test_fase4_venda.py

Testes da Fase 4: Vendas Diretas.
"""

import os
import shutil
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from utils.security import derive_encryption_key
from database.connection import EncryptedDatabase
from database.schema import (
    garantir_tabelas_fase1, 
    garantir_tabelas_fase2, 
    garantir_tabelas_fase3,
    garantir_tabelas_fase4
)
from database.audit import consultar_auditoria

from models.cliente import criar_cliente
from models.produto import criar_produto, buscar_produto_por_id
from models.venda import (
    criar_venda,
    buscar_venda_por_id,
    marcar_venda_como_paga,
    esta_atrasada,
    calcular_total_comprado_cliente,
    calcular_comportamento_pagamento_cliente,
    calcular_media_vendas_mensais_reais
)

def linha(titulo: str) -> None:
    print(f"\n{'=' * 60}\n{titulo}\n{'=' * 60}")

PASTA_TESTE = "backups/teste_temp_fase4_c"
CAMINHO_BANCO = f"{PASTA_TESTE}/loja_teste_fase4.db.enc"

if os.path.exists(PASTA_TESTE):
    shutil.rmtree(PASTA_TESTE)
os.makedirs(PASTA_TESTE)

senha = "senhaDeTesteFase4!"
chave = derive_encryption_key(senha)
usuario = "TesteFase4"

db = EncryptedDatabase(CAMINHO_BANCO, chave)
conexao = db.open()

garantir_tabelas_fase1(conexao)
garantir_tabelas_fase2(conexao)
garantir_tabelas_fase3(conexao)
garantir_tabelas_fase4(conexao)

linha("PREPARAÇÃO: Criar Cliente e Produtos")

cliente_id = criar_cliente(conexao, nome="Cliente Venda", telefone="1199999999", usuario=usuario)
produto1_id = criar_produto(conexao, codigo_etiqueta="PRD-V1", descricao="Prod V1", valor_compra=10, valor_venda=20, quantidade_estoque=10, usuario=usuario)
produto2_id = criar_produto(conexao, codigo_etiqueta="PRD-V2", descricao="Prod V2", valor_compra=15, valor_venda=30, quantidade_estoque=5, usuario=usuario)

hoje = datetime.now()


linha("TESTE 1: Criar venda com múltiplos itens (decremento e data última venda)")

data_antes = hoje.isoformat()[:10]
itens_venda_1 = [
    {"produto_id": produto1_id, "quantidade": 2, "preco_unitario": 20.0},
    {"produto_id": produto2_id, "quantidade": 1, "preco_unitario": 25.0}  # desconto
]

venda1_id = criar_venda(
    conexao, cliente_id, forma_pagamento='dinheiro', itens=itens_venda_1, 
    usuario=usuario, data_venda=data_antes
)

# Verifica estoque (PRD1 = 10-2=8, PRD2 = 5-1=4) e data_ultima_venda
p1 = buscar_produto_por_id(conexao, produto1_id)
p2 = buscar_produto_por_id(conexao, produto2_id)

assert p1[10] == 8, f"Estoque P1 esperado 8, tem {p1[10]}"
assert p2[10] == 4, f"Estoque P2 esperado 4, tem {p2[10]}"
assert p1[12] == data_antes, "Data ultima venda P1 não atualizada"
assert p2[12] == data_antes, "Data ultima venda P2 não atualizada"

print("[OK] Venda criada, estoque e última venda atualizados")


linha("TESTE 2: Duas passadas - Falha no segundo item não altera o primeiro")

itens_venda_falha = [
    {"produto_id": produto1_id, "quantidade": 1, "preco_unitario": 20.0},
    {"produto_id": produto2_id, "quantidade": 10, "preco_unitario": 25.0}  # não tem 10 no estoque
]

try:
    criar_venda(conexao, cliente_id, forma_pagamento='pix', itens=itens_venda_falha, usuario=usuario)
    assert False, "A venda deveria falhar por estoque insuficiente no item 2"
except ValueError as e:
    print(f"Erro esperado: {e}")

# Estoque P1 não deve ter sido alterado da primeira validação
p1_apos = buscar_produto_por_id(conexao, produto1_id)
assert p1_apos[10] == 8, f"O estoque do P1 vazou! Esperado 8, tem {p1_apos[10]}"

print("[OK] Validação em duas passadas blindou o banco contra alterações parciais")


linha("TESTE 3: Criar venda pendente sem vencimento")

try:
    criar_venda(
        conexao, cliente_id, forma_pagamento='outro', 
        itens=[{"produto_id": produto1_id, "quantidade": 1, "preco_unitario": 20.0}],
        usuario=usuario, status_pagamento='pendente'
    )
    assert False, "A venda deveria falhar por não informar vencimento"
except ValueError as e:
    print(f"Erro esperado: {e}")

print("[OK] Venda pendente sem vencimento bloqueada")


linha("TESTE 4: Venda pendente com vencimento no passado, atraso e pagamento")

data_vencimento_passado = (hoje - timedelta(days=5)).isoformat()[:10]

venda_atrasada_id = criar_venda(
    conexao, cliente_id, forma_pagamento='cartao_credito', 
    itens=[{"produto_id": produto1_id, "quantidade": 1, "preco_unitario": 20.0}],
    usuario=usuario, status_pagamento='pendente', data_vencimento=data_vencimento_passado
)

assert esta_atrasada(conexao, venda_atrasada_id) is True, "Venda não foi detectada como atrasada"

marcar_venda_como_paga(conexao, venda_atrasada_id, usuario)

assert esta_atrasada(conexao, venda_atrasada_id) is False, "Venda ainda aparece como atrasada após paga"

v_atrasada_banco = buscar_venda_por_id(conexao, venda_atrasada_id)
assert v_atrasada_banco[4] == 'pago', "Status não virou 'pago'"
assert v_atrasada_banco[6] is not None, "Data efetiva de pagamento vazia"

print("[OK] Venda atrasada identificada corretamente e paga")


linha("TESTE 5 e 6: Métricas do cliente (Comportamento e Total Comprado)")

# Criar mais uma venda pendente, em aberto (para testar o comportamento)
data_vencimento_futuro = (hoje + timedelta(days=5)).isoformat()[:10]
venda_pendente_id = criar_venda(
    conexao, cliente_id, forma_pagamento='dinheiro', 
    itens=[{"produto_id": produto2_id, "quantidade": 1, "preco_unitario": 30.0}],
    usuario=usuario, status_pagamento='pendente', data_vencimento=data_vencimento_futuro
)

# Resumo do cliente até agora:
# Venda 1: Paga em dia (à vista) - Itens: (2*20) + (1*25) = 65
# Venda 2: Atrasada, mas paga depois - Item: (1*20) = 20
# Venda 3: Pendente em aberto - Item: (1*30) = 30
# Total Comprado: 65 + 20 + 30 = 115

total = calcular_total_comprado_cliente(conexao, cliente_id)
assert total == 115.0, f"Total esperado 115, tem {total}"
print(f"[OK] Total comprado calculado corretamente: {total}")

comportamento = calcular_comportamento_pagamento_cliente(conexao, cliente_id)
assert comportamento["pagas_em_dia"] == 1, f"Pagas em dia esperado 1, tem {comportamento['pagas_em_dia']}"
assert comportamento["pagas_atrasadas"] == 1, f"Pagas atrasadas esperado 1, tem {comportamento['pagas_atrasadas']}"
assert comportamento["pendentes_em_aberto"] == 1, f"Pendentes esperado 1, tem {comportamento['pendentes_em_aberto']}"
print("[OK] Comportamento de pagamento segmentado corretamente")


linha("TESTE 7: Calcular média de vendas mensais (Base histórica)")

# Venda 1 tem 3 itens de Qtd (2+1)
# Venda 2 (atrasada) tem 1 item de Qtd (1)
# Venda 3 (pendente) tem 1 item de Qtd (1)
# Total de peças = 5.
# Média em 3 meses: 5 / 3 = 1.666...
media = calcular_media_vendas_mensais_reais(conexao, meses=3)
assert abs(media - (5/3)) < 0.001, f"Média esperada {5/3}, tem {media}"

# E se buscar em apenas 1 mes e houver uma venda a mais de 30 dias?
data_antiga = (hoje - timedelta(days=45)).isoformat()
criar_venda(
    conexao, cliente_id, forma_pagamento='dinheiro', 
    itens=[{"produto_id": produto2_id, "quantidade": 1, "preco_unitario": 30.0}],
    usuario=usuario, data_venda=data_antiga
)
media_1_mes = calcular_media_vendas_mensais_reais(conexao, meses=1)
# As peças são 5 nos últimos 30 dias. 5 / 1 = 5. A venda antiga não entra.
assert media_1_mes == 5.0, f"Média 1 mês esperada 5, tem {media_1_mes}"

print(f"[OK] Média de vendas mensais calculada corretamente (3 meses={media:.2f}, 1 mês={media_1_mes:.2f})")


linha("TESTE 8: Confirmar Auditoria de Vendas e Itens")

auditoria_venda = consultar_auditoria(conexao, tabela="venda")
auditoria_item_venda = consultar_auditoria(conexao, tabela="item_venda")

# Criadas 4 vendas + 1 update (marcar_venda_como_paga)
assert len(auditoria_venda) == 5, f"Esperado 5 auditorias de venda, tem {len(auditoria_venda)}"

# Itens: 2 (Venda 1) + 1 (Venda 2) + 1 (Venda 3) + 1 (Venda 4 Antiga)
assert len(auditoria_item_venda) == 5, f"Esperado 5 auditorias de item_venda, tem {len(auditoria_item_venda)}"

print("[OK] Auditoria completa para vendas e itens_venda")


db.close()
shutil.rmtree(PASTA_TESTE)

linha("TODOS OS TESTES DA FASE 4 PASSARAM")

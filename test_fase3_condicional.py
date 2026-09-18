"""
test_fase3_condicional.py

Testes da Fase 3: Orquestração de Condicional.
"""

import os
import shutil
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from utils.security import derive_encryption_key
from database.connection import EncryptedDatabase
from database.schema import garantir_tabelas_fase1, garantir_tabelas_fase2, garantir_tabelas_fase3
from database.audit import consultar_auditoria

from models.cliente import criar_cliente
from models.produto import criar_produto, buscar_produto_por_id
from models.condicional import (
    criar_condicional,
    adicionar_item_condicional,
    listar_itens_condicional,
    resolver_item,
    finalizar_condicional,
    buscar_condicional_por_id,
    esta_vencida,
    listar_condicionais_vencidas,
)

def linha(titulo: str) -> None:
    print(f"\n{'=' * 60}\n{titulo}\n{'=' * 60}")

PASTA_TESTE = "backups/teste_temp_fase3_b"
CAMINHO_BANCO = f"{PASTA_TESTE}/loja_teste_fase3.db.enc"

if os.path.exists(PASTA_TESTE):
    shutil.rmtree(PASTA_TESTE)
os.makedirs(PASTA_TESTE)

senha = "senhaDeTesteFase3!"
chave = derive_encryption_key(senha)
usuario = "TesteFase3"

db = EncryptedDatabase(CAMINHO_BANCO, chave)
conexao = db.open()

garantir_tabelas_fase1(conexao)
garantir_tabelas_fase2(conexao)
garantir_tabelas_fase3(conexao)

linha("PREPARAÇÃO: Criar Cliente e Produtos")

cliente_id = criar_cliente(conexao, nome="Cliente Teste", telefone="1199999999", usuario=usuario)
produto1_id = criar_produto(conexao, codigo_etiqueta="PRD-1", descricao="Produto 1", valor_compra=10, valor_venda=20, quantidade_estoque=10, usuario=usuario)
produto2_id = criar_produto(conexao, codigo_etiqueta="PRD-2", descricao="Produto 2", valor_compra=15, valor_venda=30, quantidade_estoque=5, usuario=usuario)
produto3_id = criar_produto(conexao, codigo_etiqueta="PRD-3", descricao="Produto 3", valor_compra=15, valor_venda=30, quantidade_estoque=2, usuario=usuario)

hoje = datetime.now()
data_entrega = hoje.isoformat()[:10]
data_prazo_futuro = (hoje + timedelta(days=5)).isoformat()[:10]
data_prazo_passado = (hoje - timedelta(days=5)).isoformat()[:10]


linha("TESTE 1: Criar condicional e confirmar decremento de estoque")

cond_id = criar_condicional(
    conexao, cliente_id, data_entrega, data_prazo_futuro, 
    endereco_entrega="Rua A, 123", quem_entregou="Vendedor 1", usuario=usuario
)

item1_id = adicionar_item_condicional(conexao, cond_id, produto1_id, 3, usuario)
item2_id = adicionar_item_condicional(conexao, cond_id, produto2_id, 2, usuario)

# O estoque inicial era: P1=10, P2=5. Foi retirado P1=3, P2=2.
# Deve ficar P1=7, P2=3.
p1 = buscar_produto_por_id(conexao, produto1_id)
p2 = buscar_produto_por_id(conexao, produto2_id)
assert p1[10] == 7, f"Esperado 7, tem {p1[10]}"
assert p2[10] == 3, f"Esperado 3, tem {p2[10]}"

print("[OK] Condicional criada e estoque decrementado fisicamente")


linha("TESTE 2: Tentar adicionar quantidade maior que o estoque")

try:
    adicionar_item_condicional(conexao, cond_id, produto2_id, 10, usuario)
    assert False, "Deveria falhar por estoque insuficiente"
except ValueError as e:
    print(f"Erro esperado: {e}")

# Estoque P2 deve continuar 3
p2_apos = buscar_produto_por_id(conexao, produto2_id)
assert p2_apos[10] == 3, "O estoque foi alterado erroneamente"

print("[OK] Falha correta sem alterar estoque")


linha("TESTE 3: Resolver item parcialmente (boa vs problema)")

# Item 1 (P1) retirou 3. Vamos devolver 1 boa e 1 problema (total 2 resolvidas, 1 pendente).
resolver_item(conexao, item1_id, usuario, quantidade_devolvida_boa=1, quantidade_devolvida_com_problema=1, quantidade_vendida=0)

# O estoque P1 era 7. Retornou 1 peça BOA. Deve ir para 8.
# A peça com problema NÃO retorna ao estoque.
p1_apos = buscar_produto_por_id(conexao, produto1_id)
assert p1_apos[10] == 8, f"Esperado 8, tem {p1_apos[10]}"

print("[OK] Resolução parcial funcionou, só peças boas voltaram ao estoque")


linha("TESTE 4: Tentar finalizar condicional com pendências")

try:
    finalizar_condicional(conexao, cond_id, "Vendedor 1", usuario)
    assert False, "Deveria falhar, pois os itens não estão 100% resolvidos"
except ValueError as e:
    print(f"Erro esperado: {e}")

cond = buscar_condicional_por_id(conexao, cond_id)
assert cond[9] == 'ativa', "A condicional não pode ter finalizado"

print("[OK] Bloqueio correto ao tentar finalizar com itens pendentes")


linha("TESTE 5: Resolver o resto e finalizar")

# Falta 1 no item 1, e 2 no item 2.
resolver_item(conexao, item1_id, usuario, quantidade_vendida=1)
resolver_item(conexao, item2_id, usuario, quantidade_devolvida_boa=1, quantidade_vendida=1)

finalizar_condicional(conexao, cond_id, "Vendedor 1", usuario)

cond_final = buscar_condicional_por_id(conexao, cond_id)
assert cond_final[9] == 'finalizada', "A condicional deveria estar finalizada"
assert cond_final[4] is not None, "A data de retirada deveria estar preenchida"

# P1 = 8 - vendeu 1 = continua 8 (estoque não volta)
# P2 = 3 - devolveu boa 1, vendeu 1 = devolveu 1. Vai para 4.
p1_fim = buscar_produto_por_id(conexao, produto1_id)
p2_fim = buscar_produto_por_id(conexao, produto2_id)
assert p1_fim[10] == 8, f"P1 falhou. Esperado 8, tem {p1_fim[10]}"
assert p2_fim[10] == 4, f"P2 falhou. Esperado 4, tem {p2_fim[10]}"

print("[OK] Itens totalmente resolvidos e condicional finalizada com sucesso")


linha("TESTE 6: Verificação de Vencimento")

data_entrega_passado = (hoje - timedelta(days=10)).isoformat()[:10]
cond_venc_id = criar_condicional(conexao, cliente_id, data_entrega_passado, data_prazo_passado, "End B", "V1", usuario)
cond_fut_id = criar_condicional(conexao, cliente_id, data_entrega, data_prazo_futuro, "End C", "V1", usuario)

assert esta_vencida(conexao, cond_venc_id) is True, "Deveria estar vencida"
assert esta_vencida(conexao, cond_fut_id) is False, "Não deveria estar vencida"

vencidas = listar_condicionais_vencidas(conexao)
ids_vencidas = [c[0] for c in vencidas]
assert cond_venc_id in ids_vencidas
assert cond_fut_id not in ids_vencidas
assert cond_id not in ids_vencidas # cond_id está finalizada, nem pode aparecer

print("[OK] Cálculo de vencimento funcionando perfeitamente sob demanda")


linha("TESTE 7: Tentar resolver quantidade acima da retirada")

item_venc = adicionar_item_condicional(conexao, cond_venc_id, produto3_id, 2, usuario)

try:
    resolver_item(conexao, item_venc, usuario, quantidade_devolvida_boa=3)
    assert False, "Deveria falhar ao resolver mais do que foi retirado"
except ValueError as e:
    print(f"Erro esperado: {e}")

try:
    resolver_item(conexao, item_venc, usuario, quantidade_devolvida_boa=1)
    resolver_item(conexao, item_venc, usuario, quantidade_vendida=2)
    assert False, "Deveria falhar ao somar as resoluções graduais além do total"
except ValueError as e:
    print(f"Erro esperado na soma cumulativa: {e}")

print("[OK] Limite de resolução do item respeitado")


linha("TESTE 8: Confirmar Auditoria")

auditoria_cond = consultar_auditoria(conexao, tabela="condicional")
auditoria_item = consultar_auditoria(conexao, tabela="item_condicional")

# Condicionais criadas: 3, Finalizadas: 1
assert len(auditoria_cond) == 4, f"Esperadas 4 auditorias de condicional, tem {len(auditoria_cond)}"

# Itens criados: 3 (2 na primeira, 1 na segunda). Resoluções: 3 na primeira, 1 ou 2 tentativas na vencida.
# Tentativas falhas não geram auditoria. Resoluções bem sucedidas:
# item1: +1 boa/ +1 prob
# item1: +1 venda
# item2: +1 boa/ +1 venda
# item_venc: +1 boa
# Total de inserts = 3. Total de updates = 4. 
assert len(auditoria_item) == 7, f"Esperadas 7 auditorias de item_condicional, tem {len(auditoria_item)}"

print("[OK] Auditorias geradas com sucesso para as novas tabelas")


db.close()
shutil.rmtree(PASTA_TESTE)

linha("TODOS OS TESTES DA FASE 3 PASSARAM")

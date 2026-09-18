"""
test_fase1_produto.py

Testes da Fase 1 para Produto e Fornecedor: criação, código duplicado,
ajuste de estoque (positivo, negativo, e tentativa de estoque negativo),
atualização, exclusão, e log de auditoria.

Segue o mesmo padrão de test_fase0_backup_auditoria.py: script standalone,
prints explicativos em cada etapa, assert para validar, banco criptografado
de teste limpo ao final.

Rode com: python test_fase1_produto.py
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(__file__))

from utils.security import derive_encryption_key
from database.connection import EncryptedDatabase
from database.schema import garantir_tabelas_fase1
from database.audit import consultar_auditoria
from models.fornecedor import (
    criar_fornecedor,
    buscar_fornecedor_por_id,
    listar_fornecedores,
    atualizar_fornecedor,
    excluir_fornecedor,
)
from models.produto import (
    criar_produto,
    buscar_produto_por_codigo,
    listar_produtos,
    atualizar_produto,
    excluir_produto,
    ajustar_estoque,
)


def linha(titulo: str) -> None:
    print(f"\n{'=' * 60}\n{titulo}\n{'=' * 60}")


PASTA_TESTE = "backups/teste_temp"
CAMINHO_BANCO = f"{PASTA_TESTE}/loja_teste_fase1_produto.db.enc"

# Limpeza de execuções anteriores
if os.path.exists(PASTA_TESTE):
    shutil.rmtree(PASTA_TESTE)
os.makedirs(PASTA_TESTE)

senha = "senhaDeTeste123!"
chave = derive_encryption_key(senha)
usuario = "Teste"

# Abre o banco de teste e cria as tabelas
db = EncryptedDatabase(CAMINHO_BANCO, chave)
conexao = db.open()
garantir_tabelas_fase1(conexao)


# ---------------------------------------------------------------------------
# TESTE 1 — Criar fornecedor
# ---------------------------------------------------------------------------
linha("TESTE 1: Criar fornecedor")

forn_id = criar_fornecedor(
    conexao, nome="Confecção Bella", usuario=usuario,
    contato="(11) 3333-4444"
)
print(f"Fornecedor criado com id: {forn_id}")

fornecedor = buscar_fornecedor_por_id(conexao, forn_id)
print(f"Dados do fornecedor: {fornecedor}")
assert fornecedor is not None
assert fornecedor[1] == "Confecção Bella"
assert fornecedor[2] == "(11) 3333-4444"
print("\n[OK] Fornecedor criado e recuperado corretamente")


# ---------------------------------------------------------------------------
# TESTE 2 — Atualizar fornecedor
# ---------------------------------------------------------------------------
linha("TESTE 2: Atualizar fornecedor")

atualizar_fornecedor(conexao, forn_id, usuario, contato="(11) 5555-6666")
fornecedor_atualizado = buscar_fornecedor_por_id(conexao, forn_id)
print(f"Fornecedor atualizado: {fornecedor_atualizado}")
assert fornecedor_atualizado[2] == "(11) 5555-6666"
print("\n[OK] Fornecedor atualizado corretamente")


# ---------------------------------------------------------------------------
# TESTE 3 — Criar produto
# ---------------------------------------------------------------------------
linha("TESTE 3: Criar produto")

produto_id = criar_produto(
    conexao,
    codigo_etiqueta="BLU-001",
    descricao="Blusa manga longa azul",
    valor_compra=25.00,
    valor_venda=49.90,
    usuario=usuario,
    marca="Bella Moda",
    cor="Azul",
    tamanho="M",
    categoria="Blusa",
    fornecedor_id=forn_id,
    quantidade_estoque=5,
    data_compra="2026-09-01",
)
print(f"Produto criado com id: {produto_id}")

produto = buscar_produto_por_codigo(conexao, "BLU-001")
print(f"Dados do produto: {produto}")

assert produto is not None
assert produto[1] == "BLU-001"
assert produto[2] == "Blusa manga longa azul"
assert produto[8] == 25.00
assert produto[9] == 49.90
assert produto[10] == 5
assert produto[12] is None  # data_ultima_venda deve ser nula nesta fase
print("\n[OK] Produto criado e recuperado corretamente")


# ---------------------------------------------------------------------------
# TESTE 4 — Código de etiqueta duplicado
# ---------------------------------------------------------------------------
linha("TESTE 4: Código de etiqueta duplicado")

try:
    criar_produto(
        conexao,
        codigo_etiqueta="BLU-001",
        descricao="Outra blusa com mesmo código",
        valor_compra=30.00,
        valor_venda=59.90,
        usuario=usuario,
    )
    assert False, "Deveria ter levantado ValueError para código duplicado"
except ValueError as e:
    print(f"Código duplicado rejeitado corretamente: {e}")

print("\n[OK] Duplicata de codigo_etiqueta detectada e tratada")


# ---------------------------------------------------------------------------
# TESTE 5 — Validações de produto
# ---------------------------------------------------------------------------
linha("TESTE 5: Validações de produto")

# Código vazio
try:
    criar_produto(
        conexao, codigo_etiqueta="", descricao="Teste",
        valor_compra=10, valor_venda=20, usuario=usuario
    )
    assert False, "Deveria ter rejeitado código vazio"
except ValueError as e:
    print(f"Código vazio rejeitado: {e}")

# Valor de compra negativo
try:
    criar_produto(
        conexao, codigo_etiqueta="TEST-NEG", descricao="Teste",
        valor_compra=-5, valor_venda=20, usuario=usuario
    )
    assert False, "Deveria ter rejeitado valor de compra negativo"
except ValueError as e:
    print(f"Valor de compra negativo rejeitado: {e}")

# Valor de venda negativo
try:
    criar_produto(
        conexao, codigo_etiqueta="TEST-NEG2", descricao="Teste",
        valor_compra=10, valor_venda=-1, usuario=usuario
    )
    assert False, "Deveria ter rejeitado valor de venda negativo"
except ValueError as e:
    print(f"Valor de venda negativo rejeitado: {e}")

print("\n[OK] Todas as validações de produto funcionando")


# ---------------------------------------------------------------------------
# TESTE 6 — Ajustar estoque para cima
# ---------------------------------------------------------------------------
linha("TESTE 6: Ajustar estoque para cima (+3)")

novo_estoque = ajustar_estoque(conexao, produto_id, +3, usuario)
print(f"Estoque após ajuste de +3: {novo_estoque}")
assert novo_estoque == 8  # era 5, agora 8

produto_apos = buscar_produto_por_codigo(conexao, "BLU-001")
assert produto_apos[10] == 8
print("\n[OK] Estoque aumentado de 5 para 8")


# ---------------------------------------------------------------------------
# TESTE 7 — Ajustar estoque para baixo
# ---------------------------------------------------------------------------
linha("TESTE 7: Ajustar estoque para baixo (-2)")

novo_estoque = ajustar_estoque(conexao, produto_id, -2, usuario)
print(f"Estoque após ajuste de -2: {novo_estoque}")
assert novo_estoque == 6  # era 8, agora 6

produto_apos = buscar_produto_por_codigo(conexao, "BLU-001")
assert produto_apos[10] == 6
print("\n[OK] Estoque reduzido de 8 para 6")


# ---------------------------------------------------------------------------
# TESTE 8 — Tentar ajustar estoque para valor negativo (deve falhar)
# ---------------------------------------------------------------------------
linha("TESTE 8: Ajuste que resultaria em estoque negativo")

# Confirmar estado antes da tentativa
estoque_antes = buscar_produto_por_codigo(conexao, "BLU-001")[10]
print(f"Estoque atual: {estoque_antes}")

try:
    ajustar_estoque(conexao, produto_id, -100, usuario)
    assert False, "Deveria ter levantado ValueError para estoque negativo"
except ValueError as e:
    print(f"Ajuste negativo rejeitado: {e}")

# Confirmar que o banco NÃO foi alterado pela tentativa que falhou
estoque_depois = buscar_produto_por_codigo(conexao, "BLU-001")[10]
print(f"Estoque após tentativa rejeitada: {estoque_depois}")
assert estoque_depois == estoque_antes, (
    f"O estoque mudou mesmo com erro! Era {estoque_antes}, agora {estoque_depois}"
)
print("\n[OK] Estoque não foi alterado pela operação que falhou")


# ---------------------------------------------------------------------------
# TESTE 9 — Criar segundo produto e listar
# ---------------------------------------------------------------------------
linha("TESTE 9: Criar segundo produto e listar")

produto2_id = criar_produto(
    conexao,
    codigo_etiqueta="CAL-001",
    descricao="Calça jeans skinny",
    valor_compra=40.00,
    valor_venda=89.90,
    usuario=usuario,
    categoria="Calça",
    quantidade_estoque=3,
)
print(f"Produto 2 criado com id: {produto2_id}")

todos_produtos = listar_produtos(conexao)
print(f"Total de produtos cadastrados: {len(todos_produtos)}")
for p in todos_produtos:
    print(f"  - {p[1]}: {p[2]} | estoque={p[10]}")
assert len(todos_produtos) == 2
print("\n[OK] Dois produtos cadastrados e listados")


# ---------------------------------------------------------------------------
# TESTE 10 — Atualizar produto
# ---------------------------------------------------------------------------
linha("TESTE 10: Atualizar produto")

atualizar_produto(
    conexao, produto_id, usuario,
    valor_venda=54.90, cor="Azul Royal"
)
produto_atualizado = buscar_produto_por_codigo(conexao, "BLU-001")
print(f"Produto atualizado: valor_venda={produto_atualizado[9]}, cor={produto_atualizado[4]}")

assert produto_atualizado[9] == 54.90
assert produto_atualizado[4] == "Azul Royal"
# Campos não alterados devem permanecer iguais
assert produto_atualizado[2] == "Blusa manga longa azul"
assert produto_atualizado[8] == 25.00
print("\n[OK] Produto atualizado — campos não informados permaneceram iguais")


# ---------------------------------------------------------------------------
# TESTE 11 — Excluir produto
# ---------------------------------------------------------------------------
linha("TESTE 11: Excluir produto")

excluir_produto(conexao, produto2_id, usuario)
produto_excluido = conexao.execute(
    "SELECT * FROM produto WHERE id = ?", (produto2_id,)
).fetchone()
assert produto_excluido is None
print(f"Produto {produto2_id} excluído com sucesso")

todos_produtos_apos = listar_produtos(conexao)
assert len(todos_produtos_apos) == 1
print(f"Produtos restantes: {len(todos_produtos_apos)}")
print("\n[OK] Produto excluído corretamente")


# ---------------------------------------------------------------------------
# TESTE 12 — Excluir fornecedor
# ---------------------------------------------------------------------------
linha("TESTE 12: Excluir fornecedor")

# O produto BLU-001 ainda referencia este fornecedor. Antes de excluir,
# precisamos desvincular — setamos fornecedor_id como NULL diretamente
# via SQL, porque a função atualizar_produto() não aceita None como
# "limpar" um campo (None significa "não alterar").
conexao.execute(
    "UPDATE produto SET fornecedor_id = NULL WHERE id = ?", (produto_id,)
)
conexao.commit()

excluir_fornecedor(conexao, forn_id, usuario)
fornecedor_excluido = buscar_fornecedor_por_id(conexao, forn_id)
assert fornecedor_excluido is None
print(f"Fornecedor {forn_id} excluído com sucesso")

fornecedores_restantes = listar_fornecedores(conexao)
assert len(fornecedores_restantes) == 0
print("\n[OK] Fornecedor excluído corretamente")


# ---------------------------------------------------------------------------
# TESTE 13 — Verificar log de auditoria
# ---------------------------------------------------------------------------
linha("TESTE 13: Verificar log de auditoria")

entradas_produto = consultar_auditoria(conexao, tabela="produto")
entradas_fornecedor = consultar_auditoria(conexao, tabela="fornecedor")

print(f"Entradas de auditoria para 'produto': {len(entradas_produto)}")
for entrada in entradas_produto:
    print(f"  - id={entrada[0]} | op={entrada[2]} | registro={entrada[3]} | detalhes={entrada[6]}")

print(f"\nEntradas de auditoria para 'fornecedor': {len(entradas_fornecedor)}")
for entrada in entradas_fornecedor:
    print(f"  - id={entrada[0]} | op={entrada[2]} | registro={entrada[3]} | detalhes={entrada[6]}")

# Operações de produto:
# INSERT(BLU-001) + INSERT(CAL-001) = 2
# UPDATE estoque +3 = 1
# UPDATE estoque -2 = 1
# UPDATE(valor_venda + cor) = 1
# DELETE(CAL-001) = 1
# Total = 6
assert len(entradas_produto) == 6, (
    f"Esperado 6 entradas de auditoria para produto, encontrado {len(entradas_produto)}"
)

# Operações de fornecedor: INSERT + UPDATE(contato) + DELETE = 3
assert len(entradas_fornecedor) == 3, (
    f"Esperado 3 entradas de auditoria para fornecedor, encontrado {len(entradas_fornecedor)}"
)

# Verificar que as operações corretas estão presentes
operacoes_produto = [e[2] for e in entradas_produto]
assert "INSERT" in operacoes_produto
assert "UPDATE" in operacoes_produto
assert "DELETE" in operacoes_produto

operacoes_forn = [e[2] for e in entradas_fornecedor]
assert "INSERT" in operacoes_forn
assert "UPDATE" in operacoes_forn
assert "DELETE" in operacoes_forn

# Verificar que o ajuste de estoque registrou valor anterior e novo
# Procurar uma entrada de UPDATE em produto que tenha "quantidade_estoque"
import json
ajustes_estoque = [
    e for e in entradas_produto
    if e[2] == "UPDATE" and e[6] and "quantidade_estoque" in e[6]
]
print(f"\nAjustes de estoque auditados: {len(ajustes_estoque)}")
for ajuste in ajustes_estoque:
    detalhes = json.loads(ajuste[6])
    print(f"  - de={detalhes.get('de')} para={detalhes.get('para')} delta={detalhes.get('delta')}")
assert len(ajustes_estoque) >= 2, "Deveria haver pelo menos 2 ajustes de estoque auditados"

print("\n[OK] Todas as operações de escrita geraram entradas de auditoria")
print("[OK] Ajustes de estoque registram valor anterior e novo corretamente")


# ---------------------------------------------------------------------------
# Limpeza
# ---------------------------------------------------------------------------
db.close()
shutil.rmtree(PASTA_TESTE)

linha("TODOS OS TESTES DE PRODUTO E FORNECEDOR PASSARAM")

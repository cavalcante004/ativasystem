"""
test_fase1_cliente.py

Testes da Fase 1 para Cliente e Endereço: criação, atualização, exclusão
com cascata, validações, endereço principal, e log de auditoria.

Segue o mesmo padrão de test_fase0_backup_auditoria.py: script standalone,
prints explicativos em cada etapa, assert para validar, banco criptografado
de teste limpo ao final.

Rode com: python test_fase1_cliente.py
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(__file__))

from utils.security import derive_encryption_key
from database.connection import EncryptedDatabase
from database.schema import garantir_tabelas_fase1
from database.audit import consultar_auditoria
from models.cliente import (
    criar_cliente,
    buscar_cliente_por_id,
    listar_clientes,
    atualizar_cliente,
    excluir_cliente,
)
from models.endereco import (
    criar_endereco,
    listar_enderecos_do_cliente,
    atualizar_endereco,
    excluir_endereco,
    definir_endereco_principal,
)


def linha(titulo: str) -> None:
    print(f"\n{'=' * 60}\n{titulo}\n{'=' * 60}")


PASTA_TESTE = "backups/teste_temp"
CAMINHO_BANCO = f"{PASTA_TESTE}/loja_teste_fase1.db.enc"

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
# TESTE 1 — Criar cliente
# ---------------------------------------------------------------------------
linha("TESTE 1: Criar cliente")

cliente_id = criar_cliente(
    conexao, nome="Maria Silva", telefone="(11) 99999-0001",
    usuario=usuario, cpf="12345678901", observacoes="Cliente VIP"
)
print(f"Cliente criado com id: {cliente_id}")

cliente = buscar_cliente_por_id(conexao, cliente_id)
print(f"Dados do cliente: {cliente}")

assert cliente is not None
assert cliente[1] == "Maria Silva"
assert cliente[2] == "(11) 99999-0001"
assert cliente[3] == "12345678901"
assert cliente[5] == "Cliente VIP"
print("\n[OK] Cliente criado e recuperado corretamente")


# ---------------------------------------------------------------------------
# TESTE 2 — Criar segundo cliente (sem CPF)
# ---------------------------------------------------------------------------
linha("TESTE 2: Criar segundo cliente sem CPF")

cliente2_id = criar_cliente(
    conexao, nome="João Souza", telefone="(11) 88888-0001",
    usuario=usuario
)
print(f"Cliente 2 criado com id: {cliente2_id}")

todos_clientes = listar_clientes(conexao)
print(f"Total de clientes cadastrados: {len(todos_clientes)}")
assert len(todos_clientes) == 2
print("\n[OK] Segundo cliente criado sem CPF — listagem retorna 2 clientes")


# ---------------------------------------------------------------------------
# TESTE 3 — Validações de cliente
# ---------------------------------------------------------------------------
linha("TESTE 3: Validações de cliente")

# Nome muito curto
try:
    criar_cliente(conexao, nome="A", telefone="123", usuario=usuario)
    assert False, "Deveria ter levantado ValueError para nome curto"
except ValueError as e:
    print(f"Nome curto rejeitado: {e}")

# Telefone vazio
try:
    criar_cliente(conexao, nome="Teste", telefone="", usuario=usuario)
    assert False, "Deveria ter levantado ValueError para telefone vazio"
except ValueError as e:
    print(f"Telefone vazio rejeitado: {e}")

# CPF com formato errado
try:
    criar_cliente(
        conexao, nome="Teste", telefone="123", usuario=usuario, cpf="123"
    )
    assert False, "Deveria ter levantado ValueError para CPF inválido"
except ValueError as e:
    print(f"CPF inválido rejeitado: {e}")

print("\n[OK] Todas as validações de cliente funcionando")


# ---------------------------------------------------------------------------
# TESTE 4 — CPF duplicado
# ---------------------------------------------------------------------------
linha("TESTE 4: CPF duplicado")

try:
    criar_cliente(
        conexao, nome="Outra Pessoa", telefone="(11) 77777-0001",
        usuario=usuario, cpf="12345678901"
    )
    assert False, "Deveria ter levantado ValueError para CPF duplicado"
except ValueError as e:
    print(f"CPF duplicado rejeitado corretamente: {e}")

print("\n[OK] Duplicata de CPF detectada e tratada")


# ---------------------------------------------------------------------------
# TESTE 4b — CPF com formatação diferente deve ser detectado como duplicado
# ---------------------------------------------------------------------------
linha("TESTE 4b: CPF com formatação diferente (pontos e traço)")

# O cliente 1 foi criado com CPF "12345678901" (só dígitos).
# Tentar criar outro com "123.456.789-01" deve falhar — é o mesmo CPF.
try:
    criar_cliente(
        conexao, nome="Pessoa Formatada", telefone="(11) 66666-0001",
        usuario=usuario, cpf="123.456.789-01"
    )
    assert False, "Deveria ter levantado ValueError para CPF duplicado com formatação"
except ValueError as e:
    print(f"CPF com formatação diferente rejeitado corretamente: {e}")

print("\n[OK] CPF normalizado detecta duplicata independente da formatação")


# ---------------------------------------------------------------------------
# TESTE 5 — Criar múltiplos endereços para o mesmo cliente
# ---------------------------------------------------------------------------
linha("TESTE 5: Múltiplos endereços")

end1_id = criar_endereco(
    conexao, cliente_id=cliente_id, logradouro="Rua das Flores",
    cidade="São Paulo", usuario=usuario, numero="100", bairro="Centro",
    principal=True
)
print(f"Endereço 1 (principal) criado com id: {end1_id}")

end2_id = criar_endereco(
    conexao, cliente_id=cliente_id, logradouro="Av. Brasil",
    cidade="São Paulo", usuario=usuario, numero="200",
    referencia="Perto da padaria"
)
print(f"Endereço 2 criado com id: {end2_id}")

end3_id = criar_endereco(
    conexao, cliente_id=cliente_id, logradouro="Rua do Sítio",
    cidade="Ibiúna", usuario=usuario,
    referencia="Depois da ponte"
)
print(f"Endereço 3 criado com id: {end3_id}")

enderecos = listar_enderecos_do_cliente(conexao, cliente_id)
print(f"Total de endereços do cliente {cliente_id}: {len(enderecos)}")
assert len(enderecos) == 3

# Confirma que o endereço 1 é o principal
assert enderecos[0][7] == 1  # campo 'principal' do primeiro da lista
print(f"Endereço principal: id={enderecos[0][0]}, logradouro='{enderecos[0][2]}'")

print("\n[OK] 3 endereços criados, o primeiro marcado como principal")


# ---------------------------------------------------------------------------
# TESTE 6 — Definir endereço principal (e confirmar que o anterior muda pra 0)
# ---------------------------------------------------------------------------
linha("TESTE 6: Trocar endereço principal")

definir_endereco_principal(conexao, end3_id, usuario)
print(f"Endereço {end3_id} definido como principal")

enderecos = listar_enderecos_do_cliente(conexao, cliente_id)

# O endereço 3 (Rua do Sítio) agora deve ser o principal
end1_dados = [e for e in enderecos if e[0] == end1_id][0]
end3_dados = [e for e in enderecos if e[0] == end3_id][0]

assert end1_dados[7] == 0, f"Endereço 1 deveria ter principal=0, tem {end1_dados[7]}"
assert end3_dados[7] == 1, f"Endereço 3 deveria ter principal=1, tem {end3_dados[7]}"

print(f"Endereço 1 (Rua das Flores): principal={end1_dados[7]} (era 1, agora 0)")
print(f"Endereço 3 (Rua do Sítio): principal={end3_dados[7]} (era 0, agora 1)")
print("\n[OK] Troca de endereço principal funcionando — só um fica com 1")


# ---------------------------------------------------------------------------
# TESTE 7 — Atualizar endereço
# ---------------------------------------------------------------------------
linha("TESTE 7: Atualizar endereço")

atualizar_endereco(
    conexao, end2_id, usuario,
    logradouro="Av. Brasil (atualizada)", numero="201"
)
endereco_atualizado = conexao.execute(
    "SELECT * FROM endereco WHERE id = ?", (end2_id,)
).fetchone()
print(f"Endereço atualizado: {endereco_atualizado}")

assert endereco_atualizado[2] == "Av. Brasil (atualizada)"
assert endereco_atualizado[3] == "201"
print("\n[OK] Endereço atualizado corretamente")


# ---------------------------------------------------------------------------
# TESTE 8 — Atualizar cliente
# ---------------------------------------------------------------------------
linha("TESTE 8: Atualizar cliente")

atualizar_cliente(
    conexao, cliente_id, usuario,
    nome="Maria Silva Santos", observacoes="Cliente VIP - Frequente"
)
cliente_atualizado = buscar_cliente_por_id(conexao, cliente_id)
print(f"Cliente atualizado: {cliente_atualizado}")

assert cliente_atualizado[1] == "Maria Silva Santos"
assert cliente_atualizado[5] == "Cliente VIP - Frequente"
# Campos não informados devem permanecer inalterados
assert cliente_atualizado[2] == "(11) 99999-0001"
assert cliente_atualizado[3] == "12345678901"
print("\n[OK] Cliente atualizado — campos não informados permaneceram iguais")


# ---------------------------------------------------------------------------
# TESTE 9 — Excluir endereço individual
# ---------------------------------------------------------------------------
linha("TESTE 9: Excluir endereço individual")

excluir_endereco(conexao, end2_id, usuario)
enderecos_apos_exclusao = listar_enderecos_do_cliente(conexao, cliente_id)
print(f"Endereços restantes após excluir id {end2_id}: {len(enderecos_apos_exclusao)}")
assert len(enderecos_apos_exclusao) == 2
print("\n[OK] Endereço excluído individualmente")


# ---------------------------------------------------------------------------
# TESTE 10 — Excluir cliente (cascata nos endereços)
# ---------------------------------------------------------------------------
linha("TESTE 10: Excluir cliente com cascata nos endereços")

# Antes da exclusão: confirmar que existem endereços
enderecos_antes = listar_enderecos_do_cliente(conexao, cliente_id)
print(f"Endereços do cliente {cliente_id} antes da exclusão: {len(enderecos_antes)}")
assert len(enderecos_antes) == 2

excluir_cliente(conexao, cliente_id, usuario)

# Confirmar que o cliente foi excluído
cliente_excluido = buscar_cliente_por_id(conexao, cliente_id)
assert cliente_excluido is None
print("Cliente excluído com sucesso")

# Confirmar que os endereços foram excluídos em cascata
enderecos_apos = listar_enderecos_do_cliente(conexao, cliente_id)
print(f"Endereços do cliente {cliente_id} após exclusão: {len(enderecos_apos)}")
assert len(enderecos_apos) == 0
print("\n[OK] Exclusão em cascata funcionando — cliente e endereços removidos")


# ---------------------------------------------------------------------------
# TESTE 11 — Verificar log de auditoria
# ---------------------------------------------------------------------------
linha("TESTE 11: Verificar log de auditoria")

entradas_cliente = consultar_auditoria(conexao, tabela="cliente")
entradas_endereco = consultar_auditoria(conexao, tabela="endereco")

print(f"Entradas de auditoria para 'cliente': {len(entradas_cliente)}")
for entrada in entradas_cliente:
    print(f"  - id={entrada[0]} | op={entrada[2]} | registro={entrada[3]} | detalhes={entrada[6]}")

print(f"\nEntradas de auditoria para 'endereco': {len(entradas_endereco)}")
for entrada in entradas_endereco:
    print(f"  - id={entrada[0]} | op={entrada[2]} | registro={entrada[3]} | detalhes={entrada[6]}")

# Operações de cliente: INSERT(Maria) + INSERT(João) + UPDATE(Maria) + DELETE(Maria) = 4
assert len(entradas_cliente) == 4, (
    f"Esperado 4 entradas de auditoria para cliente, encontrado {len(entradas_cliente)}"
)

# Operações de endereço:
# INSERT(end1) + INSERT(end2) + INSERT(end3) = 3
# UPDATE(definir_principal end3) = 1
# UPDATE(atualizar end2) = 1
# DELETE(end2) manual = 1
# DELETE(end1) + DELETE(end3) auditoria da cascata = 2
# Total = 8
assert len(entradas_endereco) == 8, (
    f"Esperado 8 entradas de auditoria para endereço, encontrado {len(entradas_endereco)}"
)

# Verificar que as operações corretas estão presentes
operacoes_cliente = [e[2] for e in entradas_cliente]
assert "INSERT" in operacoes_cliente
assert "UPDATE" in operacoes_cliente
assert "DELETE" in operacoes_cliente
print("\n[OK] Todas as operações de escrita geraram entradas de auditoria")


# ---------------------------------------------------------------------------
# Limpeza
# ---------------------------------------------------------------------------
db.close()
shutil.rmtree(PASTA_TESTE)

linha("TODOS OS TESTES DE CLIENTE E ENDEREÇO PASSARAM")

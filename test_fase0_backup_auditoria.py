"""
test_fase0_backup_auditoria.py

Teste isolado das duas últimas peças da Fase 0: backup automático e
log de auditoria. Roda separado do test_fase0.py de propósito — cada
peça é testada sozinha antes de qualquer integração.

Rode com: python test_fase0_backup_auditoria.py
"""

import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from utils.security import derive_encryption_key
from utils.backup import BackupManager
from database.connection import EncryptedDatabase
from database.audit import garantir_tabela_log, registrar_auditoria, consultar_auditoria


def linha(titulo: str) -> None:
    print(f"\n{'=' * 60}\n{titulo}\n{'=' * 60}")


PASTA_TESTE = "backups/teste_temp"
CAMINHO_BANCO = f"{PASTA_TESTE}/loja.db.enc"
PASTA_BACKUP = f"{PASTA_TESTE}/backups"

if os.path.exists(PASTA_TESTE):
    shutil.rmtree(PASTA_TESTE)
os.makedirs(PASTA_TESTE)

senha = "minhaSenhaMestraForte123"
chave = derive_encryption_key(senha)


# ---------------------------------------------------------------------------
# TESTE 1 — Backup automático com política de retenção
# ---------------------------------------------------------------------------
linha("TESTE 1: Backup automático")

db = EncryptedDatabase(CAMINHO_BANCO, chave)
conexao = db.open()
conexao.execute("CREATE TABLE teste (id INTEGER PRIMARY KEY, valor TEXT)")
conexao.execute("INSERT INTO teste (valor) VALUES ('estado inicial')")
db.close()

gerenciador = BackupManager(CAMINHO_BANCO, PASTA_BACKUP, max_backups=3)

# cria 5 backups em sequência (com pequeno intervalo pra garantir carimbos diferentes)
for i in range(5):
    db = EncryptedDatabase(CAMINHO_BANCO, chave)
    conexao = db.open()
    conexao.execute("UPDATE teste SET valor = ? WHERE id = 1", (f"versão {i}",))
    db.close()
    gerenciador.criar_backup()
    time.sleep(1.1)  # garante carimbo de segundo diferente entre backups

backups_existentes = gerenciador.listar_backups()
print(f"Backups criados: 5 | Backups mantidos após retenção (max_backups=3): {len(backups_existentes)}")
for b in backups_existentes:
    print(f"  - {b.name}")

assert len(backups_existentes) == 3
print("\n[OK] Política de retenção manteve só os 3 backups mais recentes")

# --- Restaurando o backup mais antigo dos 3 mantidos, pra um destino de teste ---
backup_para_restaurar = backups_existentes[-1]  # o mais antigo dos que sobraram
destino_restauracao = f"{PASTA_TESTE}/restaurado.db.enc"
gerenciador.restaurar_backup(backup_para_restaurar, destino=destino_restauracao)

db_restaurado = EncryptedDatabase(destino_restauracao, chave)
conexao_restaurada = db_restaurado.open()
valor_restaurado = conexao_restaurada.execute("SELECT valor FROM teste").fetchone()[0]
db_restaurado.close()

print(f"\n[OK] Backup restaurado com sucesso — valor recuperado: '{valor_restaurado}'")


# ---------------------------------------------------------------------------
# TESTE 2 — Log de auditoria
# ---------------------------------------------------------------------------
linha("TESTE 2: Log de auditoria")

db = EncryptedDatabase(CAMINHO_BANCO, chave)
conexao = db.open()
garantir_tabela_log(conexao)

registrar_auditoria(
    conexao, tabela="produto", operacao="INSERT", registro_id=1,
    usuario="Arthur", detalhes={"nome": "Blusa azul P"},
)
registrar_auditoria(
    conexao, tabela="produto", operacao="UPDATE", registro_id=1,
    usuario="Arthur", detalhes={"campo": "quantidade_estoque", "de": 5, "para": 3},
)
registrar_auditoria(
    conexao, tabela="cliente", operacao="INSERT", registro_id=1,
    usuario="Arthur", detalhes={"nome": "Maria Teste"},
)

todas_entradas = consultar_auditoria(conexao)
entradas_produto = consultar_auditoria(conexao, tabela="produto")
db.close()

print(f"Total de entradas no log: {len(todas_entradas)}")
print(f"Entradas filtradas por tabela='produto': {len(entradas_produto)}")
for entrada in entradas_produto:
    print(f"  - {entrada}")

assert len(todas_entradas) == 3
assert len(entradas_produto) == 2
print("\n[OK] Log de auditoria gravou e filtrou corretamente")

shutil.rmtree(PASTA_TESTE)

linha("TODOS OS TESTES DE BACKUP E AUDITORIA PASSARAM")

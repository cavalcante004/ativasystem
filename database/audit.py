"""
database/audit.py

Log de auditoria: registra toda alteração relevante feita nos dados
(quem, o quê, quando, o que mudou). É o mecanismo direto contra o
desvio/perda que você mencionou no controle de condicional — se uma
peça "some" do sistema, dá pra rastrear exatamente quem mexeu e quando.

A tabela de log fica DENTRO do mesmo banco criptografado das demais
tabelas — assim ela também herda a criptografia em repouso, e não tem
como alguém apagar ou editar o log sem passar pela mesma conexão
(e portanto pela mesma senha) do restante do sistema.
"""

import json
import sqlite3
from datetime import datetime
from typing import Optional


CRIAR_TABELA_LOG = """
CREATE TABLE IF NOT EXISTS log_auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tabela TEXT NOT NULL,
    operacao TEXT NOT NULL CHECK (operacao IN ('INSERT', 'UPDATE', 'DELETE')),
    registro_id INTEGER,
    usuario TEXT NOT NULL,
    data_hora TEXT NOT NULL,
    detalhes TEXT
)
"""


def garantir_tabela_log(conexao: sqlite3.Connection) -> None:
    """Cria a tabela de log se ainda não existir. Chamar uma vez ao abrir o banco."""
    conexao.execute(CRIAR_TABELA_LOG)
    conexao.commit()


def registrar_auditoria(
    conexao: sqlite3.Connection,
    tabela: str,
    operacao: str,
    registro_id: Optional[int],
    usuario: str,
    detalhes: Optional[dict] = None,
) -> None:
    """
    Grava uma linha no log de auditoria.

    Exemplo de uso futuro, quando o módulo de Produto existir:

        registrar_auditoria(
            conexao, tabela="produto", operacao="UPDATE",
            registro_id=42, usuario="Arthur",
            detalhes={"campo": "quantidade_estoque", "de": 5, "para": 3},
        )
    """
    conexao.execute(
        "INSERT INTO log_auditoria (tabela, operacao, registro_id, usuario, data_hora, detalhes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            tabela,
            operacao,
            registro_id,
            usuario,
            datetime.now().isoformat(timespec="seconds"),
            json.dumps(detalhes, ensure_ascii=False) if detalhes else None,
        ),
    )
    conexao.commit()


def consultar_auditoria(conexao: sqlite3.Connection, tabela: Optional[str] = None) -> list:
    """Lista entradas do log, mais recentes primeiro, opcionalmente filtradas por tabela."""
    if tabela:
        cursor = conexao.execute(
            "SELECT * FROM log_auditoria WHERE tabela = ? ORDER BY id DESC", (tabela,)
        )
    else:
        cursor = conexao.execute("SELECT * FROM log_auditoria ORDER BY id DESC")
    return cursor.fetchall()

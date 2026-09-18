"""
models/fornecedor.py

CRUD simples para a entidade Fornecedor.

POR QUE FORNECEDOR É UMA TABELA SEPARADA (e não um campo texto no produto):
Um fornecedor fornece muitos produtos. Se o nome ou contato do fornecedor
mudar, queremos atualizar em UM lugar (a tabela fornecedor), não em
cada produto que veio dele. Além disso, na Fase 2 o fornecedor terá
relação com o motor de precificação (margem pode variar por fornecedor).

A TABELA É DELIBERADAMENTE SIMPLES NESTA FASE:
Só nome e contato. Campos como CNPJ, endereço do fornecedor, prazo de
entrega etc. podem ser adicionados em fases futuras se o negócio precisar.
"""

import sqlite3
from typing import Optional

from database.audit import registrar_auditoria


def criar_fornecedor(
    conexao: sqlite3.Connection,
    nome: str,
    usuario: str,
    contato: Optional[str] = None,
) -> int:
    """
    Insere um novo fornecedor no banco.

    conexao: conexão sqlite3 (via EncryptedDatabase.open()).
    nome: nome do fornecedor.
    usuario: quem está fazendo a operação (para auditoria).
    contato: telefone ou outro meio de contato (opcional).

    Retorna o id do fornecedor criado.
    """
    if not nome or not nome.strip():
        raise ValueError("O nome do fornecedor é obrigatório.")

    cursor = conexao.execute(
        "INSERT INTO fornecedor (nome, contato) VALUES (?, ?)",
        (nome.strip(), contato),
    )
    conexao.commit()

    fornecedor_id = cursor.lastrowid

    registrar_auditoria(
        conexao,
        tabela="fornecedor",
        operacao="INSERT",
        registro_id=fornecedor_id,
        usuario=usuario,
        detalhes={"nome": nome.strip(), "contato": contato},
    )

    return fornecedor_id


def buscar_fornecedor_por_id(
    conexao: sqlite3.Connection,
    fornecedor_id: int,
) -> Optional[tuple]:
    """
    Busca um fornecedor pelo id.

    Retorna uma tupla com os dados, ou None se não encontrado.
    """
    cursor = conexao.execute(
        "SELECT * FROM fornecedor WHERE id = ?", (fornecedor_id,)
    )
    return cursor.fetchone()


def listar_fornecedores(conexao: sqlite3.Connection) -> list[tuple]:
    """
    Lista todos os fornecedores cadastrados, ordenados por nome.

    Retorna lista de tuplas (pode ser vazia).
    """
    cursor = conexao.execute("SELECT * FROM fornecedor ORDER BY nome")
    return cursor.fetchall()


def atualizar_fornecedor(
    conexao: sqlite3.Connection,
    fornecedor_id: int,
    usuario: str,
    nome: Optional[str] = None,
    contato: Optional[str] = None,
) -> None:
    """
    Atualiza os dados de um fornecedor existente. Só os campos informados
    (não None) são alterados.

    Levanta ValueError se o fornecedor não existir.
    """
    fornecedor_atual = buscar_fornecedor_por_id(conexao, fornecedor_id)
    if fornecedor_atual is None:
        raise ValueError(f"Fornecedor com id {fornecedor_id} não encontrado.")

    # Ordem: id, nome, contato
    _, nome_atual, contato_atual = fornecedor_atual

    novo_nome = nome if nome is not None else nome_atual
    novo_contato = contato if contato is not None else contato_atual

    if not novo_nome or not novo_nome.strip():
        raise ValueError("O nome do fornecedor é obrigatório.")

    conexao.execute(
        "UPDATE fornecedor SET nome = ?, contato = ? WHERE id = ?",
        (novo_nome.strip(), novo_contato, fornecedor_id),
    )
    conexao.commit()

    alteracoes = {}
    if nome is not None and nome.strip() != nome_atual:
        alteracoes["nome"] = {"de": nome_atual, "para": nome.strip()}
    if contato is not None and contato != contato_atual:
        alteracoes["contato"] = {"de": contato_atual, "para": contato}

    registrar_auditoria(
        conexao,
        tabela="fornecedor",
        operacao="UPDATE",
        registro_id=fornecedor_id,
        usuario=usuario,
        detalhes=alteracoes,
    )


def excluir_fornecedor(
    conexao: sqlite3.Connection,
    fornecedor_id: int,
    usuario: str,
) -> None:
    """
    Exclui um fornecedor pelo id.

    Levanta ValueError se o fornecedor não existir.

    Nota: produtos vinculados a este fornecedor NÃO são excluídos em cascata
    (a FK de produto.fornecedor_id não tem ON DELETE CASCADE). Se houver
    produtos vinculados, o SQLite levantará IntegrityError — isso é
    intencional, porque excluir um fornecedor não deve apagar os produtos.
    """
    fornecedor_atual = buscar_fornecedor_por_id(conexao, fornecedor_id)
    if fornecedor_atual is None:
        raise ValueError(f"Fornecedor com id {fornecedor_id} não encontrado.")

    _, nome, contato = fornecedor_atual

    conexao.execute("DELETE FROM fornecedor WHERE id = ?", (fornecedor_id,))
    conexao.commit()

    registrar_auditoria(
        conexao,
        tabela="fornecedor",
        operacao="DELETE",
        registro_id=fornecedor_id,
        usuario=usuario,
        detalhes={"nome": nome, "contato": contato},
    )

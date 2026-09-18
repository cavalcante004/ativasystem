"""
models/endereco.py

Operações sobre a entidade Endereço, que pertence a um Cliente (1:N).

POR QUE ENDEREÇO É UMA TABELA SEPARADA:
Na realidade de venda na condicional em cidade pequena, é comum o cliente
ter mais de um endereço (casa da mãe, trabalho, sítio). Modelar como
campo dentro da tabela cliente forçaria um endereço por pessoa e perderia
essa informação. A tabela separada com FK permite N endereços por cliente,
com um marcado como "principal" para uso padrão (ex: entrega de peças).

CAMPO 'REFERENCIA':
Cidades pequenas frequentemente usam pontos de referência no lugar de
CEP — "perto da padaria do João", "depois da praça". Por isso o campo
existe e é relevante no domínio do negócio.
"""

import sqlite3
from typing import Optional

from database.audit import registrar_auditoria


def _validar_dados_endereco(logradouro: str, cidade: str) -> None:
    """
    Valida os campos obrigatórios do endereço.

    logradouro: rua/avenida — não pode ser vazio.
    cidade: não pode ser vazia.
    """
    if not logradouro or not logradouro.strip():
        raise ValueError("O logradouro do endereço é obrigatório.")

    if not cidade or not cidade.strip():
        raise ValueError("A cidade do endereço é obrigatória.")


def criar_endereco(
    conexao: sqlite3.Connection,
    cliente_id: int,
    logradouro: str,
    cidade: str,
    usuario: str,
    numero: Optional[str] = None,
    bairro: Optional[str] = None,
    referencia: Optional[str] = None,
    principal: bool = False,
) -> int:
    """
    Insere um novo endereço vinculado a um cliente.

    conexao: conexão sqlite3 (via EncryptedDatabase.open()).
    cliente_id: id do cliente dono do endereço.
    logradouro: rua/avenida.
    cidade: cidade.
    usuario: quem está fazendo a operação (para auditoria).
    numero: número (opcional — nem todo endereço rural tem número).
    bairro: bairro (opcional).
    referencia: ponto de referência (opcional).
    principal: se True, marca este como endereço principal do cliente
               (e desmarca qualquer outro que fosse principal antes).

    Retorna o id do endereço criado.
    """
    _validar_dados_endereco(logradouro, cidade)

    valor_principal = 1 if principal else 0

    # Se este endereço deve ser o principal, desmarca os outros primeiro
    if principal:
        conexao.execute(
            "UPDATE endereco SET principal = 0 WHERE cliente_id = ?",
            (cliente_id,),
        )

    try:
        cursor = conexao.execute(
            "INSERT INTO endereco (cliente_id, logradouro, numero, bairro, cidade, referencia, principal) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (cliente_id, logradouro.strip(), numero, bairro, cidade.strip(), referencia, valor_principal),
        )
        conexao.commit()
    except sqlite3.IntegrityError as exc:
        # FK inválida — cliente_id não existe na tabela cliente
        raise ValueError(
            f"Cliente com id {cliente_id} não encontrado. "
            "Não é possível criar endereço para um cliente inexistente."
        ) from exc

    endereco_id = cursor.lastrowid

    registrar_auditoria(
        conexao,
        tabela="endereco",
        operacao="INSERT",
        registro_id=endereco_id,
        usuario=usuario,
        detalhes={
            "cliente_id": cliente_id,
            "logradouro": logradouro.strip(),
            "cidade": cidade.strip(),
            "principal": valor_principal,
        },
    )

    return endereco_id


def listar_enderecos_do_cliente(
    conexao: sqlite3.Connection,
    cliente_id: int,
) -> list[tuple]:
    """
    Lista todos os endereços de um cliente específico.

    Retorna lista de tuplas (pode ser vazia se o cliente não tiver endereços).
    """
    cursor = conexao.execute(
        "SELECT * FROM endereco WHERE cliente_id = ? ORDER BY principal DESC, id",
        (cliente_id,),
    )
    return cursor.fetchall()


def atualizar_endereco(
    conexao: sqlite3.Connection,
    endereco_id: int,
    usuario: str,
    logradouro: Optional[str] = None,
    numero: Optional[str] = None,
    bairro: Optional[str] = None,
    cidade: Optional[str] = None,
    referencia: Optional[str] = None,
) -> None:
    """
    Atualiza os dados de um endereço existente. Só os campos informados
    (não None) são alterados.

    Nota: para alterar o campo 'principal', use definir_endereco_principal().

    Levanta ValueError se o endereço não existir.
    """
    endereco_atual = conexao.execute(
        "SELECT * FROM endereco WHERE id = ?", (endereco_id,)
    ).fetchone()

    if endereco_atual is None:
        raise ValueError(f"Endereço com id {endereco_id} não encontrado.")

    # Ordem: id, cliente_id, logradouro, numero, bairro, cidade, referencia, principal
    _, cliente_id, log_atual, num_atual, bairro_atual, cidade_atual, ref_atual, _ = endereco_atual

    novo_logradouro = logradouro if logradouro is not None else log_atual
    novo_numero = numero if numero is not None else num_atual
    novo_bairro = bairro if bairro is not None else bairro_atual
    nova_cidade = cidade if cidade is not None else cidade_atual
    nova_referencia = referencia if referencia is not None else ref_atual

    _validar_dados_endereco(novo_logradouro, nova_cidade)

    conexao.execute(
        "UPDATE endereco SET logradouro = ?, numero = ?, bairro = ?, "
        "cidade = ?, referencia = ? WHERE id = ?",
        (novo_logradouro.strip(), novo_numero, novo_bairro, nova_cidade.strip(), nova_referencia, endereco_id),
    )
    conexao.commit()

    alteracoes = {}
    if logradouro is not None and logradouro.strip() != log_atual:
        alteracoes["logradouro"] = {"de": log_atual, "para": logradouro.strip()}
    if numero is not None and numero != num_atual:
        alteracoes["numero"] = {"de": num_atual, "para": numero}
    if bairro is not None and bairro != bairro_atual:
        alteracoes["bairro"] = {"de": bairro_atual, "para": bairro}
    if cidade is not None and cidade.strip() != cidade_atual:
        alteracoes["cidade"] = {"de": cidade_atual, "para": cidade.strip()}
    if referencia is not None and referencia != ref_atual:
        alteracoes["referencia"] = {"de": ref_atual, "para": referencia}

    registrar_auditoria(
        conexao,
        tabela="endereco",
        operacao="UPDATE",
        registro_id=endereco_id,
        usuario=usuario,
        detalhes=alteracoes,
    )


def excluir_endereco(
    conexao: sqlite3.Connection,
    endereco_id: int,
    usuario: str,
) -> None:
    """
    Exclui um endereço pelo id.

    Levanta ValueError se o endereço não existir.
    """
    endereco_atual = conexao.execute(
        "SELECT * FROM endereco WHERE id = ?", (endereco_id,)
    ).fetchone()

    if endereco_atual is None:
        raise ValueError(f"Endereço com id {endereco_id} não encontrado.")

    _, cliente_id, logradouro, _, _, cidade, _, _ = endereco_atual

    conexao.execute("DELETE FROM endereco WHERE id = ?", (endereco_id,))
    conexao.commit()

    registrar_auditoria(
        conexao,
        tabela="endereco",
        operacao="DELETE",
        registro_id=endereco_id,
        usuario=usuario,
        detalhes={"cliente_id": cliente_id, "logradouro": logradouro, "cidade": cidade},
    )


def definir_endereco_principal(
    conexao: sqlite3.Connection,
    endereco_id: int,
    usuario: str,
) -> None:
    """
    Define um endereço como principal do seu cliente, desmarcando qualquer
    outro endereço do mesmo cliente que fosse principal antes.

    Garante que apenas um endereço por cliente tenha principal = 1.

    Levanta ValueError se o endereço não existir.
    """
    endereco = conexao.execute(
        "SELECT id, cliente_id, principal FROM endereco WHERE id = ?",
        (endereco_id,),
    ).fetchone()

    if endereco is None:
        raise ValueError(f"Endereço com id {endereco_id} não encontrado.")

    _, cliente_id, principal_atual = endereco

    # Zera todos os endereços do cliente e marca só o escolhido.
    # Fazemos numa "transação lógica": as duas operações em sequência
    # com um único commit no final.
    conexao.execute(
        "UPDATE endereco SET principal = 0 WHERE cliente_id = ?",
        (cliente_id,),
    )
    conexao.execute(
        "UPDATE endereco SET principal = 1 WHERE id = ?",
        (endereco_id,),
    )
    conexao.commit()

    registrar_auditoria(
        conexao,
        tabela="endereco",
        operacao="UPDATE",
        registro_id=endereco_id,
        usuario=usuario,
        detalhes={
            "acao": "definir_endereco_principal",
            "cliente_id": cliente_id,
            "principal": {"de": principal_atual, "para": 1},
        },
    )

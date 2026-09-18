"""
models/condicional.py

Operações de negócio sobre a entidade Condicional (cabeçalho e itens): 
criação, adição de itens, resolução de itens, e finalização.
"""

import sqlite3
from typing import Optional
from datetime import datetime

from database.audit import registrar_auditoria
from models.cliente import buscar_cliente_por_id
from models.produto import buscar_produto_por_id, ajustar_estoque


# ===========================================================================
# CABEÇALHO (Condicional)
# ===========================================================================

def criar_condicional(
    conexao: sqlite3.Connection,
    cliente_id: int,
    data_entrega: str,
    data_prazo: str,
    endereco_entrega: str,
    quem_entregou: str,
    usuario: str,
    observacoes: Optional[str] = None,
) -> int:
    if not buscar_cliente_por_id(conexao, cliente_id):
        raise ValueError(f"Cliente com id {cliente_id} não encontrado.")

    if not data_entrega or not data_entrega.strip():
        raise ValueError("A data de entrega é obrigatória.")

    if not data_prazo or not data_prazo.strip():
        raise ValueError("A data de prazo é obrigatória.")

    if data_prazo < data_entrega:
        raise ValueError(f"A data de prazo ({data_prazo}) não pode ser anterior à data de entrega ({data_entrega}).")

    if not endereco_entrega or not endereco_entrega.strip():
        raise ValueError("O endereço de entrega é obrigatório.")

    if not quem_entregou or not quem_entregou.strip():
        raise ValueError("O nome de quem entregou é obrigatório.")

    cursor = conexao.execute(
        "INSERT INTO condicional "
        "(cliente_id, data_entrega, data_prazo, endereco_entrega, quem_entregou, observacoes, status) "
        "VALUES (?, ?, ?, ?, ?, ?, 'ativa')",
        (cliente_id, data_entrega.strip(), data_prazo.strip(), endereco_entrega.strip(), quem_entregou.strip(), observacoes)
    )
    conexao.commit()

    condicional_id = cursor.lastrowid

    registrar_auditoria(
        conexao,
        tabela="condicional",
        operacao="INSERT",
        registro_id=condicional_id,
        usuario=usuario,
        detalhes={
            "cliente_id": cliente_id,
            "data_entrega": data_entrega.strip(),
            "data_prazo": data_prazo.strip(),
            "endereco_entrega": endereco_entrega.strip(),
            "quem_entregou": quem_entregou.strip(),
            "status": "ativa"
        }
    )

    return condicional_id


def buscar_condicional_por_id(
    conexao: sqlite3.Connection,
    condicional_id: int,
) -> Optional[tuple]:
    cursor = conexao.execute(
        "SELECT * FROM condicional WHERE id = ?",
        (condicional_id,)
    )
    return cursor.fetchone()


def listar_condicionais(
    conexao: sqlite3.Connection,
    status: Optional[str] = None,
) -> list[tuple]:
    if status:
        cursor = conexao.execute(
            "SELECT * FROM condicional WHERE status = ? ORDER BY data_entrega DESC",
            (status,)
        )
    else:
        cursor = conexao.execute("SELECT * FROM condicional ORDER BY data_entrega DESC")
    return cursor.fetchall()


def listar_condicionais_do_cliente(
    conexao: sqlite3.Connection,
    cliente_id: int,
) -> list[tuple]:
    cursor = conexao.execute(
        "SELECT * FROM condicional WHERE cliente_id = ? ORDER BY data_entrega DESC",
        (cliente_id,)
    )
    return cursor.fetchall()


def esta_vencida(
    conexao: sqlite3.Connection,
    condicional_id: int,
) -> bool:
    condicional = buscar_condicional_por_id(conexao, condicional_id)
    if not condicional:
        raise ValueError(f"Condicional com id {condicional_id} não encontrada.")
    
    # Ordem: id, cliente_id, data_entrega, data_prazo, data_retirada, endereco_entrega, endereco_retirada, quem_entregou, quem_retirou, status, observacoes
    status = condicional[9]
    data_prazo = condicional[3]

    if status != 'ativa':
        return False
    
    hoje = datetime.now().isoformat()[:10] # Apenas parte da data YYYY-MM-DD
    # Considerar comparação correta usando strings ISO.
    # Ex: '2026-09-17' > '2026-09-16' (vencida)
    # Se a data de prazo está "no passado" em relação a hoje:
    # Se tem horário no banco (ex: 2026-09-16T... e comparar apenas até o dia ou ISO todo)
    # Comparar strings ISO:
    return hoje > data_prazo


def listar_condicionais_vencidas(
    conexao: sqlite3.Connection,
) -> list[tuple]:
    ativas = listar_condicionais(conexao, status="ativa")
    hoje = datetime.now().isoformat()[:10]
    
    vencidas = []
    for cond in ativas:
        # data_prazo = cond[3]
        if hoje > cond[3]:
            vencidas.append(cond)
            
    return vencidas


def finalizar_condicional(
    conexao: sqlite3.Connection,
    condicional_id: int,
    quem_retirou: str,
    usuario: str,
    endereco_retirada: Optional[str] = None,
) -> None:
    condicional = buscar_condicional_por_id(conexao, condicional_id)
    if not condicional:
        raise ValueError(f"Condicional com id {condicional_id} não encontrada.")
    
    status = condicional[9]
    if status == 'finalizada':
        raise ValueError(f"A condicional {condicional_id} já está finalizada.")

    if not quem_retirou or not quem_retirou.strip():
        raise ValueError("O nome de quem retirou é obrigatório para finalizar a condicional.")

    itens = listar_itens_condicional(conexao, condicional_id)
    
    pendentes = []
    for item in itens:
        # id, condicional_id, produto_id, qtd_retirada, qtd_boa, qtd_problema, qtd_vendida
        qtd_retirada = item[3]
        qtd_boa = item[4]
        qtd_problema = item[5]
        qtd_vendida = item[6]
        
        resolvido = qtd_boa + qtd_problema + qtd_vendida
        if resolvido < qtd_retirada:
            pendentes.append(f"Produto ID {item[2]}: faltam {qtd_retirada - resolvido} de {qtd_retirada}")

    if pendentes:
        raise ValueError("Não é possível finalizar a condicional. Há itens pendentes:\n" + "\n".join(pendentes))

    hoje = datetime.now().isoformat()
    endereco_ret_final = endereco_retirada.strip() if endereco_retirada else condicional[5] # usa endereco_entrega se não informado

    conexao.execute(
        "UPDATE condicional SET status = 'finalizada', data_retirada = ?, quem_retirou = ?, endereco_retirada = ? WHERE id = ?",
        (hoje, quem_retirou.strip(), endereco_ret_final, condicional_id)
    )
    conexao.commit()

    registrar_auditoria(
        conexao,
        tabela="condicional",
        operacao="UPDATE",
        registro_id=condicional_id,
        usuario=usuario,
        detalhes={
            "status": {"de": "ativa", "para": "finalizada"},
            "data_retirada": hoje,
            "quem_retirou": quem_retirou.strip(),
            "endereco_retirada": endereco_ret_final
        }
    )


# ===========================================================================
# ITENS
# ===========================================================================

def adicionar_item_condicional(
    conexao: sqlite3.Connection,
    condicional_id: int,
    produto_id: int,
    quantidade: int,
    usuario: str,
) -> int:
    condicional = buscar_condicional_por_id(conexao, condicional_id)
    if not condicional:
        raise ValueError(f"Condicional com id {condicional_id} não encontrada.")
    
    if condicional[9] != 'ativa':
        raise ValueError("Não é possível adicionar itens em uma condicional que não está ativa.")

    produto = buscar_produto_por_id(conexao, produto_id)
    if not produto:
        raise ValueError(f"Produto com id {produto_id} não encontrado.")

    if quantidade <= 0:
        raise ValueError("A quantidade retirada deve ser maior que zero.")

    # Verifica estoque
    estoque_atual = produto[10]
    if quantidade > estoque_atual:
        raise ValueError(f"Estoque insuficiente para o produto '{produto[1]}'. Solicitado: {quantidade}, Disponível: {estoque_atual}.")

    # Decrementa o estoque fisicamente - reaproveitando ajustar_estoque
    ajustar_estoque(conexao, produto_id, -quantidade, usuario)

    # Adiciona o item
    cursor = conexao.execute(
        "INSERT INTO item_condicional (condicional_id, produto_id, quantidade_retirada) VALUES (?, ?, ?)",
        (condicional_id, produto_id, quantidade)
    )
    conexao.commit()

    item_id = cursor.lastrowid

    registrar_auditoria(
        conexao,
        tabela="item_condicional",
        operacao="INSERT",
        registro_id=item_id,
        usuario=usuario,
        detalhes={
            "condicional_id": condicional_id,
            "produto_id": produto_id,
            "quantidade_retirada": quantidade
        }
    )

    return item_id


def listar_itens_condicional(
    conexao: sqlite3.Connection,
    condicional_id: int,
) -> list[tuple]:
    cursor = conexao.execute(
        "SELECT * FROM item_condicional WHERE condicional_id = ?",
        (condicional_id,)
    )
    return cursor.fetchall()


def resolver_item(
    conexao: sqlite3.Connection,
    item_id: int,
    usuario: str,
    quantidade_devolvida_boa: int = 0,
    quantidade_devolvida_com_problema: int = 0,
    quantidade_vendida: int = 0,
) -> None:
    if quantidade_devolvida_boa < 0 or quantidade_devolvida_com_problema < 0 or quantidade_vendida < 0:
        raise ValueError("Nenhuma quantidade informada pode ser negativa.")

    cursor = conexao.execute("SELECT * FROM item_condicional WHERE id = ?", (item_id,))
    item = cursor.fetchone()
    
    if not item:
        raise ValueError(f"Item de condicional com id {item_id} não encontrado.")

    # 0: id, 1: condicional_id, 2: produto_id, 3: qtd_retirada, 4: qtd_boa, 5: qtd_problema, 6: qtd_vendida
    produto_id = item[2]
    qtd_retirada = item[3]
    atual_boa = item[4]
    atual_problema = item[5]
    atual_vendida = item[6]

    resolvido_antes = atual_boa + atual_problema + atual_vendida
    nova_resolucao = quantidade_devolvida_boa + quantidade_devolvida_com_problema + quantidade_vendida

    if resolvido_antes + nova_resolucao > qtd_retirada:
        disponivel = qtd_retirada - resolvido_antes
        raise ValueError(f"A quantidade informada excede o que falta resolver. Faltam apenas {disponivel} peça(s) para resolver neste item.")

    novo_boa = atual_boa + quantidade_devolvida_boa
    novo_problema = atual_problema + quantidade_devolvida_com_problema
    novo_vendida = atual_vendida + quantidade_vendida

    # Devolver ao estoque as peças boas
    if quantidade_devolvida_boa > 0:
        ajustar_estoque(conexao, produto_id, +quantidade_devolvida_boa, usuario)

    conexao.execute(
        "UPDATE item_condicional SET quantidade_devolvida_boa = ?, quantidade_devolvida_com_problema = ?, quantidade_vendida = ? WHERE id = ?",
        (novo_boa, novo_problema, novo_vendida, item_id)
    )
    conexao.commit()

    registrar_auditoria(
        conexao,
        tabela="item_condicional",
        operacao="UPDATE",
        registro_id=item_id,
        usuario=usuario,
        detalhes={
            "incrementos": {
                "quantidade_devolvida_boa": quantidade_devolvida_boa,
                "quantidade_devolvida_com_problema": quantidade_devolvida_com_problema,
                "quantidade_vendida": quantidade_vendida
            },
            "estado_atual": {
                "quantidade_devolvida_boa": novo_boa,
                "quantidade_devolvida_com_problema": novo_problema,
                "quantidade_vendida": novo_vendida
            }
        }
    )

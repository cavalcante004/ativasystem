"""
models/venda.py

Operações de negócio sobre a entidade Venda (cabeçalho e itens): 
criação, baixa de estoque, recebimento de pagamento,
e cálculo de métricas para o cliente e para a loja.
"""

import sqlite3
from typing import Optional, List, Dict
from datetime import datetime, timedelta

from database.audit import registrar_auditoria
from models.cliente import buscar_cliente_por_id
from models.produto import buscar_produto_por_id, ajustar_estoque, atualizar_produto


# ===========================================================================
# CABEÇALHO E ITENS (Venda)
# ===========================================================================

def criar_venda(
    conexao: sqlite3.Connection,
    cliente_id: int,
    forma_pagamento: str,
    itens: List[Dict],
    usuario: str,
    data_venda: Optional[str] = None,
    status_pagamento: str = 'pago',
    data_vencimento: Optional[str] = None,
    observacoes: Optional[str] = None,
) -> int:
    # Validações de Cabeçalho
    if not buscar_cliente_por_id(conexao, cliente_id):
        raise ValueError(f"Cliente com id {cliente_id} não encontrado.")

    formas_pagamento_validas = ('dinheiro', 'pix', 'cartao_credito', 'cartao_debito', 'outro')
    if forma_pagamento not in formas_pagamento_validas:
        raise ValueError(f"Forma de pagamento '{forma_pagamento}' inválida. Use uma destas: {', '.join(formas_pagamento_validas)}.")

    status_pagamento_validos = ('pago', 'pendente')
    if status_pagamento not in status_pagamento_validos:
        raise ValueError(f"Status de pagamento '{status_pagamento}' inválido. Use 'pago' ou 'pendente'.")

    if status_pagamento == 'pendente' and not data_vencimento:
        raise ValueError("A data de vencimento é obrigatória para vendas com status 'pendente'.")

    if not itens:
        raise ValueError("A venda deve conter pelo menos um item.")

    data_venda_final = data_venda if data_venda else datetime.now().isoformat()
    data_pagamento_efetivo = data_venda_final if status_pagamento == 'pago' else None

    # PRIMEIRA PASSADA: Validação (sem alterar banco)
    for item in itens:
        produto_id = item.get('produto_id')
        quantidade = item.get('quantidade')
        preco_unitario = item.get('preco_unitario')

        if produto_id is None or quantidade is None or preco_unitario is None:
            raise ValueError("Todos os itens devem conter 'produto_id', 'quantidade' e 'preco_unitario'.")

        if quantidade <= 0:
            raise ValueError(f"A quantidade do produto {produto_id} deve ser maior que zero.")

        if preco_unitario < 0:
            raise ValueError(f"O preço unitário do produto {produto_id} não pode ser negativo.")

        produto = buscar_produto_por_id(conexao, produto_id)
        if not produto:
            raise ValueError(f"Produto com id {produto_id} não encontrado.")

        estoque_atual = produto[10]
        if quantidade > estoque_atual:
            raise ValueError(f"Estoque insuficiente para o produto '{produto[1]}'. Solicitado: {quantidade}, Disponível: {estoque_atual}.")

    # SEGUNDA PASSADA: Escrita (cabeçalho, itens, estoque, data_ultima_venda e auditoria)
    cursor = conexao.execute(
        "INSERT INTO venda (cliente_id, data_venda, forma_pagamento, status_pagamento, data_vencimento, data_pagamento_efetivo, observacoes) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (cliente_id, data_venda_final, forma_pagamento, status_pagamento, data_vencimento, data_pagamento_efetivo, observacoes)
    )
    venda_id = cursor.lastrowid

    registrar_auditoria(
        conexao,
        tabela="venda",
        operacao="INSERT",
        registro_id=venda_id,
        usuario=usuario,
        detalhes={
            "cliente_id": cliente_id,
            "data_venda": data_venda_final,
            "forma_pagamento": forma_pagamento,
            "status_pagamento": status_pagamento,
            "data_vencimento": data_vencimento,
            "data_pagamento_efetivo": data_pagamento_efetivo,
            "observacoes": observacoes
        }
    )

    for item in itens:
        produto_id = item['produto_id']
        quantidade = item['quantidade']
        preco_unitario = item['preco_unitario']

        # Insere o item da venda
        cursor_item = conexao.execute(
            "INSERT INTO item_venda (venda_id, produto_id, quantidade, preco_unitario_praticado) VALUES (?, ?, ?, ?)",
            (venda_id, produto_id, quantidade, preco_unitario)
        )
        item_id = cursor_item.lastrowid

        registrar_auditoria(
            conexao,
            tabela="item_venda",
            operacao="INSERT",
            registro_id=item_id,
            usuario=usuario,
            detalhes={
                "venda_id": venda_id,
                "produto_id": produto_id,
                "quantidade": quantidade,
                "preco_unitario_praticado": preco_unitario
            }
        )

        # Decrementa o estoque fisicamente
        ajustar_estoque(conexao, produto_id, -quantidade, usuario)

        # Atualiza a data da última venda do produto
        atualizar_produto(conexao, produto_id, usuario, data_ultima_venda=data_venda_final[:10])

    conexao.commit()
    return venda_id


def buscar_venda_por_id(
    conexao: sqlite3.Connection,
    venda_id: int,
) -> Optional[tuple]:
    cursor = conexao.execute(
        "SELECT * FROM venda WHERE id = ?",
        (venda_id,)
    )
    return cursor.fetchone()


def listar_vendas(
    conexao: sqlite3.Connection,
    cliente_id: Optional[int] = None,
    status_pagamento: Optional[str] = None,
) -> list[tuple]:
    query = "SELECT * FROM venda WHERE 1=1"
    parametros = []

    if cliente_id is not None:
        query += " AND cliente_id = ?"
        parametros.append(cliente_id)

    if status_pagamento is not None:
        query += " AND status_pagamento = ?"
        parametros.append(status_pagamento)

    query += " ORDER BY data_venda DESC"
    cursor = conexao.execute(query, parametros)
    return cursor.fetchall()


def listar_itens_venda(
    conexao: sqlite3.Connection,
    venda_id: int,
) -> list[tuple]:
    cursor = conexao.execute(
        "SELECT * FROM item_venda WHERE venda_id = ?",
        (venda_id,)
    )
    return cursor.fetchall()


def calcular_total_venda(
    conexao: sqlite3.Connection,
    venda_id: int,
) -> float:
    itens = listar_itens_venda(conexao, venda_id)
    total = 0.0
    for item in itens:
        # id, venda_id, produto_id, quantidade, preco_unitario_praticado
        quantidade = item[3]
        preco_unitario = item[4]
        total += quantidade * preco_unitario
    return total


def marcar_venda_como_paga(
    conexao: sqlite3.Connection,
    venda_id: int,
    usuario: str,
    data_pagamento: Optional[str] = None,
) -> None:
    venda = buscar_venda_por_id(conexao, venda_id)
    if not venda:
        raise ValueError(f"Venda com id {venda_id} não encontrada.")

    # id, cliente_id, data_venda, forma_pagamento, status_pagamento, data_vencimento, data_pagamento_efetivo, observacoes
    status_atual = venda[4]
    if status_atual == 'pago':
        raise ValueError(f"A venda {venda_id} já está paga.")

    data_pagamento_final = data_pagamento if data_pagamento else datetime.now().isoformat()

    conexao.execute(
        "UPDATE venda SET status_pagamento = 'pago', data_pagamento_efetivo = ? WHERE id = ?",
        (data_pagamento_final, venda_id)
    )
    conexao.commit()

    registrar_auditoria(
        conexao,
        tabela="venda",
        operacao="UPDATE",
        registro_id=venda_id,
        usuario=usuario,
        detalhes={
            "status_pagamento": {"de": "pendente", "para": "pago"},
            "data_pagamento_efetivo": data_pagamento_final
        }
    )


def esta_atrasada(
    conexao: sqlite3.Connection,
    venda_id: int,
) -> bool:
    venda = buscar_venda_por_id(conexao, venda_id)
    if not venda:
        raise ValueError(f"Venda com id {venda_id} não encontrada.")

    status_pagamento = venda[4]
    data_vencimento = venda[5]

    if status_pagamento != 'pendente' or not data_vencimento:
        return False

    hoje = datetime.now().isoformat()[:10]
    return hoje > data_vencimento


def listar_vendas_atrasadas(
    conexao: sqlite3.Connection,
) -> list[tuple]:
    vendas_pendentes = listar_vendas(conexao, status_pagamento='pendente')
    hoje = datetime.now().isoformat()[:10]
    
    atrasadas = []
    for venda in vendas_pendentes:
        data_vencimento = venda[5]
        if data_vencimento and hoje > data_vencimento:
            atrasadas.append(venda)
            
    return atrasadas


# ===========================================================================
# MÉTRICAS DO CLIENTE E MOTOR FINANCEIRO
# ===========================================================================

def calcular_total_comprado_cliente(
    conexao: sqlite3.Connection,
    cliente_id: int,
) -> float:
    vendas = listar_vendas(conexao, cliente_id=cliente_id)
    total = 0.0
    for venda in vendas:
        total += calcular_total_venda(conexao, venda[0])
    return total


def calcular_comportamento_pagamento_cliente(
    conexao: sqlite3.Connection,
    cliente_id: int,
) -> dict:
    """
    Retorna estatísticas de pagamento:
    - pagas_em_dia: à vista ou (status='pago' E data_pagamento_efetivo <= data_vencimento)
    - pagas_atrasadas: (status='pago' E data_pagamento_efetivo > data_vencimento)
    - pendentes_em_aberto: status='pendente'
    """
    vendas = listar_vendas(conexao, cliente_id=cliente_id)
    
    pagas_em_dia = 0
    pagas_atrasadas = 0
    pendentes_em_aberto = 0

    for venda in vendas:
        status_pagamento = venda[4]
        data_vencimento = venda[5]
        data_pagamento_efetivo = venda[6]

        if status_pagamento == 'pendente':
            pendentes_em_aberto += 1
        elif status_pagamento == 'pago':
            # Se não tem vencimento ou não tem data de pagamento efetivo (ex: pagou na hora), consideramos em dia
            if not data_vencimento or not data_pagamento_efetivo:
                pagas_em_dia += 1
            else:
                # Compara apenas até o dia (YYYY-MM-DD)
                vencimento_dia = data_vencimento[:10]
                pagamento_dia = data_pagamento_efetivo[:10]
                if pagamento_dia <= vencimento_dia:
                    pagas_em_dia += 1
                else:
                    pagas_atrasadas += 1

    return {
        "pagas_em_dia": pagas_em_dia,
        "pagas_atrasadas": pagas_atrasadas,
        "pendentes_em_aberto": pendentes_em_aberto
    }


def calcular_media_vendas_mensais_reais(
    conexao: sqlite3.Connection,
    meses: int = 3,
) -> float:
    """
    Calcula a média real de peças vendidas por mês, 
    com base no histórico de itens vendidos nos últimos 'meses'.
    
    AVISO: Esta função APENAS calcula o valor sugerido. 
    Ela NÃO atualiza a 'configuracao_financeira' automaticamente. 
    Se desejar usar esse valor, aplique-o via atualizar_configuracao().
    """
    if meses <= 0:
        raise ValueError("A quantidade de meses deve ser maior que zero.")

    data_limite = (datetime.now() - timedelta(days=30 * meses)).isoformat()

    # Busca apenas os itens de vendas realizadas a partir de data_limite
    query = '''
        SELECT SUM(iv.quantidade) 
        FROM item_venda iv
        JOIN venda v ON iv.venda_id = v.id
        WHERE v.data_venda >= ?
    '''
    cursor = conexao.execute(query, (data_limite,))
    resultado = cursor.fetchone()
    
    total_pecas = resultado[0] if resultado and resultado[0] else 0
    
    return total_pecas / meses

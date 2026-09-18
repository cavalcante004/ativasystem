"""
models/produto.py

Operações de negócio sobre a entidade Produto: CRUD completo e ajuste
de estoque, com validação de dados e auditoria.

MODELO AGRUPADO POR SKU:
Duas blusas idênticas (mesma cor/marca/modelo/tamanho) são UM registro
com quantidade_estoque = 2, não dois registros separados. O identificador
único é o codigo_etiqueta (SKU), definido pelo dono da loja.

VALOR DE VENDA:
Nesta fase, o valor_venda é editável manualmente. O motor de precificação
automática (preco_venda = custo_total * (1 + margem)) será implementado
na Fase 2. Por enquanto, o campo existe e o dono da loja preenche como
quiser.

AJUSTE DE ESTOQUE:
A função ajustar_estoque() é a ÚNICA forma correta de alterar a quantidade
em estoque. Ela recebe um delta (positivo para entrada, negativo para saída),
valida que o resultado não fique negativo, e audita a mudança com valor
anterior e novo. Isso garante rastreabilidade total — cada movimentação
de estoque fica registrada no log.
"""

import sqlite3
from typing import Optional

from database.audit import registrar_auditoria


def _validar_dados_produto(
    codigo_etiqueta: str,
    descricao: str,
    valor_compra: float,
    valor_venda: float,
    quantidade_estoque: int = 0,
) -> None:
    """
    Valida os campos obrigatórios do produto antes de INSERT/UPDATE.

    codigo_etiqueta: SKU — não pode ser vazio.
    descricao: descrição do produto — não pode ser vazia.
    valor_compra: custo de aquisição — não pode ser negativo.
    valor_venda: preço de venda — não pode ser negativo.
    quantidade_estoque: não pode ser negativo.
    """
    if not codigo_etiqueta or not codigo_etiqueta.strip():
        raise ValueError(
            "O código de etiqueta (SKU) do produto é obrigatório."
        )

    if not descricao or not descricao.strip():
        raise ValueError("A descrição do produto é obrigatória.")

    if valor_compra < 0:
        raise ValueError(
            f"O valor de compra não pode ser negativo (informado: {valor_compra})."
        )

    if valor_venda < 0:
        raise ValueError(
            f"O valor de venda não pode ser negativo (informado: {valor_venda})."
        )

    if quantidade_estoque < 0:
        raise ValueError(
            f"A quantidade em estoque não pode ser negativa (informado: {quantidade_estoque})."
        )


def criar_produto(
    conexao: sqlite3.Connection,
    codigo_etiqueta: str,
    descricao: str,
    valor_compra: float,
    valor_venda: float,
    usuario: str,
    marca: Optional[str] = None,
    cor: Optional[str] = None,
    tamanho: Optional[str] = None,
    categoria: Optional[str] = None,
    fornecedor_id: Optional[int] = None,
    quantidade_estoque: int = 0,
    data_compra: Optional[str] = None,
) -> int:
    """
    Insere um novo produto no banco e registra na auditoria.

    conexao: conexão sqlite3 (via EncryptedDatabase.open()).
    codigo_etiqueta: SKU — identificador único do produto.
    descricao: descrição legível (ex: "Blusa manga longa").
    valor_compra: custo de aquisição (>= 0).
    valor_venda: preço de venda definido manualmente (>= 0).
    usuario: quem está fazendo a operação (para auditoria).
    marca, cor, tamanho, categoria: atributos opcionais.
    fornecedor_id: FK para a tabela fornecedor (opcional).
    quantidade_estoque: quantidade inicial (padrão 0, >= 0).
    data_compra: data de aquisição em ISO 8601 (opcional).

    Retorna o id do produto criado.
    Levanta ValueError se os dados forem inválidos ou se o codigo_etiqueta
    já existir no banco.
    """
    _validar_dados_produto(
        codigo_etiqueta, descricao, valor_compra, valor_venda, quantidade_estoque
    )

    try:
        cursor = conexao.execute(
            "INSERT INTO produto "
            "(codigo_etiqueta, descricao, marca, cor, tamanho, categoria, "
            "fornecedor_id, valor_compra, valor_venda, quantidade_estoque, "
            "data_compra, data_ultima_venda) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                codigo_etiqueta.strip(),
                descricao.strip(),
                marca,
                cor,
                tamanho,
                categoria,
                fornecedor_id,
                valor_compra,
                valor_venda,
                quantidade_estoque,
                data_compra,
                None,  # data_ultima_venda é sempre nulo nesta fase
            ),
        )
        conexao.commit()
    except sqlite3.IntegrityError as exc:
        erro_msg = str(exc).lower()
        # Diferenciamos o tipo de IntegrityError para dar mensagem específica
        if "unique" in erro_msg or "codigo_etiqueta" in erro_msg:
            raise ValueError(
                f"Já existe um produto cadastrado com o código de etiqueta "
                f"'{codigo_etiqueta}'."
            ) from exc
        # FK inválida (fornecedor_id não existe) ou CHECK constraint
        raise ValueError(
            f"Erro de integridade ao criar produto: {exc}"
        ) from exc

    produto_id = cursor.lastrowid

    registrar_auditoria(
        conexao,
        tabela="produto",
        operacao="INSERT",
        registro_id=produto_id,
        usuario=usuario,
        detalhes={
            "codigo_etiqueta": codigo_etiqueta.strip(),
            "descricao": descricao.strip(),
            "valor_compra": valor_compra,
            "valor_venda": valor_venda,
            "quantidade_estoque": quantidade_estoque,
        },
    )

    return produto_id


def buscar_produto_por_codigo(
    conexao: sqlite3.Connection,
    codigo_etiqueta: str,
) -> Optional[tuple]:
    """
    Busca um produto pelo codigo_etiqueta (SKU).

    Retorna uma tupla com os dados do produto, ou None se não encontrado.
    """
    cursor = conexao.execute(
        "SELECT * FROM produto WHERE codigo_etiqueta = ?",
        (codigo_etiqueta.strip(),),
    )
    return cursor.fetchone()


def buscar_produto_por_id(
    conexao: sqlite3.Connection,
    produto_id: int,
) -> Optional[tuple]:
    """
    Busca um produto pelo id numérico.

    Retorna uma tupla com os dados do produto, ou None se não encontrado.

    Adicionada na Fase 2 para uso pelo motor de precificação, que trabalha
    com ids numéricos (não com codigo_etiqueta).
    """
    cursor = conexao.execute(
        "SELECT * FROM produto WHERE id = ?", (produto_id,)
    )
    return cursor.fetchone()


def listar_produtos(conexao: sqlite3.Connection) -> list[tuple]:
    """
    Lista todos os produtos cadastrados, ordenados pela descrição.

    Retorna lista de tuplas (pode ser vazia).
    """
    cursor = conexao.execute("SELECT * FROM produto ORDER BY descricao")
    return cursor.fetchall()


def atualizar_produto(
    conexao: sqlite3.Connection,
    produto_id: int,
    usuario: str,
    descricao: Optional[str] = None,
    marca: Optional[str] = None,
    cor: Optional[str] = None,
    tamanho: Optional[str] = None,
    categoria: Optional[str] = None,
    fornecedor_id: Optional[int] = None,
    valor_compra: Optional[float] = None,
    valor_venda: Optional[float] = None,
    data_compra: Optional[str] = None,
    data_ultima_venda: Optional[str] = None,
) -> None:
    """
    Atualiza os dados de um produto existente. Só os campos informados
    (não None) são alterados.

    Nota: para alterar quantidade_estoque, use ajustar_estoque().
    Nota: codigo_etiqueta não é editável (é o identificador do SKU).

    Registra na auditoria o valor anterior e o novo de cada campo alterado.

    Levanta ValueError se o produto não existir ou se os dados forem inválidos.
    """
    produto_atual = conexao.execute(
        "SELECT * FROM produto WHERE id = ?", (produto_id,)
    ).fetchone()

    if produto_atual is None:
        raise ValueError(f"Produto com id {produto_id} não encontrado.")

    # Ordem dos campos na tabela:
    # 0:id, 1:codigo_etiqueta, 2:descricao, 3:marca, 4:cor, 5:tamanho,
    # 6:categoria, 7:fornecedor_id, 8:valor_compra, 9:valor_venda,
    # 10:quantidade_estoque, 11:data_compra, 12:data_ultima_venda
    nova_descricao = descricao if descricao is not None else produto_atual[2]
    nova_marca = marca if marca is not None else produto_atual[3]
    nova_cor = cor if cor is not None else produto_atual[4]
    novo_tamanho = tamanho if tamanho is not None else produto_atual[5]
    nova_categoria = categoria if categoria is not None else produto_atual[6]
    novo_fornecedor_id = fornecedor_id if fornecedor_id is not None else produto_atual[7]
    novo_valor_compra = valor_compra if valor_compra is not None else produto_atual[8]
    novo_valor_venda = valor_venda if valor_venda is not None else produto_atual[9]
    nova_data_compra = data_compra if data_compra is not None else produto_atual[11]
    nova_data_ultima_venda = data_ultima_venda if data_ultima_venda is not None else produto_atual[12]

    # Validar com os valores que vão efetivamente para o banco
    _validar_dados_produto(
        produto_atual[1],  # codigo_etiqueta não muda
        nova_descricao,
        novo_valor_compra,
        novo_valor_venda,
        produto_atual[10],  # quantidade_estoque não muda aqui
    )

    conexao.execute(
        "UPDATE produto SET descricao = ?, marca = ?, cor = ?, tamanho = ?, "
        "categoria = ?, fornecedor_id = ?, valor_compra = ?, valor_venda = ?, "
        "data_compra = ?, data_ultima_venda = ? WHERE id = ?",
        (
            nova_descricao.strip() if isinstance(nova_descricao, str) else nova_descricao,
            nova_marca,
            nova_cor,
            novo_tamanho,
            nova_categoria,
            novo_fornecedor_id,
            novo_valor_compra,
            novo_valor_venda,
            nova_data_compra,
            nova_data_ultima_venda,
            produto_id,
        ),
    )
    conexao.commit()

    # Montar detalhes de auditoria com campos que realmente mudaram
    alteracoes = {}
    campos_para_checar = [
        ("descricao", descricao, produto_atual[2]),
        ("marca", marca, produto_atual[3]),
        ("cor", cor, produto_atual[4]),
        ("tamanho", tamanho, produto_atual[5]),
        ("categoria", categoria, produto_atual[6]),
        ("fornecedor_id", fornecedor_id, produto_atual[7]),
        ("valor_compra", valor_compra, produto_atual[8]),
        ("valor_venda", valor_venda, produto_atual[9]),
        ("data_compra", data_compra, produto_atual[11]),
        ("data_ultima_venda", data_ultima_venda, produto_atual[12]),
    ]
    for campo, novo_valor, valor_atual in campos_para_checar:
        if novo_valor is not None and novo_valor != valor_atual:
            alteracoes[campo] = {"de": valor_atual, "para": novo_valor}

    registrar_auditoria(
        conexao,
        tabela="produto",
        operacao="UPDATE",
        registro_id=produto_id,
        usuario=usuario,
        detalhes=alteracoes,
    )


def excluir_produto(
    conexao: sqlite3.Connection,
    produto_id: int,
    usuario: str,
) -> None:
    """
    Exclui um produto pelo id.

    Registra a exclusão na auditoria com os dados do produto removido.

    Levanta ValueError se o produto não existir.
    """
    produto_atual = conexao.execute(
        "SELECT * FROM produto WHERE id = ?", (produto_id,)
    ).fetchone()

    if produto_atual is None:
        raise ValueError(f"Produto com id {produto_id} não encontrado.")

    conexao.execute("DELETE FROM produto WHERE id = ?", (produto_id,))
    conexao.commit()

    registrar_auditoria(
        conexao,
        tabela="produto",
        operacao="DELETE",
        registro_id=produto_id,
        usuario=usuario,
        detalhes={
            "codigo_etiqueta": produto_atual[1],
            "descricao": produto_atual[2],
            "valor_compra": produto_atual[8],
            "valor_venda": produto_atual[9],
            "quantidade_estoque": produto_atual[10],
        },
    )


def ajustar_estoque(
    conexao: sqlite3.Connection,
    produto_id: int,
    quantidade_delta: int,
    usuario: str,
) -> int:
    """
    Altera a quantidade em estoque de um produto somando (ou subtraindo)
    o delta informado.

    conexao: conexão sqlite3 (via EncryptedDatabase.open()).
    produto_id: id do produto.
    quantidade_delta: valor a somar ao estoque atual. Positivo para entrada
                      de mercadoria, negativo para saída (ex: venda, perda).
    usuario: quem está fazendo a operação (para auditoria).

    Retorna a nova quantidade em estoque.

    Levanta ValueError se:
      - O produto não existir.
      - A operação resultaria em estoque negativo (nesse caso, o banco
        NÃO é alterado — a exceção é lançada antes do UPDATE).
    """
    produto = conexao.execute(
        "SELECT id, quantidade_estoque, codigo_etiqueta FROM produto WHERE id = ?",
        (produto_id,),
    ).fetchone()

    if produto is None:
        raise ValueError(f"Produto com id {produto_id} não encontrado.")

    _, estoque_atual, codigo_etiqueta = produto
    novo_estoque = estoque_atual + quantidade_delta

    # Validamos ANTES do UPDATE para garantir que o banco nunca recebe
    # um valor negativo — mesmo que o CHECK constraint do SQLite também
    # impeça, a mensagem de erro do SQLite seria genérica e em inglês.
    if novo_estoque < 0:
        raise ValueError(
            f"Estoque insuficiente para o produto '{codigo_etiqueta}' (id {produto_id}). "
            f"Estoque atual: {estoque_atual}, ajuste solicitado: {quantidade_delta}, "
            f"resultado seria: {novo_estoque}. O estoque não pode ficar negativo."
        )

    conexao.execute(
        "UPDATE produto SET quantidade_estoque = ? WHERE id = ?",
        (novo_estoque, produto_id),
    )
    conexao.commit()

    registrar_auditoria(
        conexao,
        tabela="produto",
        operacao="UPDATE",
        registro_id=produto_id,
        usuario=usuario,
        detalhes={
            "campo": "quantidade_estoque",
            "de": estoque_atual,
            "para": novo_estoque,
            "delta": quantidade_delta,
        },
    )

    return novo_estoque

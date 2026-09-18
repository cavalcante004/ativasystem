"""
models/financeiro.py

Motor de precificação e gestão financeira do sistema de condicional.

FÓRMULA CENTRAL DE PRECIFICAÇÃO:
    custo_total = valor_compra + imposto_estimado + rateio_custo_fixo_por_peca
    preco_venda_sugerido = custo_total * (1 + margem_lucro)

Onde:
    imposto_estimado = valor_compra * percentual_imposto_padrao
    rateio_custo_fixo_por_peca = custo_fixo_mensal / quantidade_estimada_vendas_mes
    custo_fixo_mensal = soma(salario dos funcionarios ativos) + soma(valor das contas recorrentes)

POR QUE UM ÚNICO ARQUIVO:
Configuração financeira, funcionários, contas a pagar e motor de cálculo
pertencem ao mesmo domínio (financeiro). Dividi-los em 4 arquivos criaria
acoplamento circular e tornaria o import graph mais complexo sem ganho
real. Em vez disso, usamos seções comentadas internas.

SIMPLIFICAÇÃO TEMPORÁRIA:
O campo quantidade_estimada_vendas_mes é configurado manualmente pelo
usuário. Quando a Fase 4 (Vendas) for implementada, este número poderá
ser calculado a partir do histórico real de vendas em vez de estimado
manualmente.
"""

import sqlite3
from typing import Optional

from database.audit import registrar_auditoria
from models.produto import buscar_produto_por_id, atualizar_produto


# ===========================================================================
# SEÇÃO 1: Configuração financeira (linha única)
# ===========================================================================

def garantir_configuracao_financeira(
    conexao: sqlite3.Connection,
    margem_lucro_padrao: float = 0.30,
    percentual_imposto_padrao: float = 0.0,
    quantidade_estimada_vendas_mes: int = 1,
) -> None:
    """
    Cria a linha única de configuração financeira SOMENTE se ela ainda
    não existir. Se já existir, não faz nada (idempotente).

    Chamada uma vez na inicialização do banco, após garantir_tabelas_fase2().

    conexao: conexão sqlite3 (via EncryptedDatabase.open()).
    margem_lucro_padrao: margem sobre o custo (0.30 = 30%).
    percentual_imposto_padrao: imposto estimado sobre o valor de compra.
    quantidade_estimada_vendas_mes: estimativa manual de vendas/mês (> 0).
    """
    existente = conexao.execute(
        "SELECT id FROM configuracao_financeira WHERE id = 1"
    ).fetchone()

    if existente is not None:
        return

    conexao.execute(
        "INSERT INTO configuracao_financeira "
        "(id, margem_lucro_padrao, percentual_imposto_padrao, quantidade_estimada_vendas_mes) "
        "VALUES (1, ?, ?, ?)",
        (margem_lucro_padrao, percentual_imposto_padrao, quantidade_estimada_vendas_mes),
    )
    conexao.commit()


def obter_configuracao(conexao: sqlite3.Connection) -> tuple:
    """
    Retorna a configuração financeira atual.

    Formato da tupla: (id, margem_lucro_padrao, percentual_imposto_padrao,
    quantidade_estimada_vendas_mes).

    Levanta ValueError se a configuração não foi inicializada.
    """
    config = conexao.execute(
        "SELECT * FROM configuracao_financeira WHERE id = 1"
    ).fetchone()

    if config is None:
        raise ValueError(
            "Configuração financeira não encontrada. "
            "Chame garantir_configuracao_financeira() na inicialização do banco."
        )
    return config


def atualizar_configuracao(
    conexao: sqlite3.Connection,
    usuario: str,
    margem_lucro_padrao: Optional[float] = None,
    percentual_imposto_padrao: Optional[float] = None,
    quantidade_estimada_vendas_mes: Optional[int] = None,
) -> None:
    """
    Atualiza os parâmetros da configuração financeira. Só os campos
    informados (não None) são alterados.

    Validações (mesmos CHECKs do schema, em Python com mensagem clara):
    - margem_lucro_padrao >= 0
    - percentual_imposto_padrao >= 0
    - quantidade_estimada_vendas_mes > 0 (protege contra divisão por zero)

    conexao: conexão sqlite3.
    usuario: quem está fazendo a alteração (para auditoria).

    Levanta ValueError se algum valor for inválido.
    """
    config_atual = obter_configuracao(conexao)
    # Ordem: id, margem_lucro_padrao, percentual_imposto_padrao, quantidade_estimada_vendas_mes
    _, margem_atual, imposto_atual, qtd_atual = config_atual

    nova_margem = margem_lucro_padrao if margem_lucro_padrao is not None else margem_atual
    novo_imposto = percentual_imposto_padrao if percentual_imposto_padrao is not None else imposto_atual
    nova_qtd = quantidade_estimada_vendas_mes if quantidade_estimada_vendas_mes is not None else qtd_atual

    # Validações com mensagem clara em português
    if nova_margem < 0:
        raise ValueError(
            f"A margem de lucro não pode ser negativa (informado: {nova_margem})."
        )
    if novo_imposto < 0:
        raise ValueError(
            f"O percentual de imposto não pode ser negativo (informado: {novo_imposto})."
        )
    if nova_qtd <= 0:
        raise ValueError(
            f"A quantidade estimada de vendas por mês deve ser maior que zero "
            f"(informado: {nova_qtd}). Valor zero causaria divisão por zero no "
            f"cálculo de rateio de custo fixo."
        )

    conexao.execute(
        "UPDATE configuracao_financeira SET margem_lucro_padrao = ?, "
        "percentual_imposto_padrao = ?, quantidade_estimada_vendas_mes = ? "
        "WHERE id = 1",
        (nova_margem, novo_imposto, nova_qtd),
    )
    conexao.commit()

    # Auditoria: registrar apenas os campos que realmente mudaram
    alteracoes = {}
    if margem_lucro_padrao is not None and margem_lucro_padrao != margem_atual:
        alteracoes["margem_lucro_padrao"] = {"de": margem_atual, "para": margem_lucro_padrao}
    if percentual_imposto_padrao is not None and percentual_imposto_padrao != imposto_atual:
        alteracoes["percentual_imposto_padrao"] = {"de": imposto_atual, "para": percentual_imposto_padrao}
    if quantidade_estimada_vendas_mes is not None and quantidade_estimada_vendas_mes != qtd_atual:
        alteracoes["quantidade_estimada_vendas_mes"] = {"de": qtd_atual, "para": quantidade_estimada_vendas_mes}

    registrar_auditoria(
        conexao,
        tabela="configuracao_financeira",
        operacao="UPDATE",
        registro_id=1,
        usuario=usuario,
        detalhes=alteracoes,
    )


# ===========================================================================
# SEÇÃO 2: Funcionários
# ===========================================================================

def criar_funcionario(
    conexao: sqlite3.Connection,
    nome: str,
    salario: float,
    usuario: str,
) -> int:
    """
    Insere um novo funcionário (ativo por padrão).

    conexao: conexão sqlite3.
    nome: nome do funcionário — não pode ser vazio.
    salario: salário mensal — não pode ser negativo.
    usuario: quem está fazendo a operação (para auditoria).

    Retorna o id do funcionário criado.
    """
    if not nome or not nome.strip():
        raise ValueError("O nome do funcionário é obrigatório.")
    if salario < 0:
        raise ValueError(
            f"O salário não pode ser negativo (informado: {salario})."
        )

    cursor = conexao.execute(
        "INSERT INTO funcionario (nome, salario) VALUES (?, ?)",
        (nome.strip(), salario),
    )
    conexao.commit()

    funcionario_id = cursor.lastrowid

    registrar_auditoria(
        conexao,
        tabela="funcionario",
        operacao="INSERT",
        registro_id=funcionario_id,
        usuario=usuario,
        detalhes={"nome": nome.strip(), "salario": salario, "ativo": 1},
    )

    return funcionario_id


def _buscar_funcionario_por_id(
    conexao: sqlite3.Connection,
    funcionario_id: int,
) -> tuple:
    """
    Busca um funcionário pelo id. Uso interno — levanta ValueError se
    não encontrado (evita repetir essa checagem em cada função pública).

    Ordem da tupla: id, nome, salario, ativo.
    """
    funcionario = conexao.execute(
        "SELECT * FROM funcionario WHERE id = ?", (funcionario_id,)
    ).fetchone()

    if funcionario is None:
        raise ValueError(f"Funcionário com id {funcionario_id} não encontrado.")

    return funcionario


def listar_funcionarios(
    conexao: sqlite3.Connection,
    somente_ativos: bool = True,
) -> list[tuple]:
    """
    Lista funcionários cadastrados.

    somente_ativos: se True (padrão), retorna apenas funcionários com ativo=1.
                    Se False, retorna todos (ativos e inativos).

    Retorna lista de tuplas ordenada por nome.
    """
    if somente_ativos:
        cursor = conexao.execute(
            "SELECT * FROM funcionario WHERE ativo = 1 ORDER BY nome"
        )
    else:
        cursor = conexao.execute("SELECT * FROM funcionario ORDER BY nome")
    return cursor.fetchall()


def atualizar_funcionario(
    conexao: sqlite3.Connection,
    funcionario_id: int,
    usuario: str,
    nome: Optional[str] = None,
    salario: Optional[float] = None,
) -> None:
    """
    Atualiza nome e/ou salário de um funcionário. Só os campos informados
    (não None) são alterados.

    Levanta ValueError se o funcionário não existir ou se os dados forem inválidos.
    """
    funcionario_atual = _buscar_funcionario_por_id(conexao, funcionario_id)
    _, nome_atual, salario_atual, _ = funcionario_atual

    novo_nome = nome if nome is not None else nome_atual
    novo_salario = salario if salario is not None else salario_atual

    if not novo_nome or not novo_nome.strip():
        raise ValueError("O nome do funcionário é obrigatório.")
    if novo_salario < 0:
        raise ValueError(
            f"O salário não pode ser negativo (informado: {novo_salario})."
        )

    conexao.execute(
        "UPDATE funcionario SET nome = ?, salario = ? WHERE id = ?",
        (novo_nome.strip(), novo_salario, funcionario_id),
    )
    conexao.commit()

    alteracoes = {}
    if nome is not None and nome.strip() != nome_atual:
        alteracoes["nome"] = {"de": nome_atual, "para": nome.strip()}
    if salario is not None and salario != salario_atual:
        alteracoes["salario"] = {"de": salario_atual, "para": salario}

    registrar_auditoria(
        conexao,
        tabela="funcionario",
        operacao="UPDATE",
        registro_id=funcionario_id,
        usuario=usuario,
        detalhes=alteracoes,
    )


def desligar_funcionario(
    conexao: sqlite3.Connection,
    funcionario_id: int,
    usuario: str,
) -> None:
    """
    Desliga um funcionário (seta ativo=0). NÃO exclui do banco — preserva
    o histórico para auditoria e relatórios futuros.

    Levanta ValueError se o funcionário não existir ou já estiver inativo.
    """
    funcionario = _buscar_funcionario_por_id(conexao, funcionario_id)
    _, nome, _, ativo = funcionario

    if ativo == 0:
        raise ValueError(
            f"O funcionário '{nome}' (id {funcionario_id}) já está desligado."
        )

    conexao.execute(
        "UPDATE funcionario SET ativo = 0 WHERE id = ?", (funcionario_id,)
    )
    conexao.commit()

    registrar_auditoria(
        conexao,
        tabela="funcionario",
        operacao="UPDATE",
        registro_id=funcionario_id,
        usuario=usuario,
        detalhes={"ativo": {"de": 1, "para": 0}, "acao": "desligamento"},
    )


def reativar_funcionario(
    conexao: sqlite3.Connection,
    funcionario_id: int,
    usuario: str,
) -> None:
    """
    Reativa um funcionário previamente desligado (seta ativo=1).

    Levanta ValueError se o funcionário não existir ou já estiver ativo.
    """
    funcionario = _buscar_funcionario_por_id(conexao, funcionario_id)
    _, nome, _, ativo = funcionario

    if ativo == 1:
        raise ValueError(
            f"O funcionário '{nome}' (id {funcionario_id}) já está ativo."
        )

    conexao.execute(
        "UPDATE funcionario SET ativo = 1 WHERE id = ?", (funcionario_id,)
    )
    conexao.commit()

    registrar_auditoria(
        conexao,
        tabela="funcionario",
        operacao="UPDATE",
        registro_id=funcionario_id,
        usuario=usuario,
        detalhes={"ativo": {"de": 0, "para": 1}, "acao": "reativacao"},
    )


# ===========================================================================
# SEÇÃO 3: Contas a pagar
# ===========================================================================

def criar_conta_a_pagar(
    conexao: sqlite3.Connection,
    descricao: str,
    valor: float,
    vencimento: str,
    usuario: str,
    recorrente: bool = False,
) -> int:
    """
    Insere uma nova conta a pagar.

    conexao: conexão sqlite3.
    descricao: descrição da conta — não pode ser vazia.
    valor: valor da conta — não pode ser negativo.
    vencimento: data de vencimento em ISO 8601 — não pode ser vazio.
    usuario: quem está fazendo a operação (para auditoria).
    recorrente: se True, a conta entra no cálculo de custo fixo mensal.

    Retorna o id da conta criada.
    """
    if not descricao or not descricao.strip():
        raise ValueError("A descrição da conta é obrigatória.")
    if valor < 0:
        raise ValueError(
            f"O valor da conta não pode ser negativo (informado: {valor})."
        )
    if not vencimento or not vencimento.strip():
        raise ValueError("A data de vencimento é obrigatória.")

    recorrente_int = 1 if recorrente else 0

    cursor = conexao.execute(
        "INSERT INTO conta_a_pagar (descricao, valor, vencimento, recorrente) "
        "VALUES (?, ?, ?, ?)",
        (descricao.strip(), valor, vencimento.strip(), recorrente_int),
    )
    conexao.commit()

    conta_id = cursor.lastrowid

    registrar_auditoria(
        conexao,
        tabela="conta_a_pagar",
        operacao="INSERT",
        registro_id=conta_id,
        usuario=usuario,
        detalhes={
            "descricao": descricao.strip(),
            "valor": valor,
            "vencimento": vencimento.strip(),
            "recorrente": recorrente_int,
        },
    )

    return conta_id


def _buscar_conta_por_id(
    conexao: sqlite3.Connection,
    conta_id: int,
) -> tuple:
    """
    Busca uma conta a pagar pelo id. Uso interno — levanta ValueError
    se não encontrada.

    Ordem da tupla: id, descricao, valor, vencimento, status, recorrente.
    """
    conta = conexao.execute(
        "SELECT * FROM conta_a_pagar WHERE id = ?", (conta_id,)
    ).fetchone()

    if conta is None:
        raise ValueError(f"Conta a pagar com id {conta_id} não encontrada.")

    return conta


def listar_contas_a_pagar(
    conexao: sqlite3.Connection,
    apenas_pendentes: bool = False,
) -> list[tuple]:
    """
    Lista contas a pagar cadastradas.

    apenas_pendentes: se True, retorna apenas contas com status='pendente'.
                      Se False (padrão), retorna todas.

    Retorna lista de tuplas ordenada por vencimento.
    """
    if apenas_pendentes:
        cursor = conexao.execute(
            "SELECT * FROM conta_a_pagar WHERE status = 'pendente' ORDER BY vencimento"
        )
    else:
        cursor = conexao.execute("SELECT * FROM conta_a_pagar ORDER BY vencimento")
    return cursor.fetchall()


def marcar_conta_como_paga(
    conexao: sqlite3.Connection,
    conta_id: int,
    usuario: str,
) -> None:
    """
    Marca uma conta a pagar como 'paga'.

    Levanta ValueError se a conta não existir ou já estiver paga.
    """
    conta = _buscar_conta_por_id(conexao, conta_id)
    _, descricao, _, _, status, _ = conta

    if status == "paga":
        raise ValueError(
            f"A conta '{descricao}' (id {conta_id}) já está marcada como paga."
        )

    conexao.execute(
        "UPDATE conta_a_pagar SET status = 'paga' WHERE id = ?", (conta_id,)
    )
    conexao.commit()

    registrar_auditoria(
        conexao,
        tabela="conta_a_pagar",
        operacao="UPDATE",
        registro_id=conta_id,
        usuario=usuario,
        detalhes={"status": {"de": "pendente", "para": "paga"}},
    )


def atualizar_conta_a_pagar(
    conexao: sqlite3.Connection,
    conta_id: int,
    usuario: str,
    descricao: Optional[str] = None,
    valor: Optional[float] = None,
    vencimento: Optional[str] = None,
    recorrente: Optional[bool] = None,
) -> None:
    """
    Atualiza os dados de uma conta a pagar existente. Só os campos
    informados (não None) são alterados.

    Levanta ValueError se a conta não existir ou se os dados forem inválidos.
    """
    conta_atual = _buscar_conta_por_id(conexao, conta_id)
    # Ordem: id, descricao, valor, vencimento, status, recorrente
    _, desc_atual, valor_atual, venc_atual, _, recorrente_atual = conta_atual

    nova_desc = descricao if descricao is not None else desc_atual
    novo_valor = valor if valor is not None else valor_atual
    novo_venc = vencimento if vencimento is not None else venc_atual
    novo_recorrente = (1 if recorrente else 0) if recorrente is not None else recorrente_atual

    if not nova_desc or not nova_desc.strip():
        raise ValueError("A descrição da conta é obrigatória.")
    if novo_valor < 0:
        raise ValueError(
            f"O valor da conta não pode ser negativo (informado: {novo_valor})."
        )
    if not novo_venc or not novo_venc.strip():
        raise ValueError("A data de vencimento é obrigatória.")

    conexao.execute(
        "UPDATE conta_a_pagar SET descricao = ?, valor = ?, vencimento = ?, recorrente = ? "
        "WHERE id = ?",
        (nova_desc.strip(), novo_valor, novo_venc.strip(), novo_recorrente, conta_id),
    )
    conexao.commit()

    alteracoes = {}
    if descricao is not None and descricao.strip() != desc_atual:
        alteracoes["descricao"] = {"de": desc_atual, "para": descricao.strip()}
    if valor is not None and valor != valor_atual:
        alteracoes["valor"] = {"de": valor_atual, "para": valor}
    if vencimento is not None and vencimento.strip() != venc_atual:
        alteracoes["vencimento"] = {"de": venc_atual, "para": vencimento.strip()}
    if recorrente is not None and novo_recorrente != recorrente_atual:
        alteracoes["recorrente"] = {"de": recorrente_atual, "para": novo_recorrente}

    registrar_auditoria(
        conexao,
        tabela="conta_a_pagar",
        operacao="UPDATE",
        registro_id=conta_id,
        usuario=usuario,
        detalhes=alteracoes,
    )


def excluir_conta_a_pagar(
    conexao: sqlite3.Connection,
    conta_id: int,
    usuario: str,
) -> None:
    """
    Exclui uma conta a pagar pelo id.

    Levanta ValueError se a conta não existir.
    """
    conta_atual = _buscar_conta_por_id(conexao, conta_id)
    _, descricao, valor, vencimento, status, recorrente = conta_atual

    conexao.execute("DELETE FROM conta_a_pagar WHERE id = ?", (conta_id,))
    conexao.commit()

    registrar_auditoria(
        conexao,
        tabela="conta_a_pagar",
        operacao="DELETE",
        registro_id=conta_id,
        usuario=usuario,
        detalhes={
            "descricao": descricao,
            "valor": valor,
            "vencimento": vencimento,
            "status": status,
            "recorrente": recorrente,
        },
    )


# ===========================================================================
# SEÇÃO 4: Motor de cálculo (núcleo da Fase 2)
# ===========================================================================

def calcular_custo_fixo_mensal(conexao: sqlite3.Connection) -> float:
    """
    Calcula o custo fixo mensal total do negócio.

    Composto por:
    1. Soma dos salários de todos os funcionários ATIVOS (ativo=1)
    2. Soma dos valores de todas as contas a pagar RECORRENTES (recorrente=1),
       independente do status (paga ou pendente) — uma conta recorrente
       representa um custo fixo que existe todo mês.

    Retorna o valor total (float). Retorna 0.0 se não houver funcionários
    nem contas recorrentes.
    """
    # COALESCE garante retorno 0.0 quando não há registros (evita None)
    soma_salarios = conexao.execute(
        "SELECT COALESCE(SUM(salario), 0.0) FROM funcionario WHERE ativo = 1"
    ).fetchone()[0]

    soma_contas_recorrentes = conexao.execute(
        "SELECT COALESCE(SUM(valor), 0.0) FROM conta_a_pagar WHERE recorrente = 1"
    ).fetchone()[0]

    return soma_salarios + soma_contas_recorrentes


def calcular_rateio_por_peca(conexao: sqlite3.Connection) -> float:
    """
    Calcula o rateio de custo fixo por peça vendida.

    Fórmula: custo_fixo_mensal / quantidade_estimada_vendas_mes

    A divisão por zero é impossível aqui porque quantidade_estimada_vendas_mes
    tem CHECK > 0 no banco E validação Python em atualizar_configuracao().

    Retorna o valor do rateio por peça (float).
    """
    custo_fixo = calcular_custo_fixo_mensal(conexao)
    config = obter_configuracao(conexao)
    qtd_estimada = config[3]  # quantidade_estimada_vendas_mes

    return custo_fixo / qtd_estimada


def calcular_preco_sugerido(
    conexao: sqlite3.Connection,
    produto_id: int,
) -> dict:
    """
    Calcula o preço de venda sugerido para um produto, detalhando cada
    componente da fórmula.

    O detalhamento (não só o número final) permite ao dono do sistema
    entender de onde veio o preço, em vez de receber um número "mágico".

    conexao: conexão sqlite3.
    produto_id: id numérico do produto.

    Retorna um dicionário com:
        produto_id, valor_compra, imposto_estimado, rateio_custo_fixo,
        custo_total, margem_lucro, preco_sugerido.

    Levanta ValueError se o produto não existir.
    """
    produto = buscar_produto_por_id(conexao, produto_id)
    if produto is None:
        raise ValueError(f"Produto com id {produto_id} não encontrado.")

    # Ordem dos campos do produto:
    # 0:id, 1:codigo_etiqueta, 2:descricao, 3:marca, 4:cor, 5:tamanho,
    # 6:categoria, 7:fornecedor_id, 8:valor_compra, 9:valor_venda, ...
    valor_compra = produto[8]

    config = obter_configuracao(conexao)
    margem_lucro = config[1]           # margem_lucro_padrao
    percentual_imposto = config[2]     # percentual_imposto_padrao

    imposto_estimado = valor_compra * percentual_imposto
    rateio_custo_fixo = calcular_rateio_por_peca(conexao)
    custo_total = valor_compra + imposto_estimado + rateio_custo_fixo
    preco_sugerido = custo_total * (1 + margem_lucro)

    return {
        "produto_id": produto_id,
        "valor_compra": valor_compra,
        "imposto_estimado": round(imposto_estimado, 2),
        "rateio_custo_fixo": round(rateio_custo_fixo, 2),
        "custo_total": round(custo_total, 2),
        "margem_lucro": margem_lucro,
        "preco_sugerido": round(preco_sugerido, 2),
    }


def aplicar_preco_sugerido(
    conexao: sqlite3.Connection,
    produto_id: int,
    usuario: str,
) -> float:
    """
    Calcula o preço sugerido para um produto e aplica como novo valor_venda.

    Reaproveita atualizar_produto() de models.produto para gravar e auditar
    a mudança — não duplica lógica de auditoria.

    conexao: conexão sqlite3.
    produto_id: id numérico do produto.
    usuario: quem está fazendo a operação (para auditoria).

    Retorna o preço aplicado (float).
    """
    resultado = calcular_preco_sugerido(conexao, produto_id)
    preco = resultado["preco_sugerido"]

    # atualizar_produto já valida, grava e audita a mudança
    atualizar_produto(conexao, produto_id, usuario, valor_venda=preco)

    return preco

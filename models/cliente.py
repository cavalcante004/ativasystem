"""
models/cliente.py

Operações de negócio sobre a entidade Cliente: criação, consulta,
atualização e exclusão, com validação de dados e auditoria.

POR QUE FUNÇÕES SOLTAS E NÃO UMA CLASSE:
Cada função recebe a conexão como parâmetro e faz UMA coisa. Isso mantém
a responsabilidade única clara e torna os testes triviais — basta passar
uma conexão de teste. Uma classe "GerenciadorDeCliente" adicionaria estado
sem ganho real, já que o estado está no banco, não na memória.

POR QUE AS VALIDAÇÕES FICAM AQUI E NÃO NO BANCO:
O banco impõe restrições de integridade (UNIQUE, NOT NULL), mas mensagens
de erro do SQLite são genéricas e em inglês. As validações aqui servem
para dar feedback claro em português ANTES de tentar o INSERT/UPDATE,
e para tratar os erros do banco (IntegrityError) com mensagens amigáveis.
"""

import re
import sqlite3
from datetime import datetime
from typing import Optional

from database.audit import registrar_auditoria
from models.endereco import listar_enderecos_do_cliente


def _normalizar_cpf(cpf: Optional[str]) -> Optional[str]:
    """
    Remove pontuação do CPF (pontos e traço) e retorna só os 11 dígitos.

    Retorna None se o CPF não foi informado ou é vazio.
    Levanta ValueError se, após remover pontuação, o resultado não tiver
    exatamente 11 dígitos numéricos.

    POR QUE NORMALIZAR ANTES DE GRAVAR:
    O campo CPF no banco tem constraint UNIQUE. Se gravarmos o valor bruto
    (ex: "123.456.789-01"), ele não colide com "12345678901" — são strings
    diferentes para o SQLite, mesmo sendo o mesmo CPF. Normalizando aqui,
    garantimos que toda comparação e gravação usa o mesmo formato.
    """
    if cpf is None or cpf.strip() == "":
        return None

    cpf_limpo = re.sub(r"[.\-]", "", cpf.strip())
    if not re.fullmatch(r"\d{11}", cpf_limpo):
        raise ValueError(
            f"O CPF informado ('{cpf}') deve conter exatamente 11 dígitos numéricos."
        )
    return cpf_limpo


def _validar_dados_cliente(
    nome: str,
    telefone: str,
    cpf: Optional[str] = None,
) -> None:
    """
    Valida os campos obrigatórios do cliente antes de qualquer operação
    no banco. Levanta ValueError com mensagem em português se algo estiver
    errado.

    nome: deve ter pelo menos 2 caracteres (não vazio).
    telefone: não pode ser vazio.
    cpf: se informado, deve conter exatamente 11 dígitos numéricos.
         Não validamos dígito verificador — só formato.
         A validação de formato do CPF é delegada para _normalizar_cpf().
    """
    if not nome or len(nome.strip()) < 2:
        raise ValueError(
            "O nome do cliente deve ter pelo menos 2 caracteres."
        )

    if not telefone or not telefone.strip():
        raise ValueError(
            "O telefone do cliente é obrigatório e não pode ser vazio."
        )

    # Validação de formato do CPF (levanta ValueError se inválido)
    _normalizar_cpf(cpf)


def criar_cliente(
    conexao: sqlite3.Connection,
    nome: str,
    telefone: str,
    usuario: str,
    cpf: Optional[str] = None,
    observacoes: Optional[str] = None,
) -> int:
    """
    Insere um novo cliente no banco e registra a operação na auditoria.

    conexao: conexão sqlite3 (via EncryptedDatabase.open()).
    nome: nome completo do cliente.
    telefone: telefone de contato.
    usuario: identificação de quem está realizando a operação (para auditoria).
    cpf: opcional — se informado, deve ter 11 dígitos e ser único no banco.
    observacoes: campo livre para anotações.

    Retorna o id do cliente criado.
    Levanta ValueError se os dados forem inválidos ou se o CPF já existir.
    """
    _validar_dados_cliente(nome, telefone, cpf)

    # Normaliza o CPF para gravar sempre no formato limpo (só dígitos),
    # garantindo que o UNIQUE do banco funcione independente da formatação
    # que o usuário digitou.
    cpf_normalizado = _normalizar_cpf(cpf)

    data_cadastro = datetime.now().isoformat(timespec="seconds")

    try:
        cursor = conexao.execute(
            "INSERT INTO cliente (nome, telefone, cpf, data_cadastro, observacoes) "
            "VALUES (?, ?, ?, ?, ?)",
            (nome.strip(), telefone.strip(), cpf_normalizado, data_cadastro, observacoes),
        )
        conexao.commit()
    except sqlite3.IntegrityError as exc:
        # O UNIQUE no campo cpf é a causa mais provável aqui.
        raise ValueError(
            f"Já existe um cliente cadastrado com o CPF '{cpf}'."
        ) from exc

    cliente_id = cursor.lastrowid

    registrar_auditoria(
        conexao,
        tabela="cliente",
        operacao="INSERT",
        registro_id=cliente_id,
        usuario=usuario,
        detalhes={"nome": nome.strip(), "telefone": telefone.strip(), "cpf": cpf_normalizado},
    )

    return cliente_id


def buscar_cliente_por_id(
    conexao: sqlite3.Connection,
    cliente_id: int,
) -> Optional[tuple]:
    """
    Busca um cliente pelo id.

    Retorna uma tupla com os dados do cliente, ou None se não encontrado.
    """
    cursor = conexao.execute(
        "SELECT * FROM cliente WHERE id = ?", (cliente_id,)
    )
    return cursor.fetchone()


def listar_clientes(conexao: sqlite3.Connection) -> list[tuple]:
    """
    Lista todos os clientes cadastrados, ordenados por nome.

    Retorna uma lista de tuplas (pode ser vazia se não houver clientes).
    """
    cursor = conexao.execute("SELECT * FROM cliente ORDER BY nome")
    return cursor.fetchall()


def atualizar_cliente(
    conexao: sqlite3.Connection,
    cliente_id: int,
    usuario: str,
    nome: Optional[str] = None,
    telefone: Optional[str] = None,
    cpf: Optional[str] = None,
    observacoes: Optional[str] = None,
) -> None:
    """
    Atualiza os dados de um cliente existente. Só os campos informados
    (não None) são alterados — os demais permanecem como estão.

    Registra na auditoria o valor anterior e o novo de cada campo alterado.

    Levanta ValueError se o cliente não existir ou se os dados forem inválidos.
    """
    cliente_atual = buscar_cliente_por_id(conexao, cliente_id)
    if cliente_atual is None:
        raise ValueError(f"Cliente com id {cliente_id} não encontrado.")

    # Desempacotar os campos atuais para comparação na auditoria
    # Ordem: id, nome, telefone, cpf, data_cadastro, observacoes
    _, nome_atual, telefone_atual, cpf_atual, _, observacoes_atual = cliente_atual

    # Usar valores atuais como fallback para campos não informados
    novo_nome = nome if nome is not None else nome_atual
    novo_telefone = telefone if telefone is not None else telefone_atual
    novo_cpf = cpf if cpf is not None else cpf_atual
    novas_observacoes = observacoes if observacoes is not None else observacoes_atual

    _validar_dados_cliente(novo_nome, novo_telefone, novo_cpf)

    # Normaliza o CPF antes de gravar, pelo mesmo motivo que em criar_cliente
    novo_cpf_normalizado = _normalizar_cpf(novo_cpf)

    try:
        conexao.execute(
            "UPDATE cliente SET nome = ?, telefone = ?, cpf = ?, observacoes = ? "
            "WHERE id = ?",
            (novo_nome.strip(), novo_telefone.strip(), novo_cpf_normalizado, novas_observacoes, cliente_id),
        )
        conexao.commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError(
            f"Já existe um cliente cadastrado com o CPF '{novo_cpf}'."
        ) from exc

    # Montar detalhes de auditoria: só os campos que realmente mudaram
    alteracoes = {}
    if nome is not None and nome.strip() != nome_atual:
        alteracoes["nome"] = {"de": nome_atual, "para": nome.strip()}
    if telefone is not None and telefone.strip() != telefone_atual:
        alteracoes["telefone"] = {"de": telefone_atual, "para": telefone.strip()}
    if novo_cpf_normalizado != cpf_atual:
        alteracoes["cpf"] = {"de": cpf_atual, "para": novo_cpf_normalizado}
    if observacoes is not None and observacoes != observacoes_atual:
        alteracoes["observacoes"] = {"de": observacoes_atual, "para": observacoes}

    registrar_auditoria(
        conexao,
        tabela="cliente",
        operacao="UPDATE",
        registro_id=cliente_id,
        usuario=usuario,
        detalhes=alteracoes,
    )


def excluir_cliente(
    conexao: sqlite3.Connection,
    cliente_id: int,
    usuario: str,
) -> None:
    """
    Exclui um cliente pelo id. Os endereços associados são excluídos
    automaticamente pelo ON DELETE CASCADE definido no schema.

    Registra a exclusão na auditoria com os dados do cliente removido
    E de cada endereço que será removido em cascata — porque o CASCADE
    do SQLite apaga os endereços por baixo, sem passar pela função
    excluir_endereco(), então a auditoria precisa ser feita aqui.

    Levanta ValueError se o cliente não existir.
    """
    cliente_atual = buscar_cliente_por_id(conexao, cliente_id)
    if cliente_atual is None:
        raise ValueError(f"Cliente com id {cliente_id} não encontrado.")

    _, nome, telefone, cpf, data_cadastro, observacoes = cliente_atual

    # Auditar os endereços ANTES do DELETE, porque o CASCADE vai apagá-los
    # e depois não teremos mais os dados para registrar.
    # Ordem: id, cliente_id, logradouro, numero, bairro, cidade, referencia, principal
    enderecos_do_cliente = listar_enderecos_do_cliente(conexao, cliente_id)
    for endereco in enderecos_do_cliente:
        registrar_auditoria(
            conexao,
            tabela="endereco",
            operacao="DELETE",
            registro_id=endereco[0],
            usuario=usuario,
            detalhes={
                "cliente_id": cliente_id,
                "logradouro": endereco[2],
                "cidade": endereco[5],
                "motivo": "exclusão em cascata do cliente",
            },
        )

    conexao.execute("DELETE FROM cliente WHERE id = ?", (cliente_id,))
    conexao.commit()

    registrar_auditoria(
        conexao,
        tabela="cliente",
        operacao="DELETE",
        registro_id=cliente_id,
        usuario=usuario,
        detalhes={"nome": nome, "telefone": telefone, "cpf": cpf},
    )

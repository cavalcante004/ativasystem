"""
database/connection.py

Camada de acesso ao banco de dados com criptografia EM REPOUSO.

CONCEITO (por que isso existe):
Um arquivo .db do SQLite comum é texto/binário legível por qualquer
programa que souber abri-lo. Se alguém copiar o arquivo do computador,
lê os dados de cliente, telefone, endereço e financeiro sem esforço.

ESTRATÉGIA:
O arquivo em disco NUNCA fica decifrado permanentemente. O fluxo é:

    1. open()  -> decifra o conteúdo para um arquivo temporário
    2. o programa usa esse arquivo temporário normalmente (é um SQLite comum)
    3. close() -> recriptografa o conteúdo e apaga o arquivo temporário
                  de forma segura (sobrescrevendo os bytes antes de excluir)

Optamos por criptografar o arquivo inteiro (em vez de usar SQLCipher)
porque SQLCipher exige uma biblioteca nativa (DLL) que complica bastante
a distribuição do .exe final via PyInstaller no Windows. Esta abordagem
usa só Python puro + a biblioteca `cryptography`, o que empacota sem dor.
"""

import os
import sqlite3
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class EncryptedDatabase:
    """
    Representa uma conexão com um banco SQLite que vive criptografado em disco.

    Uso típico:
        db = EncryptedDatabase("dados/loja.db.enc", chave)
        conexao = db.open()
        # ... usa a conexao normalmente (cursor, execute, commit) ...
        db.close()
    """

    def __init__(self, encrypted_path: str, key: bytes):
        """
        encrypted_path: caminho do arquivo criptografado no disco.
        key: chave Fernet (32 bytes, urlsafe-base64). Gerada a partir
             da senha mestra do usuário — ver utils/security.py.
        """
        self.encrypted_path = Path(encrypted_path)
        self.fernet = Fernet(key)
        self._temp_path: Path | None = None
        self._connection: sqlite3.Connection | None = None

    def open(self) -> sqlite3.Connection:
        """
        Decifra o banco existente (se houver) para um arquivo temporário
        e retorna uma conexão sqlite3 normal apontando para ele.

        Se o arquivo criptografado ainda não existir, cria um banco novo
        vazio — é o caso do primeiro uso do aplicativo.
        """
        fd, temp_path_str = tempfile.mkstemp(suffix=".db", prefix="condicional_")
        os.close(fd)  # só precisamos do caminho, sqlite3 abre o arquivo sozinho
        self._temp_path = Path(temp_path_str)

        if self.encrypted_path.exists():
            encrypted_bytes = self.encrypted_path.read_bytes()
            try:
                decrypted_bytes = self.fernet.decrypt(encrypted_bytes)
            except InvalidToken as exc:
                # Senha errada ou arquivo corrompido/adulterado.
                # Nunca abrir um banco "quase certo" — falha alto e claro.
                raise ValueError(
                    "Não foi possível decifrar o banco de dados. "
                    "Senha incorreta ou arquivo corrompido."
                ) from exc
            self._temp_path.write_bytes(decrypted_bytes)
        # Se não existir, o arquivo temporário fica vazio — sqlite3 o
        # inicializa como um banco novo no primeiro CREATE TABLE.

        self._connection = sqlite3.connect(str(self._temp_path))
        self._connection.execute("PRAGMA foreign_keys = ON")
        return self._connection

    def close(self) -> None:
        """
        Fecha a conexão, recriptografa o conteúdo atual do banco e
        apaga o arquivo temporário de forma segura.

        Deve ser chamado sempre ao encerrar o programa (ou em um
        bloco try/finally) — se não for chamado, o arquivo temporário
        decifrado pode ficar esquecido no disco.
        """
        if self._connection is not None:
            self._connection.commit()
            self._connection.close()
            self._connection = None

        if self._temp_path is not None and self._temp_path.exists():
            plain_bytes = self._temp_path.read_bytes()
            encrypted_bytes = self.fernet.encrypt(plain_bytes)

            self.encrypted_path.parent.mkdir(parents=True, exist_ok=True)
            self.encrypted_path.write_bytes(encrypted_bytes)

            self._secure_delete(self._temp_path)
            self._temp_path = None

    @staticmethod
    def _secure_delete(path: Path) -> None:
        """
        Sobrescreve o conteúdo do arquivo com bytes aleatórios antes de
        excluí-lo. Isso evita que os dados decifrados fiquem recuperáveis
        no disco por ferramentas de recuperação de arquivo após o delete.
        """
        length = path.stat().st_size
        with open(path, "ba+", buffering=0) as f:
            f.seek(0)
            f.write(os.urandom(length))
        path.unlink()

    def __enter__(self) -> sqlite3.Connection:
        """Permite usar 'with EncryptedDatabase(...) as conexao:'."""
        return self.open()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

"""
utils/security.py

Autenticação da senha mestra do aplicativo, e derivação da chave usada
para criptografar o banco de dados.

DUAS RESPONSABILIDADES DIFERENTES AQUI (não confundir uma com a outra):

1. Verificar se a senha digitada está correta
   -> usamos Argon2 (hash de senha), que é feito para ISSO e nada mais.
      Um hash Argon2 não pode ser "revertido" para descobrir a chave.

2. Gerar a chave de criptografia do banco a partir da senha
   -> usamos PBKDF2 (derivação de chave), um algoritmo diferente,
      próprio para transformar "senha que uma pessoa digita" em
      "chave de 32 bytes que um algoritmo de criptografia exige".

Por que dois algoritmos diferentes para a mesma senha? Porque servem
a propósitos distintos: Argon2 quer ser LENTO e resistente a ataque de
força bruta na hora de VERIFICAR; PBKDF2 aqui quer ser DETERMINÍSTICO
(a mesma senha sempre gera a mesma chave, senão não conseguimos abrir
o banco na próxima vez que o programa rodar).
"""

import base64
import hashlib

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()

# Em produção, este "salt" deve ser gerado uma vez (os.urandom(16)) e
# guardado em um arquivo de configuração local — nunca fixo no código.
# Deixado como constante aqui só para a Fase 0 (vamos resolver isso
# quando implementarmos a tela de primeiro acesso).
_SALT_PLACEHOLDER = b"troque-por-salt-aleatorio-real"


def hash_password(plain_password: str) -> str:
    """Gera o hash Argon2 da senha, para guardar e comparar depois."""
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Confere se a senha digitada bate com o hash salvo."""
    try:
        return _hasher.verify(hashed_password, plain_password)
    except VerifyMismatchError:
        return False


def derive_encryption_key(plain_password: str, salt: bytes = _SALT_PLACEHOLDER) -> bytes:
    """
    Transforma a senha mestra em uma chave de 32 bytes compatível com
    Fernet (usada pelo EncryptedDatabase para cifrar/decifrar o banco).

    100.000 iterações é o mínimo recomendado atualmente para PBKDF2-HMAC-SHA256
    — torna um ataque de força bruta computacionalmente caro.
    """
    key_bytes = hashlib.pbkdf2_hmac(
        "sha256",
        plain_password.encode("utf-8"),
        salt,
        iterations=100_000,
        dklen=32,
    )
    return base64.urlsafe_b64encode(key_bytes)

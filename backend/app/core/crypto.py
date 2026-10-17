"""Fachada de criptografia de segredos para módulos de integração (billing, ERP).

Reutiliza o Fernet/PBKDF2 de `app.agents.services.crypto` (o mesmo do TOTP), de modo que
exista uma única chave derivada de SECRET_KEY. Decifrar um valor corrompido ou cifrado com
outra chave devolve string vazia, nunca levanta.
"""
from __future__ import annotations

from app.agents.services import crypto as _crypto


def encrypt_value(plaintext: str) -> str:
    return _crypto.encrypt(plaintext) or ""


def decrypt_value(ciphertext: str) -> str:
    return _crypto.decrypt(ciphertext) or ""

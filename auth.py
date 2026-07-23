"""
Autenticação leve: usuário + PIN numérico de 4 dígitos.
Token de sessão é assinado (itsdangerous, já vem com o Flask) e sem
expiração — não há sessão no banco, o token carrega a identidade.
"""
import os
import bcrypt
from itsdangerous import URLSafeSerializer, BadSignature, BadData

_SECRET = os.environ.get("SECRET_KEY")
if not _SECRET:
    raise RuntimeError("defina a env var SECRET_KEY")

_serializer = URLSafeSerializer(_SECRET, salt="boggle-perfil")


def hash_pin(pin):
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()


def checar_pin(pin, pin_hash):
    return bcrypt.checkpw(pin.encode(), pin_hash.encode())


def gerar_token(profile_id, username):
    return _serializer.dumps({"pid": str(profile_id), "u": username})


def verificar_token(token):
    """Retorna (profile_id, username) ou (None, None) se o token for inválido."""
    try:
        data = _serializer.loads(token)
    except (BadSignature, BadData):
        return None, None
    return data.get("pid"), data.get("u")

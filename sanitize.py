"""
Validação e sanitização de inputs. Centraliza todas as regras
para nomes, nomes de sala, etc.
"""
import re

_NOME_RE = re.compile(r'^[A-Za-z0-9À-ÿ_\-. ]+$')
_SALA_RE = re.compile(r'^[A-Za-z0-9À-ÿ_\-. !?]+$')


def nome_usuario(raw):
    """Retorna (nome_limpo, erro_msg). erro_msg é None se válido."""
    if not raw or not isinstance(raw, str):
        return None, "nome obrigatório"
    nome = raw.strip()[:16]
    if len(nome) < 2:
        return None, "nome precisa ter ao menos 2 caracteres"
    if not _NOME_RE.match(nome):
        return None, "nome contém caracteres inválidos"
    return nome, None


def nome_sala(raw):
    """Retorna (nome_limpo, erro_msg)."""
    if not raw or not isinstance(raw, str):
        return None, "nome da sala obrigatório"
    nome = raw.strip()[:32]
    if len(nome) < 1:
        return None, "nome da sala não pode ser vazio"
    if not _SALA_RE.match(nome):
        return None, "nome da sala contém caracteres inválidos"
    return nome, None


def pin(raw):
    """Retorna (pin_limpo, erro_msg)."""
    if not raw or not isinstance(raw, str):
        return None, "PIN obrigatório"
    p = raw.strip()
    if not (p.isdigit() and len(p) == 4):
        return None, "o PIN precisa ter exatamente 4 dígitos"
    return p, None


def caminho(raw):
    """Valida que o caminho é uma lista de inteiros não-negativos."""
    if not isinstance(raw, list):
        return None, "caminho inválido"
    try:
        c = [int(i) for i in raw]
    except (ValueError, TypeError):
        return None, "caminho contém valores inválidos"
    if any(i < 0 for i in c):
        return None, "caminho contém índices negativos"
    return c, None


def sala_id(raw):
    """Valida que o sala_id é alfanumérico e curto."""
    if not raw or not isinstance(raw, str):
        return None, "sala_id ausente"
    s = raw.strip()[:10]
    if not re.match(r'^[A-Z0-9]+$', s):
        return None, "sala_id inválido"
    return s, None

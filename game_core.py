"""
Núcleo do Boggle: geração de grade, validação de palavra no tabuleiro,
pontuação individual e resolução da regra clássica (anula repetidas).
Sem dependência de framework — dá pra testar isolado.
"""
import json
import random
import os

BASE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(BASE, "words.json"), encoding="utf-8") as f:
    WORDS = set(json.load(f))

# distribuição de letras ponderada pro PT-BR (mais vogais e consoantes comuns)
POOL = ("AAAAAAAAAAAAAABBCCCCDDDDEEEEEEEEEEEEEEFFGGGHIIIIIIIIII"
        "JLLLLLMMMMNNNNNNOOOOOOOOOOOOPPPPQRRRRRRRRRSSSSSSSS"
        "TTTTTTTUUUUUUVVXZ")

VOGAIS = "AEIOU"


def gerar_grade():
    """16 letras (4x4). Garante ao menos 5 vogais pra jogabilidade."""
    g = [random.choice(POOL) for _ in range(16)]
    v = sum(1 for c in g if c in VOGAIS)
    while v < 5:
        k = random.randrange(16)
        if g[k] not in VOGAIS:
            g[k] = random.choice(VOGAIS)
            v += 1
    return g


def _vizinhos(a, b):
    ra, ca = divmod(a, 4)
    rb, cb = divmod(b, 4)
    return abs(ra - rb) <= 1 and abs(ca - cb) <= 1 and a != b


def caminho_valido(grade, caminho):
    """caminho = lista de índices 0..15. Verifica adjacência e não-repetição."""
    if not caminho or len(set(caminho)) != len(caminho):
        return False
    for i in range(len(caminho) - 1):
        if not _vizinhos(caminho[i], caminho[i + 1]):
            return False
    return True


def palavra_do_caminho(grade, caminho):
    return "".join(grade[i] for i in caminho)


def pontos(palavra):
    n = len(palavra)
    if n < 3:
        return 0
    if n <= 4:
        return 1
    if n == 5:
        return 2
    if n == 6:
        return 3
    if n == 7:
        return 5
    return 11


def validar_submissao(grade, caminho):
    """Retorna (ok, palavra, pontos) pra uma tentativa individual."""
    if not caminho_valido(grade, caminho):
        return False, "", 0
    w = palavra_do_caminho(grade, caminho)
    if len(w) < 3 or w not in WORDS:
        return False, w, 0
    return True, w, pontos(w)


def resolver_placar(jogadores):
    """
    jogadores: dict {nome: set(palavras_validas)}.
    Regra clássica: palavra achada por 2+ jogadores é anulada pra todos.
    Retorna dict {nome: {'palavras': [...], 'anuladas': [...], 'pontos': int}}.
    """
    contagem = {}
    for palavras in jogadores.values():
        for w in palavras:
            contagem[w] = contagem.get(w, 0) + 1

    resultado = {}
    for nome, palavras in jogadores.items():
        validas, anuladas, total = [], [], 0
        for w in palavras:
            if contagem[w] >= 2:
                anuladas.append(w)
            else:
                validas.append(w)
                total += pontos(w)
        resultado[nome] = {
            "palavras": sorted(validas),
            "anuladas": sorted(anuladas),
            "pontos": total,
        }
    return resultado

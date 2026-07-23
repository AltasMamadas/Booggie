"""
Núcleo do Boggle v2.
- Tabuleiro NxN (3..10)
- Pontuação: base = nº de letras (min 3). Exclusiva (1 jogador) vale o DOBRO.
  Repetida (2+ jogadores) vale o valor BASE. Palavra < 3 letras = 0.
- Times: pontos somados entre membros.
- Placar de partida e agregação de campeonato (por sets).
"""
import json
import random
import os
import solver as _solver

BASE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(BASE, "words.json"), encoding="utf-8") as f:
    WORDS = set(json.load(f))

# trie construída uma vez na importação (usada pra avaliar grades)
_TRIE = _solver.construir_trie(WORDS)

POOL = ("AAAAAAAAAAAAAABBCCCCDDDDEEEEEEEEEEEEEEFFGGGHIIIIIIIIII"
        "JLLLLLMMMMNNNNNNOOOOOOOOOOOOPPPPQRRRRRRRRRSSSSSSSS"
        "TTTTTTTUUUUUUVVXZ")
VOGAIS = "AEIOU"
# consoantes ponderadas por frequência no PT-BR (mais R,S,T,N,L,M,C,D,P)
POOL_CONS = "BCCCCDDDDFFGGHJLLLLLMMMMNNNNNNPPPPQRRRRRRRRRSSSSSSSSTTTTTTTVVXZ"


def _gerar_grade_crua(n=4):
    total = n * n
    # monta com proporção fixa: ~40% vogais, 60% consoantes
    n_vog = max(1, round(total * 0.40))
    letras = [random.choice(VOGAIS) for _ in range(n_vog)]
    letras += [random.choice(POOL_CONS) for _ in range(total - n_vog)]
    random.shuffle(letras)
    return letras


def gerar_grade(n=4, candidatas=30):
    """
    Gera 'candidatas' grades e retorna a que tem mais palavras encontráveis.
    Rápido: mesmo 30 candidatas num 10x10 leva ~150ms.
    Retorna (grade, qtd_palavras, maior_palavra).
    """
    melhor = None
    melhor_qtd = -1
    melhor_maior = 0
    for _ in range(max(1, candidatas)):
        g = _gerar_grade_crua(n)
        qtd, maior = _solver.contar_palavras(g, _TRIE, n)
        if qtd > melhor_qtd:
            melhor_qtd = qtd
            melhor = g
            melhor_maior = maior
    return melhor, melhor_qtd, melhor_maior


def _vizinhos(a, b, n):
    ra, ca = divmod(a, n)
    rb, cb = divmod(b, n)
    return abs(ra - rb) <= 1 and abs(ca - cb) <= 1 and a != b


def caminho_valido(caminho, n):
    if not caminho or len(set(caminho)) != len(caminho):
        return False
    total = n * n
    if any(i < 0 or i >= total for i in caminho):
        return False
    for i in range(len(caminho) - 1):
        if not _vizinhos(caminho[i], caminho[i + 1], n):
            return False
    return True


def palavra_do_caminho(grade, caminho):
    return "".join(grade[i] for i in caminho)


def _n_de_grade(grade):
    return int(round(len(grade) ** 0.5))


def validar_submissao(grade, caminho):
    n = _n_de_grade(grade)
    if not caminho_valido(caminho, n):
        return False, ""
    w = palavra_do_caminho(grade, caminho)
    if len(w) < 3 or w not in WORDS:
        return False, w
    return True, w


def pontos_base(palavra):
    n = len(palavra)
    return n if n >= 3 else 0


def resolver_placar(jogadores):
    contagem = {}
    for palavras in jogadores.values():
        for w in palavras:
            contagem[w] = contagem.get(w, 0) + 1

    resultado = {}
    for nome, palavras in jogadores.items():
        exclusivas, repetidas, total = [], [], 0
        for w in palavras:
            base = pontos_base(w)
            if contagem[w] == 1:
                total += base * 2
                exclusivas.append(w)
            else:
                total += base
                repetidas.append(w)
        resultado[nome] = {
            "exclusivas": sorted(exclusivas),
            "repetidas": sorted(repetidas),
            "pontos": total,
        }
    return resultado


def resolver_placar_times(jogadores, times):
    individual = resolver_placar(jogadores)
    placar_times = {}
    for nome, dados in individual.items():
        t = times.get(nome, "Sem time")
        placar_times[t] = placar_times.get(t, 0) + dados["pontos"]
    return individual, placar_times

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

# palavras adicionadas em tempo de execução pelos jogadores (só em memória)
EXTRAS = set()


def adicionar_palavra(p):
    """Inclui no dicionário de validação E na trie (senão o solver não a vê)."""
    p = "".join(c for c in p.upper() if c.isalpha())
    if len(p) < 3:
        return False
    if p in WORDS:
        return False
    WORDS.add(p)
    EXTRAS.add(p)
    no = _TRIE
    for ch in p:
        no = no.setdefault(ch, {})
    no["$"] = True
    return True


def remover_palavra(p):
    """Só remove palavras que foram adicionadas nesta sessão."""
    global _TRIE
    p = "".join(c for c in p.upper() if c.isalpha())
    if p in EXTRAS:
        EXTRAS.discard(p)
        WORDS.discard(p)
        # reconstrói a trie pra o solver não continuar contando a palavra
        # (custa ~35ms; remoção é rara, então compensa a simplicidade)
        _TRIE = _solver.construir_trie(WORDS)
        return True
    return False

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


def _nota_dificuldade(qtd, maior, dificuldade, alvo=0):
    """
    Nota de adequação da grade ao nível (maior = melhor).
    facil  : quanto mais palavras, melhor.
    medio  : mais perto do alvo (mediana das candidatas), melhor.
    dificil: poucas palavras, mas premiando palavras longas — senão
             a grade vira um deserto sem nada pra achar.
    """
    if dificuldade == "facil":
        return qtd
    if dificuldade == "dificil":
        return (maior * 12) - qtd
    return -abs(qtd - alvo)


def gerar_grade(n=4, candidatas=30, dificuldade="medio"):
    """
    Gera 'candidatas' grades e escolhe a que melhor atende à dificuldade.
    Retorna (grade, qtd_palavras, maior_palavra).
    """
    if dificuldade not in ("facil", "medio", "dificil"):
        dificuldade = "medio"

    avaliadas = []
    for _ in range(max(1, candidatas)):
        g = _gerar_grade_crua(n)
        qtd, maior = _solver.contar_palavras(g, _TRIE, n)
        avaliadas.append((g, qtd, maior))

    alvo = 0
    if dificuldade == "medio":
        qtds = sorted(x[1] for x in avaliadas)
        alvo = qtds[len(qtds) // 2]

    melhor = max(
        avaliadas,
        key=lambda t: _nota_dificuldade(t[1], t[2], dificuldade, alvo),
    )
    return melhor[0], melhor[1], melhor[2]


def palavras_da_grade(grade, n=None):
    """Todas as palavras encontráveis na grade (usa a trie atual)."""
    return _solver.listar_palavras(grade, _TRIE, n)


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

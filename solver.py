"""
Solver de Boggle com trie para poda. Conta palavras encontráveis numa grade.
Usado para rejeitar grades ruins e (futuramente) calibrar dificuldade.
"""
import time

# ---- Trie ----
# nó = dict; chave especial "$" marca fim de palavra.
def construir_trie(palavras):
    raiz = {}
    for w in palavras:
        no = raiz
        for ch in w:
            no = no.setdefault(ch, {})
        no["$"] = True
    return raiz


def _vizinhos_idx(n):
    """Pré-computa vizinhos de cada célula pra grade n x n."""
    viz = [[] for _ in range(n * n)]
    for i in range(n * n):
        r, c = divmod(i, n)
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < n and 0 <= nc < n:
                    viz[i].append(nr * n + nc)
    return viz


def contar_palavras(grade, trie, n=None, limite_palavras=None, deadline=None):
    """
    Retorna (qtd_palavras, palavra_mais_longa_len) encontráveis na grade.
    - limite_palavras: para cedo se atingir esse total (economia).
    - deadline: timestamp (time.time()) limite; para se estourar.
    """
    if n is None:
        n = int(round(len(grade) ** 0.5))
    viz = _vizinhos_idx(n)
    encontradas = set()
    maior = [0]
    total = len(grade)

    checa_tempo = deadline is not None
    contador = [0]

    def dfs(i, no, usados, palavra):
        # checagem de tempo periódica (a cada 4096 passos)
        if checa_tempo:
            contador[0] += 1
            if (contador[0] & 0xFFF) == 0 and time.time() > deadline:
                raise TimeoutError

        ch = grade[i]
        prox = no.get(ch)
        if prox is None:
            return
        palavra = palavra + ch
        if len(palavra) >= 3 and "$" in prox and palavra not in encontradas:
            encontradas.add(palavra)
            if len(palavra) > maior[0]:
                maior[0] = len(palavra)
            if limite_palavras and len(encontradas) >= limite_palavras:
                raise StopIteration
        for j in viz[i]:
            if j not in usados:
                usados.add(j)
                dfs(j, prox, usados, palavra)
                usados.discard(j)

    try:
        for start in range(total):
            dfs(start, trie, {start}, "")
    except StopIteration:
        pass  # atingiu limite_palavras
    # TimeoutError sobe pra quem chamou decidir

    return len(encontradas), maior[0]

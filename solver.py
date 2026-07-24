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


def dims(grade, linhas=None, colunas=None):
    """
    Descobre (linhas, colunas) de uma grade.
    Se não vier explícito, assume quadrada (compatível com o código antigo).
    """
    if linhas and colunas:
        return linhas, colunas
    n = int(round(len(grade) ** 0.5))
    return n, n


_VIZ_CACHE = {}


def _vizinhos_idx(linhas, colunas):
    """Pré-computa vizinhos de cada célula pra grade linhas x colunas.
    Memoizado: as dimensões possíveis são poucas (4x4, 4x6, 6x6...), então o
    resultado é reutilizado entre solves em vez de recomputado toda vez."""
    chave = (linhas, colunas)
    cached = _VIZ_CACHE.get(chave)
    if cached is not None:
        return cached
    total = linhas * colunas
    viz = [[] for _ in range(total)]
    for i in range(total):
        r, c = divmod(i, colunas)
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < linhas and 0 <= nc < colunas:
                    viz[i].append(nr * colunas + nc)
    _VIZ_CACHE[chave] = viz
    return viz


def contar_palavras(grade, trie, n=None, limite_palavras=None, deadline=None,
                    linhas=None, colunas=None):
    """
    Retorna (qtd_palavras, palavra_mais_longa_len) encontráveis na grade.
    - limite_palavras: para cedo se atingir esse total (economia).
    - deadline: timestamp (time.time()) limite; para se estourar.
    - linhas/colunas: pra grades retangulares (ex.: 4x6). Sem isso, assume quadrada.
    """
    if linhas is None or colunas is None:
        if n is not None:
            linhas = colunas = n
        else:
            linhas, colunas = dims(grade)
    viz = _vizinhos_idx(linhas, colunas)
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


def listar_palavras(grade, trie, n=None, linhas=None, colunas=None):
    """Como contar_palavras, mas devolve o conjunto de palavras encontráveis."""
    if linhas is None or colunas is None:
        if n is not None:
            linhas = colunas = n
        else:
            linhas, colunas = dims(grade)
    viz = _vizinhos_idx(linhas, colunas)
    encontradas = set()
    total = len(grade)

    def dfs(i, no, usados, palavra):
        ch = grade[i]
        prox = no.get(ch)
        if prox is None:
            return
        palavra = palavra + ch
        if len(palavra) >= 3 and "$" in prox:
            encontradas.add(palavra)
        for j in viz[i]:
            if j not in usados:
                usados.add(j)
                dfs(j, prox, usados, palavra)
                usados.discard(j)

    for start in range(total):
        dfs(start, trie, {start}, "")
    return encontradas


def achar_caminho(grade, palavra, linhas=None, colunas=None):
    """Devolve UM caminho (lista de índices) que forma `palavra` na grade, ou
    None se não houver. Usado pela dica para destacar as letras no tabuleiro."""
    if not palavra:
        return None
    if linhas is None or colunas is None:
        linhas, colunas = dims(grade)
    viz = _vizinhos_idx(linhas, colunas)
    palavra = palavra.upper()
    alvo = len(palavra)

    def dfs(i, pos, usados):
        if grade[i] != palavra[pos]:
            return None
        if pos == alvo - 1:
            return [i]
        for j in viz[i]:
            if j not in usados:
                usados.add(j)
                sub = dfs(j, pos + 1, usados)
                usados.discard(j)
                if sub is not None:
                    return [i] + sub
        return None

    for start in range(len(grade)):
        if grade[start] == palavra[0]:
            r = dfs(start, 0, {start})
            if r is not None:
                return r
    return None

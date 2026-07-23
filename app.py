"""
Servidor Boggle multiplayer v2.
Config de sala: tamanho (3..10), duração, modo (individual/times), campeonato (nº partidas).
Sincronização por polling. Estado em memória, uma sala global.
"""
import time
import random
import threading
from flask import Flask, request, jsonify, send_from_directory
import game_core as gc
import auth
import db

app = Flask(__name__, static_folder="static")

LOCK = threading.Lock()


def _autenticar():
    """Lê o header Authorization: Bearer <token> e retorna (pid, nome) ou (None, None)."""
    cabecalho = request.headers.get("Authorization", "")
    if not cabecalho.startswith("Bearer "):
        return None, None
    return auth.verificar_token(cabecalho[7:])


def _exigir_login():
    """Retorna (pid, nome, None) se autenticado, ou (None, None, resposta_erro)."""
    pid, nome = _autenticar()
    if not nome:
        return None, None, (jsonify({"erro": "nao autenticado"}), 401)
    return pid, nome, None

def estado_inicial():
    return {
        "fase": "lobby",           # lobby | jogando | resultado | fim_campeonato
        "config": {
            "tamanho": 4,
            "dificuldade": "medio",   # facil | medio | dificil
            "duracao": 180,
            # individual | times | sobrevivencia | caca
            "modo": "individual",
            "n_partidas": 1,       # campeonato: quantas partidas
        },
        "grade": [],
        "colunas": 4,              # nº de colunas (grades retangulares no sobrevivência)
        "linhas": 4,
        "grade_info": {},
        "grade_palavras": [],
        "resumo": {},
        # nome -> {palavras:set, visto:ts, time:str|None,
        #          fim_individual:ts, vivo:bool, ultima_palavra:ts}
        "jogadores": {},
        "host": None,              # primeiro a entrar; só ele configura/inicia
        "inicio": 0,
        "fim": 0,
        # --- sobrevivência ---
        "sobrev": {
            "fase_grade": 0,       # 0 = 4x4, 1 = 4x6, 2 = 6x6
            "prox_embaralho": 0,   # timestamp do próximo embaralhamento
            "embaralhou_em": 0,    # timestamp do último embaralhamento (pro aviso)
            "cresceu_em": 0,       # timestamp do último crescimento (pra animação)
            "celulas_novas": [],   # índices das células recém-adicionadas
        },
        "placar": {},              # placar individual da partida atual
        "placar_times": {},        # placar de times da partida atual
        "rodada": 0,               # nº da partida atual no campeonato (1-based)
        "vitorias": {},            # acumulado de sets: nome(ou time) -> nº vitórias
        "historico": [],           # [{rodada, vencedor}]
        # ranking da sessão (não zera entre campeonatos; só no /api/zerar_ranking)
        "ranking": {},             # nome -> {"total":int, "melhor":int, "partidas":int}
    }

# ---------------- parâmetros dos modos ----------------
# Sobrevivência: tempo inicial e sequência de tabuleiros por tempo decorrido.
SOBREV_TEMPO_INICIAL = 90          # 1:30
SOBREV_FASES = [                   # (segundos_decorridos, linhas, colunas)
    (0,  4, 4),
    (30, 4, 6),                    # +30s
    (60, 6, 6),                    # +30s
]
SOBREV_EMBARALHA_APOS = 90         # começa a embaralhar após 1:30 de partida
SOBREV_EMBARALHA_INTERVALO = 20    # e repete a cada 20s
SOBREV_AVISO = 5                   # segundos de aviso (peças piscando)


def _expandir_grade(grade, li_ant, co_ant, li_novo, co_novo):
    """
    Cresce o tabuleiro PRESERVANDO as letras já existentes nas mesmas
    posições (linha/coluna). Só as células novas são sorteadas.
    Retorna (nova_grade, indices_das_celulas_novas).
    """
    nova = [None] * (li_novo * co_novo)
    for r in range(li_ant):
        for c in range(co_ant):
            nova[r * co_novo + c] = grade[r * co_ant + c]
    novos = []
    for i, v in enumerate(nova):
        if v is None:
            # mistura vogais/consoantes como na geração normal
            nova[i] = (random.choice(gc.VOGAIS) if random.random() < 0.40
                       else random.choice(gc.POOL_CONS))
            novos.append(i)
    return nova, novos


def bonus_tempo(palavra):
    """3 letras=1s, 4=3s, 5=5s, 6=7s... (+2s por letra a partir de 4)."""
    n = len(palavra)
    if n < 3:
        return 0
    if n == 3:
        return 1
    return 3 + (n - 4) * 2


estado = estado_inicial()


def _fase_sobrev(decorrido):
    """Qual (linhas, colunas) corresponde ao tempo decorrido de partida."""
    atual = SOBREV_FASES[0]
    idx = 0
    for i, (t, li, co) in enumerate(SOBREV_FASES):
        if decorrido >= t:
            atual = (t, li, co)
            idx = i
    return idx, atual[1], atual[2]


def _nova_grade(linhas, colunas, dificuldade="medio", candidatas=25):
    grade, qtd, maior = gc.gerar_grade(
        linhas, candidatas=candidatas, dificuldade=dificuldade, colunas=colunas
    )
    return grade, qtd, maior


def _aplicar_sobrevivencia():
    """
    Cuida das transições de tabuleiro e do embaralhamento periódico.
    Chamado a cada consulta de estado enquanto a partida roda.
    """
    if estado["config"]["modo"] != "sobrevivencia" or estado["fase"] != "jogando":
        return
    agora = time.time()
    decorrido = agora - estado["inicio"]

    # crescimento do tabuleiro por tempo decorrido
    idx, li, co = _fase_sobrev(decorrido)
    if idx != estado["sobrev"]["fase_grade"]:
        li_ant, co_ant = estado["linhas"], estado["colunas"]
        estado["sobrev"]["fase_grade"] = idx
        # PRESERVA as letras que já estavam lá; só as células novas são sorteadas
        grade, novos = _expandir_grade(estado["grade"], li_ant, co_ant, li, co)
        estado["grade"] = grade
        estado["linhas"], estado["colunas"] = li, co
        estado["grade_palavras"] = sorted(
            gc.palavras_da_grade(grade, li, co), key=lambda w: (-len(w), w)
        )
        estado["grade_info"] = {
            "palavras": len(estado["grade_palavras"]),
            "maior": len(estado["grade_palavras"][0]) if estado["grade_palavras"] else 0,
        }
        # as palavras já achadas continuam valendo (o tabuleiro só cresceu)
        # marca as células novas pra interface animar a entrada delas
        estado["sobrev"]["cresceu_em"] = agora
        estado["sobrev"]["celulas_novas"] = novos
        # reinicia o ciclo de embaralhamento
        estado["sobrev"]["prox_embaralho"] = 0

    # embaralhamento periódico depois de SOBREV_EMBARALHA_APOS
    if decorrido >= SOBREV_EMBARALHA_APOS:
        if estado["sobrev"]["prox_embaralho"] == 0:
            estado["sobrev"]["prox_embaralho"] = agora + SOBREV_EMBARALHA_INTERVALO
        elif agora >= estado["sobrev"]["prox_embaralho"]:
            # embaralha as letras existentes (mantém o conjunto, muda as posições)
            g = estado["grade"][:]
            random.shuffle(g)
            estado["grade"] = g
            li, co = estado["linhas"], estado["colunas"]
            estado["grade_palavras"] = sorted(
                gc.palavras_da_grade(g, li, co), key=lambda w: (-len(w), w)
            )
            estado["sobrev"]["embaralhou_em"] = agora
            estado["sobrev"]["prox_embaralho"] = agora + SOBREV_EMBARALHA_INTERVALO


def _checar_eliminados():
    """No sobrevivência, marca quem ficou sem tempo. Partida acaba quando todos caem."""
    if estado["config"]["modo"] != "sobrevivencia" or estado["fase"] != "jogando":
        return
    agora = time.time()
    algum_vivo = False
    for j in estado["jogadores"].values():
        if j.get("vivo", True):
            if agora >= j.get("fim_individual", 0):
                j["vivo"] = False
            else:
                algum_vivo = True
    if not algum_vivo and estado["jogadores"]:
        # força o fim da partida
        estado["fim"] = agora - 1


def _reset_para_lobby(full=False):
    estado["fase"] = "lobby"
    estado["grade"] = []
    estado["inicio"] = 0
    estado["fim"] = 0
    estado["placar"] = {}
    estado["placar_times"] = {}
    for j in estado["jogadores"].values():
        j["palavras"] = set()
    if full:
        estado["rodada"] = 0
        estado["vitorias"] = {}
        estado["historico"] = []


def _vencedor_da_partida():
    """Retorna o nome (individual) ou time (modo times) que venceu a partida atual."""
    if estado["config"]["modo"] == "times":
        if not estado["placar_times"]:
            return None
        return max(estado["placar_times"].items(), key=lambda kv: kv[1])[0]
    else:
        if not estado["placar"]:
            return None
        return max(estado["placar"].items(), key=lambda kv: kv[1]["pontos"])[0]


def _checar_fim():
    if estado["fase"] == "jogando" and time.time() >= estado["fim"]:
        jogadores = {n: j["palavras"] for n, j in estado["jogadores"].items()}
        if estado["config"]["modo"] == "times":
            times = {n: (j["time"] or "Sem time") for n, j in estado["jogadores"].items()}
            ind, pt = gc.resolver_placar_times(jogadores, times)
            estado["placar"] = ind
            estado["placar_times"] = pt
        else:
            estado["placar"] = gc.resolver_placar(jogadores)
            estado["placar_times"] = {}

        # ranking da sessão: acumula pontos individuais de cada jogador
        for nome, dados in estado["placar"].items():
            r = estado["ranking"].setdefault(
                nome, {"total": 0, "melhor": 0, "partidas": 0}
            )
            r["total"] += dados["pontos"]
            r["partidas"] += 1
            if dados["pontos"] > r["melhor"]:
                r["melhor"] = dados["pontos"]

        # resumo da grade: o que existia vs o que o grupo achou
        todas = estado.get("grade_palavras", [])
        achadas_grupo = set()
        for j in estado["jogadores"].values():
            achadas_grupo |= j["palavras"]
        faltaram = [w for w in todas if w not in achadas_grupo]
        estado["resumo"] = {
            "total": len(todas),
            "achadas": len([w for w in todas if w in achadas_grupo]),
            "faltaram": len(faltaram),
            "maior": todas[0] if todas else "",
            "maior_achada": max(achadas_grupo, key=len) if achadas_grupo else "",
            # amostra das que faltaram, priorizando as mais longas
            "faltaram_lista": faltaram[:60],
            "achadas_lista": sorted(achadas_grupo, key=lambda w: (-len(w), w)),
        }

        # persiste estatísticas de cada jogador logado no perfil dele
        venc = _vencedor_da_partida()
        duracao = time.time() - estado["inicio"]
        modo = estado["config"]["modo"]
        for nome, dados_placar in estado["placar"].items():
            j = estado["jogadores"].get(nome)
            if not j or not j.get("perfil_id"):
                continue
            palavras = j["palavras"]
            if modo == "times":
                ganhou = (j.get("time") or "Sem time") == venc
            else:
                ganhou = nome == venc
            try:
                db.persistir_partida(j["perfil_id"], {
                    "mode": modo,
                    "team": j.get("time") if modo == "times" else None,
                    "score": dados_placar["pontos"],
                    "words_found": len(palavras),
                    "longest_word": max(palavras, key=len) if palavras else None,
                    "avg_word_length": (
                        sum(len(w) for w in palavras) / len(palavras)
                    ) if palavras else 0,
                    "words_per_second": (len(palavras) / duracao) if duracao > 0 else 0,
                    "won": ganhou,
                    "duration_seconds": duracao,
                })
            except Exception as e:
                print(f"[perfil] falha ao persistir partida de {nome}: {e}")

        # contabiliza vitória do set
        if venc is not None:
            estado["vitorias"][venc] = estado["vitorias"].get(venc, 0) + 1
            if estado["config"]["modo"] == "times":
                pontos_venc = estado["placar_times"].get(venc, 0)
            else:
                pontos_venc = estado["placar"].get(venc, {}).get("pontos", 0)
            estado["historico"].append({
                "rodada": estado["rodada"],
                "vencedor": venc,
                "pontos": pontos_venc,
            })
            # mantém só as últimas 5
            estado["historico"] = estado["historico"][-5:]

        # fim de campeonato?
        if estado["rodada"] >= estado["config"]["n_partidas"]:
            estado["fase"] = "fim_campeonato"
        else:
            estado["fase"] = "resultado"


def _limpar_ausentes():
    if estado["fase"] != "lobby":
        return
    agora = time.time()
    fora = [n for n, j in estado["jogadores"].items() if agora - j["visto"] > 30]
    for n in fora:
        del estado["jogadores"][n]
    if fora:
        _passar_host()


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/perfil/criar", methods=["POST"])
def perfil_criar():
    data = request.json or {}
    username = (data.get("username") or "").strip()[:16]
    pin = (data.get("pin") or "").strip()
    if not username or not (pin.isdigit() and len(pin) == 4):
        return jsonify({"ok": False, "motivo": "usuario ou pin invalido"}), 400
    if db.buscar_perfil(username):
        return jsonify({"ok": False, "motivo": "usuario ja existe"}), 409
    pid = db.criar_perfil(username, auth.hash_pin(pin))
    token = auth.gerar_token(pid, username)
    return jsonify({"ok": True, "token": token, "username": username})


@app.route("/api/perfil/login", methods=["POST"])
def perfil_login():
    data = request.json or {}
    username = (data.get("username") or "").strip()[:16]
    pin = (data.get("pin") or "").strip()
    perfil = db.buscar_perfil(username)
    if not perfil or not auth.checar_pin(pin, perfil["pin_hash"]):
        return jsonify({"ok": False, "motivo": "usuario ou pin incorretos"}), 401
    token = auth.gerar_token(perfil["id"], username)
    stats = db.obter_stats(perfil["id"])
    return jsonify({"ok": True, "token": token, "username": username, "stats": stats})


@app.route("/api/entrar", methods=["POST"])
def entrar():
    pid, nome, erro = _exigir_login()
    if erro:
        return erro
    with LOCK:
        if nome not in estado["jogadores"]:
            estado["jogadores"][nome] = {
                "palavras": set(), "visto": time.time(), "time": None,
                "vivo": True, "fim_individual": 0, "ultima_palavra": 0,
                "perfil_id": pid,
            }
        else:
            estado["jogadores"][nome]["visto"] = time.time()
            estado["jogadores"][nome]["perfil_id"] = pid
        # o primeiro a entrar vira host
        if estado["host"] is None or estado["host"] not in estado["jogadores"]:
            estado["host"] = nome
    return jsonify({"ok": True, "nome": nome, "host": estado["host"] == nome})


def _eh_host(nome):
    return bool(nome) and estado["host"] == nome


def _passar_host():
    """Se o host saiu, promove o próximo jogador da lista."""
    if estado["host"] in estado["jogadores"]:
        return
    estado["host"] = next(iter(estado["jogadores"]), None)


@app.route("/api/config", methods=["POST"])
def config():
    """Atualiza config da sala (só no lobby)."""
    data = request.json or {}
    _, nome, erro = _exigir_login()
    if erro:
        return erro
    with LOCK:
        if not _eh_host(nome):
            return jsonify({"ok": False, "motivo": "so o host configura"})
        if estado["fase"] not in ("lobby", "fim_campeonato"):
            return jsonify({"ok": False, "motivo": "so no lobby"})
        c = estado["config"]
        # Recordes da sessão zeram quando o MODO DE JOGO muda (as partidas
        # deixam de ser comparáveis). Entrar/sair jogador não zera nada.
        muda_modo = (
            ("modo" in data and data["modo"] != c["modo"])
            or ("tamanho" in data and int(data["tamanho"]) != c["tamanho"])
            or ("dificuldade" in data and data["dificuldade"] != c["dificuldade"])
            or ("duracao" in data and int(data["duracao"]) != c["duracao"])
        )
        if "tamanho" in data:
            c["tamanho"] = max(3, min(10, int(data["tamanho"])))
        if "dificuldade" in data and data["dificuldade"] in ("facil", "medio", "dificil"):
            c["dificuldade"] = data["dificuldade"]
        if "duracao" in data:
            c["duracao"] = max(30, min(600, int(data["duracao"])))
        if "modo" in data and data["modo"] in (
            "individual", "times", "sobrevivencia", "caca"
        ):
            c["modo"] = data["modo"]
        if "n_partidas" in data:
            c["n_partidas"] = max(1, min(15, int(data["n_partidas"])))
        if muda_modo:
            estado["ranking"] = {}
            estado["historico"] = []
            estado["vitorias"] = {}
    return jsonify({"ok": True, "config": estado["config"]})


@app.route("/api/time", methods=["POST"])
def set_time():
    """Define o time de um jogador (só no lobby)."""
    data = request.json or {}
    _, nome, erro = _exigir_login()
    if erro:
        return erro
    t = (data.get("time", "") or "").strip()[:16] or None
    with LOCK:
        if nome in estado["jogadores"]:
            estado["jogadores"][nome]["time"] = t
    return jsonify({"ok": True})


@app.route("/api/iniciar", methods=["POST"])
def iniciar():
    _, nome, erro = _exigir_login()
    if erro:
        return erro
    with LOCK:
        if not _eh_host(nome):
            return jsonify({"ok": False, "motivo": "so o host inicia"})
        # se veio de fim de campeonato, zera o placar de sets
        if estado["fase"] == "fim_campeonato":
            _reset_para_lobby(full=True)
        # nova partida do campeonato
        if estado["fase"] in ("lobby", "resultado"):
            if estado["fase"] == "lobby":
                estado["rodada"] = 0
                estado["vitorias"] = {}
                estado["historico"] = []
        estado["fase"] = "jogando"
        modo = estado["config"]["modo"]
        dif = estado["config"].get("dificuldade", "medio")

        # dimensões iniciais dependem do modo
        if modo == "sobrevivencia":
            _, li, co = _fase_sobrev(0)          # começa 4x4
            estado["sobrev"] = {"fase_grade": 0, "prox_embaralho": 0,
                                "embaralhou_em": 0, "cresceu_em": 0,
                                "celulas_novas": []}
        else:
            li = co = estado["config"]["tamanho"]

        grade, qtd_palavras, maior = gc.gerar_grade(
            li, dificuldade=dif, colunas=co,
        )
        estado["grade"] = grade
        estado["linhas"], estado["colunas"] = li, co
        estado["grade_info"] = {"palavras": qtd_palavras, "maior": maior}
        todas = gc.palavras_da_grade(grade, li, co)
        estado["grade_palavras"] = sorted(todas, key=lambda w: (-len(w), w))

        agora = time.time()
        estado["inicio"] = agora
        if modo == "sobrevivencia":
            # cada jogador tem seu próprio relógio; o "fim" da sala é só um teto
            estado["fim"] = agora + 60 * 60
        elif modo == "caca":
            # caça completa: sem limite de tempo (teto alto de segurança)
            estado["fim"] = agora + 60 * 60
        else:
            estado["fim"] = agora + estado["config"]["duracao"]

        estado["rodada"] += 1
        for j in estado["jogadores"].values():
            j["palavras"] = set()
            j["vivo"] = True
            j["fim_individual"] = agora + SOBREV_TEMPO_INICIAL
            j["ultima_palavra"] = agora
        estado["placar"] = {}
        estado["placar_times"] = {}
    return jsonify({"ok": True})


@app.route("/api/zerar_ranking", methods=["POST"])
def zerar_ranking():
    with LOCK:
        estado["ranking"] = {}
    return jsonify({"ok": True})


@app.route("/api/palavras", methods=["GET", "POST"])
def palavras_extras():
    """
    Palavras adicionadas pelos jogadores nesta sessão.
    Ficam em memória (somem se o servidor reiniciar) e valem pra todos.
    """
    if request.method == "GET":
        return jsonify({"palavras": sorted(gc.EXTRAS)})

    data = request.json or {}
    texto = (data.get("palavras") or "").upper()
    acao = data.get("acao", "add")
    novas = [p.strip() for p in texto.replace(",", " ").replace("\n", " ").split()]
    novas = ["".join(c for c in p if c.isalpha()) for p in novas]
    novas = [p for p in novas if 3 <= len(p) <= 16]

    aplicadas, ignoradas = [], []
    with LOCK:
        for p in novas:
            if acao == "remover":
                (aplicadas if gc.remover_palavra(p) else ignoradas).append(p)
            else:
                (aplicadas if gc.adicionar_palavra(p) else ignoradas).append(p)
    return jsonify({
        "ok": True,
        "acao": acao,
        "aplicadas": aplicadas,      # de fato adicionadas/removidas
        "ignoradas": ignoradas,      # já existiam no dicionário base, ou não eram extras
        "total_extras": len(gc.EXTRAS),
    })


@app.route("/api/nova", methods=["POST"])
def nova():
    """Encerra a partida / volta ao lobby. Só o host (ou sala vazia)."""
    _, nome, erro = _exigir_login()
    if erro:
        return erro
    with LOCK:
        if estado["jogadores"] and not _eh_host(nome):
            return jsonify({"ok": False, "motivo": "so o host encerra"})
        _reset_para_lobby(full=True)
    return jsonify({"ok": True})


@app.route("/api/sair", methods=["POST"])
def sair():
    """Jogador sai da sala. Se era o host, passa o bastão."""
    _, nome, erro = _exigir_login()
    if erro:
        return erro
    with LOCK:
        if nome in estado["jogadores"]:
            del estado["jogadores"][nome]
        _passar_host()
        # sala vazia volta ao lobby limpo
        if not estado["jogadores"]:
            _reset_para_lobby(full=True)
            estado["ranking"] = {}
            estado["host"] = None
    return jsonify({"ok": True})


@app.route("/api/submeter", methods=["POST"])
def submeter():
    data = request.json or {}
    _, nome, erro = _exigir_login()
    if erro:
        return erro
    caminho = data.get("caminho", [])
    with LOCK:
        if estado["fase"] != "jogando":
            return jsonify({"ok": False, "motivo": "fora de partida"})
        if nome not in estado["jogadores"]:
            return jsonify({"ok": False, "motivo": "desconhecido"})
        j = estado["jogadores"][nome]
        modo = estado["config"]["modo"]

        # no sobrevivência, quem já ficou sem tempo não pontua mais
        if modo == "sobrevivencia" and not j.get("vivo", True):
            return jsonify({"ok": False, "motivo": "sem tempo"})

        # usa as dimensões reais da grade (pode ser retangular, ex.: 4x6)
        ok, w = gc.validar_submissao(
            estado["grade"], caminho,
            linhas=estado["linhas"], colunas=estado["colunas"],
        )
        if not ok:
            return jsonify({"ok": False, "palavra": w})

        agora = time.time()
        ja = w in j["palavras"]
        j["palavras"].add(w)
        j["visto"] = agora
        if not ja:
            j["ultima_palavra"] = agora

        resp = {"ok": True, "palavra": w, "base": gc.pontos_base(w), "repetida": ja}

        # sobrevivência: palavra nova devolve tempo
        if modo == "sobrevivencia" and not ja:
            ganho = bonus_tempo(w)
            j["fim_individual"] = j.get("fim_individual", agora) + ganho
            resp["ganho_tempo"] = ganho

        # caça completa: informa o progresso
        if modo == "caca":
            total = len(estado["grade_palavras"])
            achou = len(j["palavras"])
            resp["progresso"] = {"achadas": achou, "total": total}
            if achou >= total and total > 0:
                estado["fim"] = agora - 1   # completou tudo: encerra
        return jsonify(resp)


@app.route("/api/dica", methods=["POST"])
def dica():
    """
    Dá uma dica: sempre uma palavra de EXATAMENTE 3 letras que o jogador
    ainda não achou. Disponível nos modos individual, times e caça.
    Se todas as de 3 letras já foram achadas, não devolve nada.
    """
    _, nome, erro = _exigir_login()
    if erro:
        return erro
    with LOCK:
        if estado["fase"] != "jogando":
            return jsonify({"ok": False, "motivo": "fora de partida"})
        if estado["config"]["modo"] not in ("individual", "times", "caca"):
            return jsonify({"ok": False, "motivo": "modo sem dicas"})
        if nome not in estado["jogadores"]:
            return jsonify({"ok": False, "motivo": "desconhecido"})

        ja = estado["jogadores"][nome]["palavras"]
        candidatas = [w for w in estado["grade_palavras"]
                      if len(w) == 3 and w not in ja]
        if not candidatas:
            return jsonify({"ok": True, "palavra": None,
                            "motivo": "achou todas de 3 letras"})
        return jsonify({"ok": True, "palavra": random.choice(candidatas)})


@app.route("/api/estado")
def get_estado():
    _, nome, erro = _exigir_login()
    if erro:
        return erro
    with LOCK:
        agora = time.time()
        if nome in estado["jogadores"]:
            estado["jogadores"][nome]["visto"] = agora

        # mecânicas do sobrevivência antes de avaliar o fim
        _aplicar_sobrevivencia()
        _checar_eliminados()
        _checar_fim()
        _limpar_ausentes()

        modo = estado["config"]["modo"]
        jogando = estado["fase"] == "jogando"

        # tempo restante: individual no sobrevivência, da sala nos demais
        restante = 0
        if jogando:
            if modo == "sobrevivencia" and nome in estado["jogadores"]:
                fim_ind = estado["jogadores"][nome].get("fim_individual", agora)
                restante = max(0, int(round(fim_ind - agora)))
            elif modo == "caca":
                restante = -1          # sem limite de tempo
            else:
                restante = max(0, int(estado["fim"] - agora))

        minhas = []
        vivo = True
        if nome in estado["jogadores"]:
            minhas = sorted(estado["jogadores"][nome]["palavras"])
            vivo = estado["jogadores"][nome].get("vivo", True)

        jogadores_info = []
        for n, j in estado["jogadores"].items():
            info = {"nome": n, "time": j["time"]}
            if modo == "sobrevivencia":
                info["vivo"] = j.get("vivo", True)
                info["restante"] = max(0, int(round(j.get("fim_individual", agora) - agora)))
                info["palavras"] = len(j["palavras"])
            elif modo == "caca":
                info["palavras"] = len(j["palavras"])
            jogadores_info.append(info)

        # aviso de embaralhamento: piscar por SOBREV_AVISO segundos
        embaralhou_ha = None
        cresceu_ha = None
        celulas_novas = []
        if modo == "sobrevivencia" and jogando:
            t = estado["sobrev"].get("embaralhou_em", 0)
            if t and (agora - t) <= SOBREV_AVISO:
                embaralhou_ha = round(agora - t, 1)
            # crescimento: janela maior, pra dar tempo da animação rodar
            tc = estado["sobrev"].get("cresceu_em", 0)
            if tc and (agora - tc) <= 6:
                cresceu_ha = round(agora - tc, 1)
                celulas_novas = estado["sobrev"].get("celulas_novas", [])

        resp = {
            "fase": estado["fase"],
            "config": estado["config"],
            "host": estado["host"],
            "sou_host": estado["host"] == nome,
            "rodada": estado["rodada"],
            "grade": estado["grade"] if jogando else [],
            "linhas": estado["linhas"],
            "colunas": estado["colunas"],
            # a contagem NÃO é exposta durante a partida (spoiler);
            # só sai no resumo, depois que o tempo acaba.
            "resumo": estado["resumo"] if estado["fase"] in ("resultado", "fim_campeonato") else {},
            "restante": restante,
            "vivo": vivo,
            "jogadores": jogadores_info,
            "minhas_palavras": minhas,
            "placar": estado["placar"],
            "placar_times": estado["placar_times"],
            "vitorias": estado["vitorias"],
            "historico": estado["historico"],
            "ranking": estado["ranking"],
        }
        if embaralhou_ha is not None:
            resp["embaralhou_ha"] = embaralhou_ha
            resp["aviso_embaralho"] = SOBREV_AVISO
        if cresceu_ha is not None:
            resp["cresceu_ha"] = cresceu_ha
            resp["celulas_novas"] = celulas_novas
        if modo == "caca" and jogando:
            resp["progresso"] = {
                "achadas": len(minhas),
                "total": len(estado["grade_palavras"]),
            }
        return jsonify(resp)


if __name__ == "__main__":
    import os
    porta = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=porta, debug=False)

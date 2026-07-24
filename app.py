"""
Servidor Boggle multiplayer v3.
Multi-sala com nome e senha opcional. Série de vitórias (1/3/5/7).
Modo cooperativo (caça com palavras partilhadas) e competitivo.
"""
import time, random, threading, secrets
from flask import Flask, request, jsonify, send_from_directory
import game_core as gc
import auth, db

app = Flask(__name__, static_folder="static")
LOCK = threading.Lock()

# -------- pool de salas --------
# sala_id -> {"id", "nome", "senha_hash", "estado", "criada_em", "vazia_desde"}
salas = {}

SOBREV_TEMPO_INICIAL = 90
SOBREV_FASES = [(0, 4, 4), (30, 4, 6), (60, 6, 6)]
SOBREV_EMBARALHA_APOS = 90
SOBREV_EMBARALHA_INTERVALO = 20
SOBREV_AVISO = 5


def estado_inicial():
    return {
        "fase": "lobby",
        "config": {
            "tamanho": 4,
            "dificuldade": "medio",
            "duracao": 180,
            "modo_categoria": "competitivo",  # cooperativo | competitivo
            "modo": "individual",              # individual | times | sobrevivencia | caca
            "n_partidas": 1,                   # série: primeiro a ganhar N partidas
        },
        "grade": [],
        "colunas": 4,
        "linhas": 4,
        "grade_info": {},
        "grade_palavras": [],
        "resumo": {},
        "jogadores": {},
        "host": None,
        "inicio": 0,
        "fim": 0,
        "sobrev": {
            "fase_grade": 0, "prox_embaralho": 0,
            "embaralhou_em": 0, "cresceu_em": 0, "celulas_novas": [],
        },
        "placar": {},
        "placar_times": {},
        "rodada": 0,
        "vitorias": {},
        "historico": [],
        "ranking": {},
    }


def _gerar_sala_id():
    while True:
        sid = secrets.token_hex(3).upper()
        if sid not in salas:
            return sid


def _autenticar():
    cab = request.headers.get("Authorization", "")
    if not cab.startswith("Bearer "):
        return None, None
    return auth.verificar_token(cab[7:])


def _exigir_login():
    pid, nome = _autenticar()
    if not nome:
        return None, None, (jsonify({"erro": "nao autenticado"}), 401)
    return pid, nome, None


def _sala_ou_erro(sala_id):
    if not sala_id:
        return None, (jsonify({"erro": "sala_id ausente"}), 400)
    sala = salas.get(sala_id)
    if not sala:
        return None, (jsonify({"erro": "sala nao encontrada"}), 404)
    return sala, None


def _eh_host(nome, estado):
    return bool(nome) and estado["host"] == nome


def _passar_host(estado):
    if estado["host"] in estado["jogadores"]:
        return
    estado["host"] = next(iter(estado["jogadores"]), None)


def _expandir_grade(grade, li_ant, co_ant, li_novo, co_novo):
    nova = [None] * (li_novo * co_novo)
    for r in range(li_ant):
        for c in range(co_ant):
            nova[r * co_novo + c] = grade[r * co_ant + c]
    novos = []
    for i, v in enumerate(nova):
        if v is None:
            nova[i] = (random.choice(gc.VOGAIS) if random.random() < 0.40
                       else random.choice(gc.POOL_CONS))
            novos.append(i)
    return nova, novos


def bonus_tempo(palavra):
    n = len(palavra)
    if n < 3: return 0
    if n == 3: return 1
    return 3 + (n - 4) * 2


def _fase_sobrev(decorrido):
    atual = SOBREV_FASES[0]; idx = 0
    for i, (t, li, co) in enumerate(SOBREV_FASES):
        if decorrido >= t:
            atual = (t, li, co); idx = i
    return idx, atual[1], atual[2]


def _aplicar_sobrevivencia(estado):
    if estado["config"]["modo"] != "sobrevivencia" or estado["fase"] != "jogando":
        return
    agora = time.time()
    decorrido = agora - estado["inicio"]
    idx, li, co = _fase_sobrev(decorrido)
    if idx != estado["sobrev"]["fase_grade"]:
        li_ant, co_ant = estado["linhas"], estado["colunas"]
        estado["sobrev"]["fase_grade"] = idx
        grade, novos = _expandir_grade(estado["grade"], li_ant, co_ant, li, co)
        estado["grade"] = grade
        estado["linhas"], estado["colunas"] = li, co
        estado["grade_palavras"] = sorted(
            gc.palavras_da_grade(grade, li, co), key=lambda w: (-len(w), w))
        estado["grade_info"] = {
            "palavras": len(estado["grade_palavras"]),
            "maior": len(estado["grade_palavras"][0]) if estado["grade_palavras"] else 0,
        }
        estado["sobrev"]["cresceu_em"] = agora
        estado["sobrev"]["celulas_novas"] = novos
        estado["sobrev"]["prox_embaralho"] = 0
    if decorrido >= SOBREV_EMBARALHA_APOS:
        if estado["sobrev"]["prox_embaralho"] == 0:
            estado["sobrev"]["prox_embaralho"] = agora + SOBREV_EMBARALHA_INTERVALO
        elif agora >= estado["sobrev"]["prox_embaralho"]:
            g = estado["grade"][:]
            random.shuffle(g)
            estado["grade"] = g
            li, co = estado["linhas"], estado["colunas"]
            estado["grade_palavras"] = sorted(
                gc.palavras_da_grade(g, li, co), key=lambda w: (-len(w), w))
            estado["sobrev"]["embaralhou_em"] = agora
            estado["sobrev"]["prox_embaralho"] = agora + SOBREV_EMBARALHA_INTERVALO


def _checar_eliminados(estado):
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
        estado["fim"] = agora - 1


def _reset_para_lobby(estado, full=False):
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


def _vencedor_da_partida(estado):
    if estado["config"]["modo"] == "times":
        if not estado["placar_times"]:
            return None
        return max(estado["placar_times"].items(), key=lambda kv: kv[1])[0]
    else:
        if not estado["placar"]:
            return None
        return max(estado["placar"].items(), key=lambda kv: kv[1]["pontos"])[0]


def _checar_fim(estado):
    if estado["fase"] != "jogando" or time.time() < estado["fim"]:
        return
    jogadores_palavras = {n: j["palavras"] for n, j in estado["jogadores"].items()}
    if estado["config"]["modo"] == "times":
        times = {n: (j["time"] or "Sem time") for n, j in estado["jogadores"].items()}
        ind, pt = gc.resolver_placar_times(jogadores_palavras, times)
        estado["placar"] = ind
        estado["placar_times"] = pt
    else:
        estado["placar"] = gc.resolver_placar(jogadores_palavras)
        estado["placar_times"] = {}

    for nome, dados in estado["placar"].items():
        r = estado["ranking"].setdefault(nome, {"total": 0, "melhor": 0, "partidas": 0})
        r["total"] += dados["pontos"]
        r["partidas"] += 1
        if dados["pontos"] > r["melhor"]:
            r["melhor"] = dados["pontos"]

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
        "faltaram_lista": faltaram[:60],
        "achadas_lista": sorted(achadas_grupo, key=lambda w: (-len(w), w)),
    }

    venc = _vencedor_da_partida(estado)
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
                "avg_word_length": (sum(len(w) for w in palavras) / len(palavras)) if palavras else 0,
                "words_per_second": (len(palavras) / duracao) if duracao > 0 else 0,
                "won": ganhou,
                "duration_seconds": duracao,
            })
        except Exception as e:
            print(f"[perfil] falha ao persistir partida de {nome}: {e}")

    if venc is not None:
        estado["vitorias"][venc] = estado["vitorias"].get(venc, 0) + 1
        pontos_venc = (estado["placar_times"].get(venc, 0) if modo == "times"
                       else estado["placar"].get(venc, {}).get("pontos", 0))
        estado["historico"].append({"rodada": estado["rodada"], "vencedor": venc, "pontos": pontos_venc})
        estado["historico"] = estado["historico"][-5:]

    # série: primeiro a ganhar n_partidas
    alvo = estado["config"]["n_partidas"]
    max_vit = max(estado["vitorias"].values(), default=0) if estado["vitorias"] else 0
    if alvo <= 1 or max_vit >= alvo:
        estado["fase"] = "fim_campeonato"
    else:
        estado["fase"] = "resultado"


def _limpar_ausentes(sala):
    estado = sala["estado"]
    agora = time.time()
    if estado["fase"] != "jogando":
        fora = [n for n, j in estado["jogadores"].items() if agora - j["visto"] > 30]
        for n in fora:
            del estado["jogadores"][n]
    elif (estado["jogadores"] and
          all(agora - j["visto"] > 30 for j in estado["jogadores"].values())):
        _reset_para_lobby(estado, full=True)
        estado["host"] = None
        return
    if estado["host"] not in estado["jogadores"]:
        _passar_host(estado)
    if not estado["jogadores"] and estado["fase"] != "jogando":
        _reset_para_lobby(estado, full=True)
        estado["host"] = None
        sala.setdefault("vazia_desde", agora)


def _limpar_salas_vazias():
    agora = time.time()
    para_remover = [
        sid for sid, sala in salas.items()
        if not sala["estado"]["jogadores"]
        and (agora - sala.get("vazia_desde", agora)) > 300
    ]
    for sid in para_remover:
        del salas[sid]


# ---- rotas de perfil ----

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
    return jsonify({"ok": True, "token": token, "username": username})


@app.route("/api/perfil/stats")
def perfil_stats():
    pid, nome, erro = _exigir_login()
    if erro: return erro
    stats = db.obter_stats(pid)
    if not stats:
        return jsonify({"ok": False, "motivo": "perfil nao encontrado"}), 404
    return jsonify({"ok": True,
                    "stats": {k: (str(v) if hasattr(v, '__float__') else v) for k, v in stats.items()},
                    "username": nome})


@app.route("/api/leaderboard")
def leaderboard():
    _, _, erro = _exigir_login()
    if erro: return erro
    data = db.obter_leaderboard()
    resultado = [{k: float(v) if hasattr(v, '__float__') else v for k, v in row.items()}
                 for row in data]
    return jsonify({"ok": True, "data": resultado})


# ---- rotas de sala ----

@app.route("/api/salas")
def listar_salas():
    _, _, erro = _exigir_login()
    if erro: return erro
    with LOCK:
        _limpar_salas_vazias()
        lista = [{
            "id": sala["id"],
            "nome": sala["nome"],
            "jogadores": len(sala["estado"]["jogadores"]),
            "fase": sala["estado"]["fase"],
            "tem_senha": bool(sala["senha_hash"]),
            "modo_categoria": sala["estado"]["config"]["modo_categoria"],
            "modo": sala["estado"]["config"]["modo"],
        } for sala in salas.values()]
    return jsonify({"ok": True, "salas": lista})


@app.route("/api/sala/criar", methods=["POST"])
def criar_sala():
    pid, nome, erro = _exigir_login()
    if erro: return erro
    data = request.json or {}
    nome_sala = (data.get("nome") or "").strip()[:32]
    if not nome_sala:
        return jsonify({"ok": False, "motivo": "nome da sala obrigatorio"}), 400
    senha = (data.get("senha") or "").strip()
    senha_hash = auth.hash_pin(senha) if senha else None
    with LOCK:
        sid = _gerar_sala_id()
        e = estado_inicial()
        e["jogadores"][nome] = {
            "palavras": set(), "visto": time.time(), "time": None,
            "vivo": True, "fim_individual": 0, "ultima_palavra": 0,
            "perfil_id": pid,
        }
        e["host"] = nome
        salas[sid] = {
            "id": sid, "nome": nome_sala, "senha_hash": senha_hash,
            "estado": e, "criada_em": time.time(),
        }
    return jsonify({"ok": True, "sala_id": sid, "sala_nome": nome_sala, "nome": nome})


@app.route("/api/sala/<sala_id>/entrar", methods=["POST"])
def entrar_sala(sala_id):
    pid, nome, erro = _exigir_login()
    if erro: return erro
    data = request.json or {}
    with LOCK:
        sala, err = _sala_ou_erro(sala_id)
        if err: return err
        estado = sala["estado"]
        # verifica senha se for novo na sala
        if nome not in estado["jogadores"] and sala["senha_hash"]:
            senha = (data.get("senha") or "").strip()
            if not auth.checar_pin(senha, sala["senha_hash"]):
                return jsonify({"ok": False, "motivo": "senha incorreta"}), 403
        if nome not in estado["jogadores"]:
            estado["jogadores"][nome] = {
                "palavras": set(), "visto": time.time(), "time": None,
                "vivo": True, "fim_individual": 0, "ultima_palavra": 0,
                "perfil_id": pid,
            }
        else:
            estado["jogadores"][nome]["visto"] = time.time()
            estado["jogadores"][nome]["perfil_id"] = pid
        if estado["host"] is None or estado["host"] not in estado["jogadores"]:
            estado["host"] = nome
        sala.pop("vazia_desde", None)
    return jsonify({"ok": True, "nome": nome, "sala_nome": sala["nome"],
                    "host": estado["host"] == nome})


@app.route("/api/sala/<sala_id>/sair", methods=["POST"])
def sair(sala_id):
    _, nome, erro = _exigir_login()
    if erro: return erro
    with LOCK:
        sala, err = _sala_ou_erro(sala_id)
        if err: return err
        estado = sala["estado"]
        if nome in estado["jogadores"]:
            del estado["jogadores"][nome]
        _passar_host(estado)
        if not estado["jogadores"]:
            _reset_para_lobby(estado, full=True)
            estado["ranking"] = {}
            estado["host"] = None
            sala["vazia_desde"] = time.time()
    return jsonify({"ok": True})


@app.route("/api/sala/<sala_id>/config", methods=["POST"])
def config_sala(sala_id):
    data = request.json or {}
    _, nome, erro = _exigir_login()
    if erro: return erro
    with LOCK:
        sala, err = _sala_ou_erro(sala_id)
        if err: return err
        estado = sala["estado"]
        if not _eh_host(nome, estado):
            return jsonify({"ok": False, "motivo": "so o host configura"})
        if estado["fase"] not in ("lobby", "fim_campeonato"):
            return jsonify({"ok": False, "motivo": "so no lobby"})
        c = estado["config"]
        muda_modo = (
            ("modo" in data and data["modo"] != c["modo"])
            or ("modo_categoria" in data and data["modo_categoria"] != c["modo_categoria"])
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
        if "modo_categoria" in data and data["modo_categoria"] in ("cooperativo", "competitivo"):
            c["modo_categoria"] = data["modo_categoria"]
            if data["modo_categoria"] == "cooperativo":
                c["modo"] = "caca"
        if "modo" in data and data["modo"] in ("individual", "times", "sobrevivencia"):
            if c["modo_categoria"] == "competitivo":
                c["modo"] = data["modo"]
        if "n_partidas" in data and int(data["n_partidas"]) in (1, 3, 5, 7):
            c["n_partidas"] = int(data["n_partidas"])
        if muda_modo:
            estado["ranking"] = {}
            estado["historico"] = []
            estado["vitorias"] = {}
    return jsonify({"ok": True, "config": estado["config"]})


@app.route("/api/sala/<sala_id>/time", methods=["POST"])
def set_time(sala_id):
    data = request.json or {}
    _, nome, erro = _exigir_login()
    if erro: return erro
    t = (data.get("time", "") or "").strip()[:16] or None
    with LOCK:
        sala, err = _sala_ou_erro(sala_id)
        if err: return err
        if nome in sala["estado"]["jogadores"]:
            sala["estado"]["jogadores"][nome]["time"] = t
    return jsonify({"ok": True})


@app.route("/api/sala/<sala_id>/iniciar", methods=["POST"])
def iniciar(sala_id):
    _, nome, erro = _exigir_login()
    if erro: return erro
    with LOCK:
        sala, err = _sala_ou_erro(sala_id)
        if err: return err
        estado = sala["estado"]
        if not _eh_host(nome, estado):
            return jsonify({"ok": False, "motivo": "so o host inicia"})
        if estado["fase"] == "fim_campeonato":
            _reset_para_lobby(estado, full=True)
        if estado["fase"] == "lobby":
            estado["rodada"] = 0
            estado["vitorias"] = {}
            estado["historico"] = []
        estado["fase"] = "jogando"
        modo = estado["config"]["modo"]
        dif = estado["config"].get("dificuldade", "medio")
        if modo == "sobrevivencia":
            _, li, co = _fase_sobrev(0)
            estado["sobrev"] = {"fase_grade": 0, "prox_embaralho": 0,
                                "embaralhou_em": 0, "cresceu_em": 0, "celulas_novas": []}
        else:
            li = co = estado["config"]["tamanho"]
        grade, qtd, maior = gc.gerar_grade(li, dificuldade=dif, colunas=co)
        estado["grade"] = grade
        estado["linhas"], estado["colunas"] = li, co
        estado["grade_info"] = {"palavras": qtd, "maior": maior}
        todas = gc.palavras_da_grade(grade, li, co)
        estado["grade_palavras"] = sorted(todas, key=lambda w: (-len(w), w))
        agora = time.time()
        estado["inicio"] = agora
        estado["fim"] = agora + (60 * 60 if modo in ("sobrevivencia", "caca")
                                 else estado["config"]["duracao"])
        estado["rodada"] += 1
        for j in estado["jogadores"].values():
            j["palavras"] = set()
            j["vivo"] = True
            j["fim_individual"] = agora + SOBREV_TEMPO_INICIAL
            j["ultima_palavra"] = agora
        estado["placar"] = {}
        estado["placar_times"] = {}
    return jsonify({"ok": True})


@app.route("/api/sala/<sala_id>/nova", methods=["POST"])
def nova(sala_id):
    _, nome, erro = _exigir_login()
    if erro: return erro
    with LOCK:
        sala, err = _sala_ou_erro(sala_id)
        if err: return err
        estado = sala["estado"]
        if estado["jogadores"] and not _eh_host(nome, estado):
            return jsonify({"ok": False, "motivo": "so o host encerra"})
        _reset_para_lobby(estado, full=True)
    return jsonify({"ok": True})


@app.route("/api/sala/<sala_id>/submeter", methods=["POST"])
def submeter(sala_id):
    data = request.json or {}
    _, nome, erro = _exigir_login()
    if erro: return erro
    caminho = data.get("caminho", [])
    with LOCK:
        sala, err = _sala_ou_erro(sala_id)
        if err: return err
        estado = sala["estado"]
        if estado["fase"] != "jogando":
            return jsonify({"ok": False, "motivo": "fora de partida"})
        if nome not in estado["jogadores"]:
            return jsonify({"ok": False, "motivo": "desconhecido"})
        j = estado["jogadores"][nome]
        modo = estado["config"]["modo"]
        if modo == "sobrevivencia" and not j.get("vivo", True):
            return jsonify({"ok": False, "motivo": "sem tempo"})
        ok, w = gc.validar_submissao(estado["grade"], caminho,
                                      linhas=estado["linhas"], colunas=estado["colunas"])
        if not ok:
            return jsonify({"ok": False, "palavra": w})
        agora = time.time()
        ja = w in j["palavras"]
        j["palavras"].add(w)
        j["visto"] = agora
        if not ja:
            j["ultima_palavra"] = agora
        resp = {"ok": True, "palavra": w, "base": gc.pontos_base(w), "repetida": ja}
        if modo == "sobrevivencia" and not ja:
            ganho = bonus_tempo(w)
            j["fim_individual"] = j.get("fim_individual", agora) + ganho
            resp["ganho_tempo"] = ganho
        if modo == "caca":
            modo_cat = estado["config"]["modo_categoria"]
            if modo_cat == "cooperativo":
                coletivas = set()
                for jj in estado["jogadores"].values():
                    coletivas |= jj["palavras"]
                total = len(estado["grade_palavras"])
                achou = len(coletivas)
            else:
                total = len(estado["grade_palavras"])
                achou = len(j["palavras"])
            resp["progresso"] = {"achadas": achou, "total": total}
            if achou >= total and total > 0:
                estado["fim"] = agora - 1
        return jsonify(resp)


@app.route("/api/sala/<sala_id>/dica", methods=["POST"])
def dica(sala_id):
    _, nome, erro = _exigir_login()
    if erro: return erro
    with LOCK:
        sala, err = _sala_ou_erro(sala_id)
        if err: return err
        estado = sala["estado"]
        if estado["fase"] != "jogando":
            return jsonify({"ok": False, "motivo": "fora de partida"})
        if estado["config"]["modo"] not in ("individual", "times", "caca"):
            return jsonify({"ok": False, "motivo": "modo sem dicas"})
        if nome not in estado["jogadores"]:
            return jsonify({"ok": False, "motivo": "desconhecido"})
        modo_cat = estado["config"]["modo_categoria"]
        if modo_cat == "cooperativo":
            ja = set()
            for jj in estado["jogadores"].values():
                ja |= jj["palavras"]
        else:
            ja = estado["jogadores"][nome]["palavras"]
        candidatas = [w for w in estado["grade_palavras"] if len(w) == 3 and w not in ja]
        if not candidatas:
            return jsonify({"ok": True, "palavra": None, "motivo": "achou todas de 3 letras"})
        return jsonify({"ok": True, "palavra": random.choice(candidatas)})


@app.route("/api/sala/<sala_id>/estado")
def get_estado(sala_id):
    _, nome, erro = _exigir_login()
    if erro: return erro
    with LOCK:
        sala, err = _sala_ou_erro(sala_id)
        if err: return err
        estado = sala["estado"]
        agora = time.time()
        if nome in estado["jogadores"]:
            estado["jogadores"][nome]["visto"] = agora
        _aplicar_sobrevivencia(estado)
        _checar_eliminados(estado)
        _checar_fim(estado)
        _limpar_ausentes(sala)

        modo = estado["config"]["modo"]
        modo_cat = estado["config"]["modo_categoria"]
        jogando = estado["fase"] == "jogando"

        restante = 0
        if jogando:
            if modo == "sobrevivencia" and nome in estado["jogadores"]:
                fim_ind = estado["jogadores"][nome].get("fim_individual", agora)
                restante = max(0, int(round(fim_ind - agora)))
            elif modo == "caca":
                restante = -1
            else:
                restante = max(0, int(estado["fim"] - agora))

        minhas = []
        vivo = True
        if nome in estado["jogadores"]:
            minhas = sorted(estado["jogadores"][nome]["palavras"])
            vivo = estado["jogadores"][nome].get("vivo", True)

        palavras_coletivas = None
        if modo_cat == "cooperativo" and jogando:
            col = set()
            for j in estado["jogadores"].values():
                col |= j["palavras"]
            palavras_coletivas = sorted(col)

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

        embaralhou_ha = None; cresceu_ha = None; celulas_novas = []
        if modo == "sobrevivencia" and jogando:
            t = estado["sobrev"].get("embaralhou_em", 0)
            if t and (agora - t) <= SOBREV_AVISO:
                embaralhou_ha = round(agora - t, 1)
            tc = estado["sobrev"].get("cresceu_em", 0)
            if tc and (agora - tc) <= 6:
                cresceu_ha = round(agora - tc, 1)
                celulas_novas = estado["sobrev"].get("celulas_novas", [])

        resp = {
            "fase": estado["fase"],
            "config": estado["config"],
            "sala_nome": sala["nome"],
            "host": estado["host"],
            "sou_host": estado["host"] == nome,
            "rodada": estado["rodada"],
            "grade": estado["grade"] if jogando else [],
            "linhas": estado["linhas"],
            "colunas": estado["colunas"],
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
        if palavras_coletivas is not None:
            resp["palavras_coletivas"] = palavras_coletivas
        if embaralhou_ha is not None:
            resp["embaralhou_ha"] = embaralhou_ha
            resp["aviso_embaralho"] = SOBREV_AVISO
        if cresceu_ha is not None:
            resp["cresceu_ha"] = cresceu_ha
            resp["celulas_novas"] = celulas_novas
        if modo == "caca" and jogando:
            if modo_cat == "cooperativo":
                col2 = set()
                for j in estado["jogadores"].values():
                    col2 |= j["palavras"]
                resp["progresso"] = {"achadas": len(col2), "total": len(estado["grade_palavras"])}
            else:
                resp["progresso"] = {"achadas": len(minhas), "total": len(estado["grade_palavras"])}
        return jsonify(resp)


@app.route("/api/sala/<sala_id>/palavras", methods=["GET", "POST"])
def palavras_extras(sala_id):
    _, _, erro = _exigir_login()
    if erro: return erro
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
    return jsonify({"ok": True, "acao": acao, "aplicadas": aplicadas,
                    "ignoradas": ignoradas, "total_extras": len(gc.EXTRAS)})


@app.route("/api/sala/<sala_id>/zerar_ranking", methods=["POST"])
def zerar_ranking(sala_id):
    _, _, erro = _exigir_login()
    if erro: return erro
    with LOCK:
        sala, err = _sala_ou_erro(sala_id)
        if err: return err
        sala["estado"]["ranking"] = {}
    return jsonify({"ok": True})


if __name__ == "__main__":
    import os
    porta = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=porta, debug=False)

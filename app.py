"""
Servidor Boggle multiplayer v2.
Config de sala: tamanho (3..10), duração, modo (individual/times), campeonato (nº partidas).
Sincronização por polling. Estado em memória, uma sala global.
"""
import time
import threading
from flask import Flask, request, jsonify, send_from_directory
import game_core as gc

app = Flask(__name__, static_folder="static")

LOCK = threading.Lock()

def estado_inicial():
    return {
        "fase": "lobby",           # lobby | jogando | resultado | fim_campeonato
        "config": {
            "tamanho": 4,
            "dificuldade": "medio",   # facil | medio | dificil
            "duracao": 180,
            "modo": "individual",  # individual | times
            "n_partidas": 1,       # campeonato: quantas partidas
        },
        "grade": [],
        "grade_info": {},
        "jogadores": {},           # nome -> {palavras:set, visto:ts, time:str|None}
        "inicio": 0,
        "fim": 0,
        "placar": {},              # placar individual da partida atual
        "placar_times": {},        # placar de times da partida atual
        "rodada": 0,               # nº da partida atual no campeonato (1-based)
        "vitorias": {},            # acumulado de sets: nome(ou time) -> nº vitórias
        "historico": [],           # [{rodada, vencedor}]
        # ranking da sessão (não zera entre campeonatos; só no /api/zerar_ranking)
        "ranking": {},             # nome -> {"total":int, "melhor":int, "partidas":int}
    }

estado = estado_inicial()


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

        # contabiliza vitória do set
        venc = _vencedor_da_partida()
        if venc is not None:
            estado["vitorias"][venc] = estado["vitorias"].get(venc, 0) + 1
            estado["historico"].append({"rodada": estado["rodada"], "vencedor": venc})

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


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/entrar", methods=["POST"])
def entrar():
    nome = (request.json or {}).get("nome", "").strip()[:16]
    if not nome:
        return jsonify({"erro": "nome vazio"}), 400
    with LOCK:
        if nome not in estado["jogadores"]:
            estado["jogadores"][nome] = {"palavras": set(), "visto": time.time(), "time": None}
        else:
            estado["jogadores"][nome]["visto"] = time.time()
    return jsonify({"ok": True, "nome": nome})


@app.route("/api/config", methods=["POST"])
def config():
    """Atualiza config da sala (só no lobby)."""
    data = request.json or {}
    with LOCK:
        if estado["fase"] not in ("lobby", "fim_campeonato"):
            return jsonify({"ok": False, "motivo": "so no lobby"})
        c = estado["config"]
        if "tamanho" in data:
            c["tamanho"] = max(3, min(10, int(data["tamanho"])))
        if "dificuldade" in data and data["dificuldade"] in ("facil", "medio", "dificil"):
            c["dificuldade"] = data["dificuldade"]
        if "duracao" in data:
            c["duracao"] = max(30, min(600, int(data["duracao"])))
        if "modo" in data and data["modo"] in ("individual", "times"):
            c["modo"] = data["modo"]
        if "n_partidas" in data:
            c["n_partidas"] = max(1, min(15, int(data["n_partidas"])))
    return jsonify({"ok": True, "config": estado["config"]})


@app.route("/api/time", methods=["POST"])
def set_time():
    """Define o time de um jogador (só no lobby)."""
    data = request.json or {}
    nome = data.get("nome", "")
    t = (data.get("time", "") or "").strip()[:16] or None
    with LOCK:
        if nome in estado["jogadores"]:
            estado["jogadores"][nome]["time"] = t
    return jsonify({"ok": True})


@app.route("/api/iniciar", methods=["POST"])
def iniciar():
    with LOCK:
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
        grade, qtd_palavras, maior = gc.gerar_grade(
            estado["config"]["tamanho"],
            dificuldade=estado["config"].get("dificuldade", "medio"),
        )
        estado["grade"] = grade
        estado["grade_info"] = {"palavras": qtd_palavras, "maior": maior}
        estado["inicio"] = time.time()
        estado["fim"] = estado["inicio"] + estado["config"]["duracao"]
        estado["rodada"] += 1
        for j in estado["jogadores"].values():
            j["palavras"] = set()
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
    with LOCK:
        _reset_para_lobby(full=True)
    return jsonify({"ok": True})


@app.route("/api/submeter", methods=["POST"])
def submeter():
    data = request.json or {}
    nome = data.get("nome", "")
    caminho = data.get("caminho", [])
    with LOCK:
        if estado["fase"] != "jogando":
            return jsonify({"ok": False, "motivo": "fora de partida"})
        if nome not in estado["jogadores"]:
            return jsonify({"ok": False, "motivo": "desconhecido"})
        ok, w = gc.validar_submissao(estado["grade"], caminho)
        if not ok:
            return jsonify({"ok": False, "palavra": w})
        ja = w in estado["jogadores"][nome]["palavras"]
        estado["jogadores"][nome]["palavras"].add(w)
        estado["jogadores"][nome]["visto"] = time.time()
        return jsonify({"ok": True, "palavra": w, "base": gc.pontos_base(w), "repetida": ja})


@app.route("/api/estado")
def get_estado():
    nome = request.args.get("nome", "")
    with LOCK:
        if nome in estado["jogadores"]:
            estado["jogadores"][nome]["visto"] = time.time()
        _checar_fim()
        _limpar_ausentes()

        restante = 0
        if estado["fase"] == "jogando":
            restante = max(0, int(estado["fim"] - time.time()))

        minhas = []
        if nome in estado["jogadores"]:
            minhas = sorted(estado["jogadores"][nome]["palavras"])

        jogadores_info = [
            {"nome": n, "time": j["time"]} for n, j in estado["jogadores"].items()
        ]

        return jsonify({
            "fase": estado["fase"],
            "config": estado["config"],
            "rodada": estado["rodada"],
            "grade": estado["grade"] if estado["fase"] == "jogando" else [],
            "grade_info": estado["grade_info"] if estado["fase"] == "jogando" else {},
            "restante": restante,
            "jogadores": jogadores_info,
            "minhas_palavras": minhas,
            "placar": estado["placar"],
            "placar_times": estado["placar_times"],
            "vitorias": estado["vitorias"],
            "historico": estado["historico"],
            "ranking": estado["ranking"],
        })


if __name__ == "__main__":
    import os
    porta = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=porta, debug=False)

"""
Servidor Boggle multiplayer — sincronização por polling (aguenta internet ruim).
Uma sala global simples (suficiente pra um grupo de amigos). Sem banco de dados:
estado em memória. Se o servidor reinicia, começa sala nova — ok pro caso de uso.
"""
import time
import threading
from flask import Flask, request, jsonify, send_from_directory
import game_core as gc

app = Flask(__name__, static_folder="static")

# ---- estado da sala (em memória) ----
LOCK = threading.Lock()
DURACAO = 180  # segundos por partida

estado = {
    "fase": "lobby",          # lobby | jogando | resultado
    "grade": [],
    "jogadores": {},          # nome -> {"palavras": set(), "visto": ts}
    "inicio": 0,
    "fim": 0,
    "placar": {},
    "rodada": 0,
}


def _reset_lobby():
    estado["fase"] = "lobby"
    estado["grade"] = []
    estado["inicio"] = 0
    estado["fim"] = 0
    estado["placar"] = {}
    for j in estado["jogadores"].values():
        j["palavras"] = set()


def _checar_fim():
    """Fecha a partida quando o tempo acaba e calcula o placar."""
    if estado["fase"] == "jogando" and time.time() >= estado["fim"]:
        jogadores = {n: j["palavras"] for n, j in estado["jogadores"].items()}
        estado["placar"] = gc.resolver_placar(jogadores)
        estado["fase"] = "resultado"


def _limpar_ausentes():
    """Remove quem sumiu por mais de 30s no lobby (não durante a partida)."""
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
            estado["jogadores"][nome] = {"palavras": set(), "visto": time.time()}
        else:
            estado["jogadores"][nome]["visto"] = time.time()
    return jsonify({"ok": True, "nome": nome})


@app.route("/api/iniciar", methods=["POST"])
def iniciar():
    with LOCK:
        estado["fase"] = "jogando"
        estado["grade"] = gc.gerar_grade()
        estado["inicio"] = time.time()
        estado["fim"] = estado["inicio"] + DURACAO
        estado["rodada"] += 1
        for j in estado["jogadores"].values():
            j["palavras"] = set()
        estado["placar"] = {}
    return jsonify({"ok": True})


@app.route("/api/nova", methods=["POST"])
def nova():
    with LOCK:
        _reset_lobby()
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
            return jsonify({"ok": False, "motivo": "jogador desconhecido"})
        ok, w, p = gc.validar_submissao(estado["grade"], caminho)
        if not ok:
            return jsonify({"ok": False, "palavra": w})
        ja = w in estado["jogadores"][nome]["palavras"]
        estado["jogadores"][nome]["palavras"].add(w)
        estado["jogadores"][nome]["visto"] = time.time()
        return jsonify({"ok": True, "palavra": w, "pontos": p, "repetida": ja})


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

        return jsonify({
            "fase": estado["fase"],
            "rodada": estado["rodada"],
            "grade": estado["grade"] if estado["fase"] != "lobby" else [],
            "restante": restante,
            "jogadores": list(estado["jogadores"].keys()),
            "minhas_palavras": minhas,
            "placar": estado["placar"],
        })


if __name__ == "__main__":
    import os
    porta = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=porta, debug=False)

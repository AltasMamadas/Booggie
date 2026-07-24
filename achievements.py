"""
Definição dos achievements (conquistas). A definição vive no código; o banco
guarda só o que cada perfil já desbloqueou (tabela profile_achievements).

Cada achievement tem uma função `cond(stats)` que recebe a linha de
profile_stats (dict, já com os jsonb desserializados) e devolve True quando a
conquista está cumprida. A avaliação é idempotente: rodamos todas as condições
após cada partida e inserimos as novas em profile_achievements.
"""


def _mode_games(stats, modo):
    return int((stats.get("mode_games") or {}).get(modo, 0))


def _mode_wins(stats, modo):
    return int((stats.get("mode_wins") or {}).get(modo, 0))


def _len_count(stats, tamanho):
    return int((stats.get("word_len_counts") or {}).get(str(tamanho), 0))


def _jogou_todos_modos(stats):
    mg = stats.get("mode_games") or {}
    return all(int(mg.get(m, 0)) > 0
               for m in ("individual", "times", "sobrevivencia", "duelo", "restricao", "caca"))


# id, nome, descrição, ícone (emoji), categoria, condição
ACHIEVEMENTS = [
    # --- Volume de palavras ---
    ("pal_10",    "Primeiras Palavras", "Ache 10 palavras no total",   "🔤", "Palavras",
     lambda s: s["total_words_found"] >= 10),
    ("pal_100",   "Caçador de Palavras", "Ache 100 palavras no total", "📖", "Palavras",
     lambda s: s["total_words_found"] >= 100),
    ("pal_1000",  "Dicionário Ambulante", "Ache 1.000 palavras",       "📚", "Palavras",
     lambda s: s["total_words_found"] >= 1000),
    ("pal_5000",  "Lenda das Letras",   "Ache 5.000 palavras",         "🏛️", "Palavras",
     lambda s: s["total_words_found"] >= 5000),

    # --- Palavras exclusivas (que ninguém mais achou na partida) ---
    ("exc_10",    "Original",           "10 palavras exclusivas",      "💡", "Exclusivas",
     lambda s: s["total_exclusivas"] >= 10),
    ("exc_100",   "Só Eu Vi",           "100 palavras exclusivas",     "🔦", "Exclusivas",
     lambda s: s["total_exclusivas"] >= 100),
    ("exc_500",   "Visionário",         "500 palavras exclusivas",     "👁️", "Exclusivas",
     lambda s: s["total_exclusivas"] >= 500),

    # --- Tamanho de palavra (maior palavra já achada) ---
    ("len_5",     "Encorpada",          "Ache uma palavra de 5+ letras", "✋", "Tamanho",
     lambda s: s["longest_word_len"] >= 5),
    ("len_7",     "Comprida",           "Ache uma palavra de 7+ letras", "📏", "Tamanho",
     lambda s: s["longest_word_len"] >= 7),
    ("len_9",     "Gigante",            "Ache uma palavra de 9+ letras", "🦕", "Tamanho",
     lambda s: s["longest_word_len"] >= 9),

    # --- Contagem por tamanho ---
    ("cnt5_25",   "Colecionador (5)",   "Ache 25 palavras de 5 letras", "🖐️", "Tamanho",
     lambda s: _len_count(s, 5) >= 25),
    ("cnt6_25",   "Colecionador (6)",   "Ache 25 palavras de 6 letras", "🎯", "Tamanho",
     lambda s: _len_count(s, 6) >= 25),

    # --- Jogos jogados ---
    ("jogo_1",    "Estreante",          "Jogue sua 1ª partida",        "🎬", "Jogos",
     lambda s: s["total_games"] >= 1),
    ("jogo_50",   "Veterano",           "Jogue 50 partidas",           "🎖️", "Jogos",
     lambda s: s["total_games"] >= 50),
    ("jogo_200",  "Insaciável",         "Jogue 200 partidas",          "🔥", "Jogos",
     lambda s: s["total_games"] >= 200),

    # --- Por modo ---
    ("mod_surv",  "Sobrevivente",       "10 jogos de Sobrevivência",   "⏳", "Modos",
     lambda s: _mode_games(s, "sobrevivencia") >= 10),
    ("mod_duel",  "Duelista",           "10 jogos de Duelo",           "⚔️", "Modos",
     lambda s: _mode_games(s, "duelo") >= 10),
    ("mod_time",  "Coletivo",           "10 jogos de Times",           "🤝", "Modos",
     lambda s: _mode_games(s, "times") >= 10),
    ("mod_rest",  "Estrategista",       "10 jogos de Restrição",       "🚧", "Modos",
     lambda s: _mode_games(s, "restricao") >= 10),
    ("mod_todos", "Explorador",         "Jogue todos os modos ao menos 1x", "🧭", "Modos",
     _jogou_todos_modos),

    # --- Vitórias ---
    ("vit_1",     "Primeira Vitória",   "Ganhe sua 1ª partida",        "🥇", "Vitórias",
     lambda s: s["total_wins"] >= 1),
    ("vit_25",    "Campeão",            "Ganhe 25 partidas",           "🏆", "Vitórias",
     lambda s: s["total_wins"] >= 25),
    ("vit_100",   "Imbatível",          "Ganhe 100 partidas",          "👑", "Vitórias",
     lambda s: s["total_wins"] >= 100),

    # --- Pontuação (melhor partida) ---
    ("pts_100",   "Pontuador",          "Faça 100 pts numa partida",   "💯", "Pontuação",
     lambda s: s["best_score"] >= 100),
    ("pts_250",   "Máquina de Pontos",  "Faça 250 pts numa partida",   "🚀", "Pontuação",
     lambda s: s["best_score"] >= 250),

    # --- Streaks ---
    ("stk_3",     "Constante",          "3 dias seguidos jogando",     "📅", "Streaks",
     lambda s: s.get("best_streak", 0) >= 3),
    ("stk_7",     "Semana Perfeita",    "7 dias seguidos jogando",     "🔥", "Streaks",
     lambda s: s.get("best_streak", 0) >= 7),
    ("stk_30",    "Dedicação Total",    "30 dias seguidos jogando",    "💎", "Streaks",
     lambda s: s.get("best_streak", 0) >= 30),
]

# índice por id para lookups
BY_ID = {a[0]: a for a in ACHIEVEMENTS}


def avaliar(stats):
    """Retorna o set de ids cujas condições estão cumpridas para esses stats."""
    cumpridos = set()
    for aid, _nome, _desc, _ic, _cat, cond in ACHIEVEMENTS:
        try:
            if cond(stats):
                cumpridos.add(aid)
        except Exception:
            pass
    return cumpridos


def catalogo():
    """Lista serializável (sem as funções) para o frontend."""
    return [
        {"id": aid, "nome": nome, "desc": desc, "icone": ic, "categoria": cat}
        for aid, nome, desc, ic, cat, _cond in ACHIEVEMENTS
    ]

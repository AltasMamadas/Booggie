"""
Acesso ao Postgres do Supabase (perfis, estatísticas agregadas, histórico
de partidas). Conexão direta via psycopg — sem ORM, condizente com o
resto do projeto.
"""
import os
import json
from contextlib import contextmanager
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
import achievements as ach

_DB_URL = os.environ.get("SUPABASE_DB_URL")
if not _DB_URL:
    raise RuntimeError("defina a env var SUPABASE_DB_URL")

# Pool único reutilizado por todo o processo — evita o custo de TCP+TLS+auth
# a cada query (caro no free tier do Supabase). Conexões abrem sob demanda.
_pool = ConnectionPool(
    _DB_URL,
    min_size=1,
    max_size=8,
    kwargs={"row_factory": dict_row},
    open=True,
)


@contextmanager
def _conn():
    with _pool.connection() as conn:
        yield conn


def criar_perfil(username, pin_hash):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into profiles (username, pin_hash) values (%s, %s) returning id",
                (username, pin_hash),
            )
            pid = cur.fetchone()["id"]
            cur.execute(
                "insert into profile_stats (profile_id) values (%s)", (pid,)
            )
        conn.commit()
    return pid


def buscar_perfil(username):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select id, username, pin_hash, avatar from profiles where username = %s",
                (username,),
            )
            return cur.fetchone()


def obter_avatar(profile_id):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("select avatar from profiles where id = %s", (profile_id,))
            r = cur.fetchone()
            return r["avatar"] if r else "a1"


def set_avatar(profile_id, avatar):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("update profiles set avatar = %s where id = %s",
                        (avatar, profile_id))
        conn.commit()


def obter_achievements(profile_id):
    """Ids desbloqueados + quando, para o perfil."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select achievement_id, unlocked_at from profile_achievements where profile_id = %s",
                (profile_id,),
            )
            rows = cur.fetchall()
    out = {}
    for r in rows:
        out[r["achievement_id"]] = r["unlocked_at"].isoformat() if r["unlocked_at"] else None
    return out


def obter_stats(profile_id):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select * from profile_stats where profile_id = %s", (profile_id,)
            )
            return cur.fetchone()


def obter_leaderboard():
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                select p.username,
                       p.avatar,
                       s.best_score,
                       s.total_wins,
                       s.total_games,
                       s.longest_word,
                       s.longest_word_len,
                       s.total_words_found,
                       s.total_word_chars,
                       s.total_play_seconds,
                       case when s.total_play_seconds > 0
                            then round(s.total_words_found::numeric / s.total_play_seconds, 3)
                            else 0 end as words_per_second,
                       case when s.total_words_found > 0
                            then round(s.total_word_chars::numeric / s.total_words_found, 2)
                            else 0 end as avg_word_length
                from profile_stats s
                join profiles p on p.id = s.profile_id
                where s.total_games > 0
                order by s.best_score desc
                limit 100
            """)
            return [dict(r) for r in cur.fetchall()]


def historico_partidas(profile_id, limit=20):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """select mode, team, score, words_found, longest_word,
                          words_per_second, won, duration_seconds,
                          played_at
                   from match_history
                   where profile_id = %s
                   order by played_at desc
                   limit %s""",
                (profile_id, limit),
            )
            rows = cur.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        if d.get("played_at"):
            d["played_at"] = d["played_at"].isoformat()
        result.append(d)
    return result


def persistir_partida(profile_id, dados):
    """
    dados: {mode, team, score, words_found, longest_word, avg_word_length,
            words_per_second, won, duration_seconds, exclusivas_count, word_len_hist}
    Faz insert em match_history + atualização incremental de profile_stats
    (incluindo os contadores jsonb) + desbloqueio de achievements, tudo numa
    transação. Read-modify-write sob FOR UPDATE — seguro dada a baixa
    concorrência por perfil (um jogador termina uma partida por vez).
    Retorna a lista de ids de achievements recém-desbloqueados.
    """
    longest_word_len = len(dados["longest_word"] or "")
    total_word_chars = round((dados["avg_word_length"] or 0) * dados["words_found"])
    modo = dados["mode"]
    exclusivas = int(dados.get("exclusivas_count", 0))
    hist = dados.get("word_len_hist") or {}
    novos = []
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """insert into match_history
                   (profile_id, mode, team, score, words_found, longest_word,
                    avg_word_length, words_per_second, won, duration_seconds)
                   values (%(profile_id)s, %(mode)s, %(team)s, %(score)s,
                           %(words_found)s, %(longest_word)s, %(avg_word_length)s,
                           %(words_per_second)s, %(won)s, %(duration_seconds)s)""",
                {k: dados[k] for k in ("mode", "team", "score", "words_found",
                                       "longest_word", "avg_word_length",
                                       "words_per_second", "won", "duration_seconds")}
                | {"profile_id": profile_id},
            )
            # read-modify-write dos stats (com os jsonb) sob lock de linha
            cur.execute("select * from profile_stats where profile_id = %s for update",
                        (profile_id,))
            s = cur.fetchone() or {}
            mode_games = dict(s.get("mode_games") or {})
            mode_wins = dict(s.get("mode_wins") or {})
            wlc = dict(s.get("word_len_counts") or {})
            mode_games[modo] = int(mode_games.get(modo, 0)) + 1
            if dados["won"]:
                mode_wins[modo] = int(mode_wins.get(modo, 0)) + 1
            for k, v in hist.items():
                wlc[str(k)] = int(wlc.get(str(k), 0)) + int(v)

            cur.execute(
                """update profile_stats set
                     total_games = total_games + 1,
                     total_wins = total_wins + %(won_inc)s,
                     best_score = greatest(best_score, %(score)s),
                     longest_word = case when %(longest_word_len)s > longest_word_len
                                         then %(longest_word)s else longest_word end,
                     longest_word_len = greatest(longest_word_len, %(longest_word_len)s),
                     total_words_found = total_words_found + %(words_found)s,
                     total_word_chars = total_word_chars + %(total_word_chars)s,
                     total_play_seconds = total_play_seconds + %(duration_seconds)s,
                     total_exclusivas = total_exclusivas + %(exclusivas)s,
                     mode_games = %(mode_games)s::jsonb,
                     mode_wins = %(mode_wins)s::jsonb,
                     word_len_counts = %(wlc)s::jsonb,
                     updated_at = now()
                   where profile_id = %(profile_id)s
                   returning *""",
                {
                    "profile_id": profile_id,
                    "won_inc": 1 if dados["won"] else 0,
                    "score": dados["score"],
                    "longest_word": dados["longest_word"],
                    "longest_word_len": longest_word_len,
                    "words_found": dados["words_found"],
                    "total_word_chars": total_word_chars,
                    "duration_seconds": dados["duration_seconds"],
                    "exclusivas": exclusivas,
                    "mode_games": json.dumps(mode_games),
                    "mode_wins": json.dumps(mode_wins),
                    "wlc": json.dumps(wlc),
                },
            )
            atualizado = cur.fetchone() or {}

            # desbloqueio de achievements com base nos stats já atualizados
            cumpridos = ach.avaliar(atualizado)
            if cumpridos:
                cur.execute(
                    "select achievement_id from profile_achievements where profile_id = %s",
                    (profile_id,),
                )
                ja = {r["achievement_id"] for r in cur.fetchall()}
                novos = [aid for aid in cumpridos if aid not in ja]
                for aid in novos:
                    cur.execute(
                        """insert into profile_achievements (profile_id, achievement_id)
                           values (%s, %s) on conflict do nothing""",
                        (profile_id, aid),
                    )
        conn.commit()
    return novos

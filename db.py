"""
Acesso ao Postgres do Supabase (perfis, estatísticas agregadas, histórico
de partidas). Conexão direta via psycopg — sem ORM, condizente com o
resto do projeto.
"""
import os
from contextlib import contextmanager
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

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
                "select id, username, pin_hash from profiles where username = %s",
                (username,),
            )
            return cur.fetchone()


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
            words_per_second, won, duration_seconds}
    """
    longest_word_len = len(dados["longest_word"] or "")
    total_word_chars = round((dados["avg_word_length"] or 0) * dados["words_found"])
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """insert into match_history
                   (profile_id, mode, team, score, words_found, longest_word,
                    avg_word_length, words_per_second, won, duration_seconds)
                   values (%(profile_id)s, %(mode)s, %(team)s, %(score)s,
                           %(words_found)s, %(longest_word)s, %(avg_word_length)s,
                           %(words_per_second)s, %(won)s, %(duration_seconds)s)""",
                {**dados, "profile_id": profile_id},
            )
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
                     updated_at = now()
                   where profile_id = %(profile_id)s""",
                {
                    "profile_id": profile_id,
                    "won_inc": 1 if dados["won"] else 0,
                    "score": dados["score"],
                    "longest_word": dados["longest_word"],
                    "longest_word_len": longest_word_len,
                    "words_found": dados["words_found"],
                    "total_word_chars": total_word_chars,
                    "duration_seconds": dados["duration_seconds"],
                },
            )
        conn.commit()

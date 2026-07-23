-- Perfis de jogador persistentes + historico/estatisticas de partidas

create table profiles (
  id uuid primary key default gen_random_uuid(),
  username text unique not null,
  pin_hash text not null,
  created_at timestamptz not null default now()
);

create table profile_stats (
  profile_id uuid primary key references profiles(id) on delete cascade,
  total_games int not null default 0,
  total_wins int not null default 0,
  best_score int not null default 0,
  longest_word text,
  longest_word_len int not null default 0,
  total_words_found bigint not null default 0,
  total_word_chars bigint not null default 0,
  total_play_seconds numeric not null default 0,
  updated_at timestamptz not null default now()
);
create index profile_stats_best_score_idx on profile_stats (best_score desc);
create index profile_stats_total_wins_idx on profile_stats (total_wins desc);

create table match_history (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references profiles(id) on delete cascade,
  played_at timestamptz not null default now(),
  mode text not null,
  team text,
  score int not null,
  words_found int not null,
  longest_word text,
  avg_word_length numeric,
  words_per_second numeric,
  won boolean not null,
  duration_seconds numeric
);
create index match_history_profile_idx on match_history (profile_id, played_at desc);

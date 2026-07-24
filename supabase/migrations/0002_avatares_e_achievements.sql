-- Avatar do perfil (id de avatar pré-pronto, ex.: 'a1'..'a12')
alter table profiles add column if not exists avatar text not null default 'a1';

-- Novos contadores agregados para achievements
alter table profile_stats add column if not exists total_exclusivas bigint not null default 0;
alter table profile_stats add column if not exists mode_games jsonb not null default '{}'::jsonb;
alter table profile_stats add column if not exists mode_wins jsonb not null default '{}'::jsonb;
alter table profile_stats add column if not exists word_len_counts jsonb not null default '{}'::jsonb;

-- Achievements desbloqueados por perfil (definição fica no código; aqui só o que já foi ganho)
create table if not exists profile_achievements (
  profile_id uuid not null references profiles(id) on delete cascade,
  achievement_id text not null,
  unlocked_at timestamptz not null default now(),
  primary key (profile_id, achievement_id)
);
create index if not exists profile_achievements_profile_idx on profile_achievements (profile_id);

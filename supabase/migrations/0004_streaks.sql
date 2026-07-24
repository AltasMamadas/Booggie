-- Streak de jogos diários
alter table profile_stats add column if not exists current_streak int not null default 0;
alter table profile_stats add column if not exists best_streak int not null default 0;
alter table profile_stats add column if not exists last_play_date date;

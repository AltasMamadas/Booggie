-- Bio do perfil (texto curto, opcional)
alter table profiles add column if not exists bio text not null default '';

-- Recuperação de senha: pergunta + resposta de segurança (hash bcrypt)
alter table profiles add column if not exists security_question text;
alter table profiles add column if not exists security_answer_hash text;

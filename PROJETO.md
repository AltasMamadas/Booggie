# Boggle Multiplayer — Contexto do Projeto

## O que é

Jogo de Boggle multiplayer rodando em Flask + Vanilla JS (single HTML file). Jogadores se conectam via polling (1,5s). Hospedado no Render (free tier). Banco de dados Supabase Postgres.

---

## Repositório

```
https://github.com/AltasMamadas/Booggie
```

Clone e entre na pasta:
```bash
git clone https://github.com/AltasMamadas/Booggie.git
cd Booggie
```

---

## Estrutura de arquivos

```
app.py          — servidor Flask (todas as rotas)
auth.py         — tokens JWT-like (itsdangerous) + bcrypt para PIN/senha
db.py           — acesso ao Postgres via psycopg (perfis, stats, leaderboard)
game_core.py    — lógica do jogo (grade, validação de palavra, placar)
solver.py       — encontra todas as palavras válidas de uma grade
requirements.txt
static/
  index.html    — frontend completo (CSS + HTML + JS num único arquivo)
  audio.js      — sistema de áudio (trilhas, SFX)
  *.mp3 / *.ogg
```

---

## Variáveis de ambiente obrigatórias

Crie um arquivo `.env` na raiz (já no `.gitignore`):

```env
SECRET_KEY=<sua_secret_key_aqui>
SUPABASE_DB_URL=<sua_connection_string_do_supabase>
```

> As credenciais reais estão no painel do Render (em Environment) e no painel do Supabase (Settings → Database → Connection string). **Não commite o `.env` real** — ele está no `.gitignore`.

O app **não usa python-dotenv** — você precisa exportar as vars antes de rodar:

```bash
# Linux/Mac
export SECRET_KEY=d13f1337...
export SUPABASE_DB_URL=postgresql://...
python app.py

# Windows PowerShell
$env:SECRET_KEY = "d13f1337..."
$env:SUPABASE_DB_URL = "postgresql://..."
python app.py
```

---

## Setup local

```bash
pip install -r requirements.txt
# setar env vars conforme acima
python app.py
# abre http://127.0.0.1:5000
```

---

## Banco de dados (Supabase)

- **Projeto:** veja o ID no painel do Supabase (região us-east-1)
- **Tabelas:**
  - `profiles` — id (uuid), username (unique), pin_hash, created_at
  - `profile_stats` — totais agregados por jogador (best_score, total_wins, longest_word, words_per_second, etc.)
  - `match_history` — histórico de partidas individuais
- A migration está em `supabase/migrations/0001_perfis.sql` (já aplicada)
- **Não precisa recriar o banco** — já existe e tem dados

---

## Deploy (Render)

- Serviço: Web Service, Python
- Start command: `gunicorn app:app`
- Env vars configuradas no painel do Render (as mesmas do `.env`)
- Free tier hiberna após 15 min de inatividade — primeira requisição demora ~30s

---

## Arquitetura do backend

### Autenticação
- `POST /api/perfil/criar` — cria conta com username + PIN de 4 dígitos
- `POST /api/perfil/login` — valida PIN com bcrypt, retorna token assinado
- Token: payload `{"pid": uuid, "u": username}` assinado com `itsdangerous.URLSafeSerializer`
- Enviado em todo request como `Authorization: Bearer <token>`
- Sem expiração (por enquanto)

### Multi-sala
- `salas = {}` — dict global com todas as salas ativas
- `sala_id` — 6 chars hex maiúsculo (ex.: `986EC2`)
- Cada sala: `{"id", "nome", "senha_hash", "estado", "criada_em", "vazia_desde"}`
- Salas vazias por >5 min são removidas automaticamente
- **Toda a lógica de jogo está em `estado`** — cada sala tem seu próprio `estado`

### Rotas principais
```
GET  /api/salas                    — lista salas disponíveis
POST /api/sala/criar               — cria sala {nome, senha?}
POST /api/sala/<id>/entrar         — entra na sala {senha?}

GET  /api/sala/<id>/estado         — poll (1,5s) — retorna tudo que o frontend precisa
POST /api/sala/<id>/config         — host muda configurações
POST /api/sala/<id>/iniciar        — host inicia partida
POST /api/sala/<id>/sair           — remove jogador
POST /api/sala/<id>/nova           — host volta ao lobby (encerra partida)
POST /api/sala/<id>/submeter       — submete caminho de letras
POST /api/sala/<id>/dica           — pede dica (prefixo da menor palavra não achada)
POST /api/sala/<id>/time           — define nome do time
POST /api/sala/<id>/palavras       — add/remove palavras customizadas
POST /api/sala/<id>/zerar_ranking  — zera ranking de sessão

GET  /api/leaderboard              — ranking global do Supabase
GET  /api/perfil/stats             — stats do jogador autenticado
```

---

## Arquitetura do frontend (`static/index.html`)

Telas (controladas por `show(nome)`):
- `login` — criar conta / entrar
- `home` — "Olá, [user]!" + 4 botões
- `criar-sala` — nome + senha opcional
- `entrar-sala` — lista de salas com scroll
- `lobby` — configurações + lista de jogadores
- `jogo` — tabuleiro interativo
- `resultado` — resultado de cada partida
- `fim` — fim de série (tela-fim)
- `config` — configurações de áudio, palavras, conta
- `stats` — estatísticas pessoais
- `leaderboard` — ranking global

Variáveis globais importantes:
```javascript
SALA_ID     // ID da sala atual ("986EC2" ou null)
SALA_NOME   // nome da sala
NOME        // username do jogador logado
PERFIL_TOKEN // token de auth
catSel      // "cooperativo" | "competitivo"
serieSel    // 1 | 3 | 5 | 7
```

Helper de API:
```javascript
api(url, body)         // fetch genérico com Authorization header
apiSala(path, body)    // atalho: api(`/api/sala/${SALA_ID}${path}`, body)
```

Auto-rejoin: ao carregar, tenta `localStorage.bg_perfil` (`{token, username, sala_id}`) e entra direto na sala anterior se existir.

---

## Modos de jogo

### Modo categoria
- **Competitivo** — jogadores competem entre si
- **Cooperativo** — todos encontram palavras juntos (Caça completa); `palavras_coletivas` é a união das palavras de todos; visível para o grupo inteiro

### Modos competitivos
- **Free-for-all** (`individual`) — palavra exclusiva vale dobro
- **Times** (`times`) — mesmo nome de time soma pontos
- **Sobrevivência** (`sobrevivencia`) — começa com 1:30, cada palavra devolve tempo, tabuleiro cresce depois embaralha

### Série
- 1 (partida única), 3, 5, 7
- Encerra quando alguém atinge N vitórias (não quando joga N partidas)

---

## O que foi feito nas últimas sessões

1. **Sistema de perfis** — Supabase + bcrypt + tokens stateless
2. **Leaderboard e stats** — 5 categorias (pontuação, vitórias, palavra, velocidade, total)
3. **Multi-sala** — `salas{}` substituiu `estado` global; rotas com `/api/sala/<id>/...`
4. **Homepage** — tela inicial com saudação, criar/entrar em sala
5. **Modo cooperativo** — `palavras_coletivas`, dica e progresso coletivos
6. **Série até N vitórias** — seletor 1/3/5/7

---

## O que ainda pode ser feito (ideias)

- Rate limiting no login (contra força bruta de PIN)
- Sala persistente (não some ao ficar vazia) — útil para grupos fixos
- Chat na sala / emojis de reação
- Histórico de partidas no perfil (`match_history` já existe no banco)
- Animação de confete no fim de série
- Compartilhar código da sala via link
- Modo espectador
- Palavras customizadas persistentes por perfil (hoje só duram a sessão)

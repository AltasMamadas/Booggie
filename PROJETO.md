# Lexico — Contexto do Projeto (atualizado jul/2026)

## O que é

**Lexico** é um jogo de palavras multiplayer (estilo Boggle) rodando em Flask + Vanilla JS (single HTML file). Jogadores se conectam via polling a cada 1,5s. Hospedado no Render (free tier). Banco de dados Supabase Postgres.

---

## Repositório

```
https://github.com/AltasMamadas/Booggie
```

---

## Estrutura de arquivos

```
app.py          — servidor Flask (todas as rotas)
auth.py         — tokens JWT-like (itsdangerous) + bcrypt para PIN/senha
db.py           — acesso ao Postgres via psycopg (perfis, stats, leaderboard)
game_core.py    — lógica do jogo (grade, validação, placar, trie de palavras)
solver.py       — encontra todas as palavras válidas de uma grade (busca na trie)
requirements.txt
static/
  index.html    — frontend completo (CSS + HTML + JS num único arquivo)
  audio.js      — sistema de áudio (trilhas, SFX)
  *.mp3 / *.ogg
supabase/
  migrations/
    0001_perfis.sql  — schema aplicado no Supabase
```

---

## Variáveis de ambiente

Crie `.env` na raiz (já no `.gitignore`):

```env
SECRET_KEY=<sua_secret_key>
SUPABASE_DB_URL=<connection_string_do_supabase>
```

As credenciais reais ficam no painel do Render (Environment) e no Supabase (Settings → Database). O app usa `python-dotenv` — basta ter o `.env` e rodar `python app.py`.

---

## Setup local

```bash
pip install -r requirements.txt
python app.py
# abre http://127.0.0.1:5000
```

Flask roda em modo debug localmente (auto-reload ao salvar arquivos).

---

## Banco de dados (Supabase Postgres)

Tabelas:
- `profiles` — id (uuid PK), username (unique), pin_hash, created_at
- `profile_stats` — totais agregados: best_score, total_wins, longest_word, total_words_found, total_word_chars, total_play_seconds, total_games, updated_at
- `match_history` — histórico de partidas: profile_id, mode, team, score, words_found, longest_word, avg_word_length, words_per_second, won, duration_seconds, played_at

---

## Deploy

- **Render** — Web Service Python, `gunicorn app:app`, free tier (hiberna após 15 min de inatividade, ~30s na primeira requisição)
- Push em `main` → deploy automático

---

## Arquitetura do backend

### Autenticação
- `POST /api/perfil/criar` — cria conta com username + PIN de 4 dígitos (bcrypt)
- `POST /api/perfil/login` — valida PIN, retorna token assinado com `itsdangerous`
- Token: `{"pid": uuid, "u": username}`, enviado como `Authorization: Bearer <token>` em todo request
- Sem expiração de token (por enquanto)

### Estado de salas
- `salas = {}` — dict global em memória (não persiste entre restarts)
- `sala_id` — 6 chars hex maiúsculo (ex.: `986EC2`)
- Cada sala: `{id, nome, senha_hash, estado, criada_em, vazia_desde}`
- **Thread de limpeza** roda a cada 30s: remove jogadores inativos (20s no lobby, 40s em jogo) e salas vazias há >60s
- Toda a lógica de jogo está em `estado` — cada sala tem o seu

### Rotas principais

```
GET  /api/salas                    — lista salas (roda limpeza antes)
POST /api/sala/criar               — cria sala {nome, senha?}
POST /api/sala/<id>/entrar         — entra na sala
GET  /api/sala/<id>/estado         — poll 1,5s — tudo que o frontend precisa
POST /api/sala/<id>/config         — host muda config
POST /api/sala/<id>/iniciar        — host inicia partida
POST /api/sala/<id>/sair           — remove jogador
POST /api/sala/<id>/nova           — host volta ao lobby
POST /api/sala/<id>/submeter       — submete palavra (caminho de células)
POST /api/sala/<id>/dica           — prefixo da menor palavra não achada
POST /api/sala/<id>/time           — define nome + cor do time (cores 1-6)
POST /api/sala/<id>/palavras       — add/remove palavras extras (GET lista todas)
POST /api/sala/<id>/zerar_ranking  — zera ranking de sessão
GET  /api/leaderboard              — ranking global do Supabase
GET  /api/perfil/stats             — stats do jogador autenticado
```

---

## Arquitetura do frontend (`static/index.html`)

Telas (controladas por `show(nome)`):
- `login` — criar conta / entrar com PIN
- `home` — saudação + botões principais
- `criar-sala` — nome + senha opcional
- `entrar-sala` — lista de salas abertas
- `lobby` — config da partida + jogadores + palavras extras
- `jogo` — tabuleiro interativo (arrastar para conectar letras)
- `resultado` — resultado de cada rodada
- `fim` — fim de série
- `config` — áudio, sensibilidade, conta, tema de cores
- `stats` — estatísticas pessoais (5 categorias)
- `leaderboard` — ranking global (5 categorias)

Variáveis globais importantes:
```javascript
SALA_ID, SALA_NOME, NOME, PERFIL_TOKEN
catSel    // "cooperativo" | "competitivo"
serieSel  // 1 | 3 | 5 | 7
corTimeSel // 1-6 (cor do time)
```

Auto-rejoin: ao carregar, verifica `localStorage.bg_perfil` e tenta reentrar na sala anterior automaticamente.

---

## Modos de jogo

### Categorias
- **Competitivo** — jogadores competem entre si
- **Cooperativo** — todos encontram palavras juntos; `palavras_coletivas` é compartilhada; dica e progresso são coletivos

### Modos competitivos
- **Free-for-all** (`individual`) — palavra exclusiva (só um jogador achou) vale dobro
- **Times** (`times`) — jogadores com mesmo nome de time somam pontos; cores de 1-6 (vermelho, azul, verde, amarelo, roxo, laranja)
- **Sobrevivência** (`sobrevivencia`) — começa com 1:30, cada palavra devolve tempo, tabuleiro cresce e embaralha
- **Caça** (`caca`) — sem relógio, achar todas as palavras do tabuleiro; dica disponível

### Série
- Seletor: 1 (partida única), 3, 5, 7
- Encerra quando alguém atinge N vitórias (não quando joga N rodadas)

---

## Funcionalidades implementadas

- **Perfis persistentes** — username + PIN, dados salvos no Supabase
- **Leaderboard global** — 5 categorias: pontuação, vitórias, palavra mais longa, palavras/min, total de palavras
- **Estatísticas pessoais** — mesmas 5 categorias + histórico de melhores
- **Multi-sala** — várias salas simultâneas independentes
- **Limpeza automática de salas** — thread de background + cleanup no listing
- **Pacotes de palavras** — NSFW, Geografia, Gen Alpha, Marcas (clique para ativar/desativar; adicionados via endpoint `/palavras`)
- **Palavras extras manuais** — adicionar/remover palavras por sala e sessão
- **Cores de time** — 6 cores predefinidas, badge colorido na lista de jogadores
- **Série até N vitórias** — 1/3/5/7
- **Tempo em segundos** — 30s a 600s (não mais em minutos)
- **Logo clicável** — volta ao home com confirmação
- **Tema escuro** — padrão dark navy + teal; personalizável
- **Customização de cores** — fundo, cards, bordas, accent, texto; 4 presets (Escuro, Roxo, Floresta, Clássico); salvo em localStorage
- **Auto-rejoin** — ao recarregar, volta para a sala automaticamente
- **Host badge** + **auto-reassignment** — host passa para próximo jogador se sair
- **Áudio** — trilhas de fundo, SFX, volume separado; suporte a música própria (upload local)
- **Sensibilidade do toque** — controle de precisão para selecionar letras diagonais

---

## O que NÃO foi feito ainda (ideias para próximos passos)

### Produto / UX
- Foto de perfil (Supabase Storage + coluna `profile_picture_url` em profiles)
- Chat na sala / emojis de reação durante o jogo
- Modo espectador (entrar numa sala sem jogar)
- Compartilhar código da sala via link direto (URL com `?sala=ABCD12`)
- Animação de confete/celebração no fim de série
- Histórico de partidas visível no perfil (`match_history` já existe no banco, mas sem tela)
- Sala persistente (não desaparece ao ficar vazia) — útil para grupos fixos
- Tutorial / onboarding para novos jogadores

### Técnico
- Rate limiting no login (contra força bruta de PIN de 4 dígitos)
- Palavras extras persistentes por perfil (hoje somem ao reiniciar o servidor)
- Migrar de polling para WebSockets (latência menor, menos carga no servidor)
- Recuperação de senha / troca de PIN
- Expiração / renovação de token
- Modo offline / PWA (jogar sozinho contra o relógio sem servidor)
- Internacionalização (inglês / outro idioma)

### Conteúdo
- Mais pacotes de palavras (temas: esportes, culinária, música...)
- Palavras customizadas persistentes por sala (hoje são globais, afetam todas as salas)
- Dicionário ajustável por região (BR vs PT)

---

## Decisões técnicas relevantes

- **Polling em vez de WebSocket** — simplicidade de deploy no Render free tier (sem suporte nativo a sockets persistentes sem worker dedicado)
- **Estado em memória** — zero latência de DB durante o jogo; trade-off: perde tudo se o servidor reiniciar
- **Token stateless** — evita query ao DB a cada poll (HMAC local); sem revogar tokens individualmente
- **Trie para validação** — `solver.py` constrói uma trie em memória; reconstrução custa ~35ms (feita em batch ao remover pacotes)
- **Single HTML file** — sem build tool, sem framework; tudo inline

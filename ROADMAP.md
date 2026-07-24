# 🎮 Boggle — Roadmap de Implementações

## 📋 Resumo das Ideias

Organizado por categoria, prioridade e esforço.

---

## 1️⃣ LOBBY — Palavras customizadas

### 1.1 Mover customizações de configurações para criação do lobby
**O quê:** Adicionar/remover palavras customizadas **apenas ao criar a sala**, não nas configurações gerais.

**Por quê:** Menos burocracia no lobby; palavras customizadas são específicas da sessão/sala.

**Esforço:** 🟡 Médio (2-3h)
- Backend: mover lógica de `/config` para `/sala/criar` 
- Frontend: remover campo de palavras customizadas de `tela-config`, adicionar em `tela-criar-sala`

**Dependências:** Nenhuma

**Status:** ⭕ Não iniciado

---

### 1.2 Pacotes de dicionário pré-prontos
**O quê:** Incluir opções ao criar sala:
- Base (padrão)
- Base + NSFW
- Base + Geografia
- Base + Gen Alpha
- Custom (usuario coloca manual)

**Por quê:** Variedade de temas; entretém diferentes públicos; mais fácil do que adicionar palavra por palavra.

**Esforço:** 🟡 Médio (3-4h)
- Backend: criar tabela/dict com listas de palavras por categoria em `game_core.py`
- Frontend: selector de dicionários em `tela-criar-sala`
- Integração: merge palavras base + selecionadas + custom antes de resolver_placar

**Dependências:** Nenhuma (independente)

**Status:** ⭕ Não iniciado

---

## 2️⃣ LOBBY — Times visuais (modo competitivo)

### 2.1 Botão "Criar/Escolher time" no lobby
**O quê:** No modo competitivo (Times), ao invés de digitar nome do time num input, ter:
- Input para nome do time
- Botão "Criar time"
- Cores predefinidas: vermelho, azul, verde, amarelo, roxo, laranja
- Exibir na lista de jogadores: `[nome_jogador] [time_badge com cor]`

**Por quê:** UX mais clara; cores visuais facilitam seguir o jogo.

**Esforço:** 🟡 Médio (2-3h)
- Frontend: redesenhar `tela-lobby` → input + botão + color picker
- Backend: adicionar `{nome: string, cor: string}` no schema de times
- Display: adicionar CSS para badges coloridas

**Dependências:** Nenhuma

**Status:** ⭕ Não iniciado

---

## 3️⃣ CONFIGURAÇÕES — Múltiplos painéis

### 3.1 Música própria — fix upload
**O quê:** Consertrar o upload de música customizada (hoje não funciona bem).

**Por quê:** Funcionalidade atual quebrada; usuários querem poder usar sua própria trilha sonora.

**Esforço:** 🟢 Pequeno (1h)
- Revisar `audio.js` → lógica de upload/play
- Testar em múltiplos navegadores
- Adicionar fallback se arquivo falhar

**Dependências:** Nenhuma

**Status:** ⭕ Não iniciado

**Notas:** Verificar `static/index.html` seção de áudio.

---

### 3.2 Foto de perfil
**O quê:** Adicionar upload de foto de perfil (profile picture).

**Por quê:** Identidade visual; torna o jogo mais pessoal.

**Esforço:** 🟠 Grande (4-6h)
- Backend: 
  - Nova coluna em `profiles` → `profile_picture_url` (text)
  - Endpoint: `POST /api/perfil/foto` → upload para cloud storage (Supabase Storage ou similar)
- Frontend:
  - Tela de config: adicionar input file com preview
  - Tela de perfil: exibir foto
  - Lobby: mostrar foto ao lado do nome de cada jogador
- Storage: configurar Supabase Storage ou usar Firebase

**Dependências:** Supabase Storage (precisa criar bucket)

**Status:** ⭕ Não iniciado

**Notas:** Considerar usar Supabase Storage (já é cliente) vs Firebase vs CloudFlare R2.

---

### 3.3 Modo escuro
**O quê:** Adicionar toggle de tema escuro/claro.

**Por quê:** Melhor experiência noturna; padrão moderno.

**Esforço:** 🟡 Médio (2-3h)
- Frontend:
  - Adicionar CSS vars para tema escuro
  - Toggle em `tela-config`
  - Salvar em `localStorage` → `bg_tema`
  - Aplicar ao carregar página
- CSS: revisar paleta de cores, criar versão escura

**Dependências:** Nenhuma

**Status:** ⭕ Não iniciado

---

## 4️⃣ UX/UI — Design & Visual

### 4.1 Revisar paleta de cores
**O quê:** Definir cores para:
- Primária (buttons, highlights)
- Secundária (backgrounds, borders)
- Tema claro + escuro
- Cores dos times (vermelho, azul, verde, etc.)

**Por quê:** Consistência visual; identidade de marca.

**Esforço:** 🟡 Médio (2-3h)
- Ficar com quem? (designer ou você decide)
- Criar variáveis CSS com paleta
- Testar contraste (acessibilidade)

**Dependências:** Nenhuma (pode ser feito em paralelo)

**Status:** ⭕ Não iniciado

---

### 4.2 Arte/Inspiração visual
**O quê:** Definir estilo visual (flat, neumorphic, glassmorphic, etc.) e buscar inspiração em jogos similares.

**Esforço:** 🟠 Grande (variável)
- Pesquisa: Wordle, Scrabble, Quordle layouts
- Mockups: redesenhar telas em Figma/papel
- Implementação: atualizar CSS + SVG se necessário

**Dependências:** Paleta de cores (4.1)

**Status:** ⭕ Não iniciado

---

## 5️⃣ UNIDADES — Tempo em segundos

### 5.1 Alterar duracao de partida para segundos
**O quê:** Mudar seletor de tempo de `1 min, 2 min, 3 min, 5 min` para segundos:
- 30s, 60s, 90s, 120s, 180s, 300s (ou customizável)

**Por quê:** Mais flexibilidade; melhor para testes rápidos.

**Esforço:** 🟢 Pequeno (1h)
- Frontend: trocar labels em `tela-lobby`
- Backend: verificar se já usa segundos internamente (sim, usa)
- Testes: confirmar que timers funcionam

**Dependências:** Nenhuma

**Status:** ⭕ Não iniciado

---

## 6️⃣ NAVEGAÇÃO — Logo volta ao home

### 6.1 Logo (Boggle) clicável → volta ao home
**O quê:** Clique no nome "BOGGLE" no canto superior esquerdo volta para `tela-home`.

**Por quê:** Padrão UX; escape rápido de qualquer tela.

**Esforço:** 🟢 Pequeno (15 min)
- Frontend: adicionar click handler ao logo
- Lógica: `show("home")` + limpar `SALA_ID`

**Dependências:** Nenhuma

**Status:** ⭕ Não iniciado

---

## 📊 Mapa de Prioridade

### 🚀 Fase 1 (Rápido, Alto Impacto)
1. **Logo clicável** (6.1) — 15 min ⭐
2. **Tempo em segundos** (5.1) — 1h ⭐
3. **Modo escuro** (3.3) — 2-3h ⭐
4. **Mover palavras customizadas** (1.1) — 2-3h
5. **Times com cores** (2.1) — 2-3h

**Tempo total:** ~10-12h

---

### 🎨 Fase 2 (Design & Estrutura)
1. **Paleta de cores** (4.1) — 2-3h
2. **Arte/Inspiração** (4.2) — 4-6h (variável)

**Tempo total:** ~6-9h

---

### 🔧 Fase 3 (Features complexas)
1. **Música própria fix** (3.1) — 1h
2. **Pacotes de dicionário** (1.2) — 3-4h
3. **Foto de perfil** (3.2) — 4-6h

**Tempo total:** ~8-11h

---

## 🎯 Recomendação de Ordem

**Semana 1 (Fase 1 — rápido):**
```
Dia 1: Logo clicável + Tempo em segundos + Modo escuro
Dia 2: Mover palavras customizadas + Times com cores
```
→ Lançar update rápido, testar feedback

**Semana 2+ (Fase 2 & 3):**
- Paleta de cores + Art/Design
- Pacotes de dicionário
- Foto de perfil

---

## 💡 Notas Técnicas

### Supabase Storage (para fotos de perfil)
Se for fazer 3.2 (foto de perfil):
```sql
-- Nova coluna em profiles
ALTER TABLE profiles ADD COLUMN profile_picture_url TEXT;

-- Supabase Storage bucket
CREATE BUCKET IF NOT EXISTS profile-pictures
```

### CSS Vars para tema escuro
```css
:root {
  --cor-primaria: #8B4513;
  --cor-secundaria: #D2B48C;
  --bg-light: #FFF8DC;
  --text-light: #000;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg-light: #1a1a1a;
    --text-light: #FFF;
  }
}
```

### Paleta de times (sugestão)
- 🔴 Vermelho: `#E63946`
- 🔵 Azul: `#457B9D`
- 🟢 Verde: `#2A9D8F`
- 🟡 Amarelo: `#F4A261`
- 🟣 Roxo: `#9D84B7`
- 🟠 Laranja: `#F77F00`

---

## 📝 Status Geral

| Fase | Tarefas | Status |
|------|---------|--------|
| 1 | 5 tarefas | ⭕ Não iniciado |
| 2 | 2 tarefas | ⭕ Não iniciado |
| 3 | 3 tarefas | ⭕ Não iniciado |

**Total:** 10 tarefas, ~24-32 horas de trabalho

---

## 🔗 Links úteis

- Figma (se usar): https://figma.com
- Supabase Storage docs: https://supabase.com/docs/guides/storage
- Paleta de cores: https://coolors.co

---

Quer começar com a Fase 1? Posso implementar já! 🚀

/* ================================================================
   Áudio do Boggle — trilhas originais geradas por código (Web Audio).
   Nada de arquivos externos: as músicas são sequências compostas aqui,
   então não há questão de direitos autorais. O jogador pode carregar
   um .mp3 próprio pelas Configurações.
   ================================================================ */
const Audio2 = (() => {
  let ctx = null;
  let musicaGain = null, sfxGain = null;
  let tocando = false;
  let loopTimer = null;
  let trilhaAtual = 0;
  let mp3El = null;          // <audio> quando o usuário carrega o próprio
  let usandoMp3 = false;

  const cfg = {
    musicaOn: true,
    sfxOn: true,
    volMusica: 0.35,
    volSfx: 0.5,
  };

  function init() {
    if (ctx) return;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    ctx = new AC();
    musicaGain = ctx.createGain();
    sfxGain = ctx.createGain();
    musicaGain.gain.value = cfg.volMusica;
    sfxGain.gain.value = cfg.volSfx;
    musicaGain.connect(ctx.destination);
    sfxGain.connect(ctx.destination);
  }

  // navegadores exigem gesto do usuário pra liberar áudio
  function destravar() {
    init();
    if (ctx && ctx.state === "suspended") ctx.resume();
  }

  // ---------- síntese básica ----------
  function nota(freq, inicio, dur, tipo, ganho, destino) {
    if (!ctx) return;
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = tipo || "sine";
    osc.frequency.value = freq;
    // envelope suave pra não estalar
    g.gain.setValueAtTime(0, inicio);
    g.gain.linearRampToValueAtTime(ganho, inicio + 0.02);
    g.gain.exponentialRampToValueAtTime(0.001, inicio + dur);
    osc.connect(g);
    g.connect(destino || musicaGain);
    osc.start(inicio);
    osc.stop(inicio + dur + 0.05);
  }

  function ruido(inicio, dur, ganho, destino) {
    if (!ctx) return;
    const n = Math.floor(ctx.sampleRate * dur);
    const buf = ctx.createBuffer(1, n, ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    const g = ctx.createGain();
    g.gain.value = ganho;
    src.connect(g); g.connect(destino || sfxGain);
    src.start(inicio);
  }

  // frequência de uma nota MIDI
  const f = (m) => 440 * Math.pow(2, (m - 69) / 12);

  /* ---------- 3 trilhas originais ----------
     Cada uma retorna a duração do ciclo, e agenda as notas a partir de t0. */

  // 1) "Passeio" — leve, dedilhado, maior
  function trilhaPasseio(t0) {
    const bpm = 96, b = 60 / bpm;
    const acordes = [
      [60, 64, 67], [57, 60, 64], [65, 69, 72], [55, 59, 62],
    ];
    acordes.forEach((ac, i) => {
      const t = t0 + i * b * 4;
      // baixo
      nota(f(ac[0] - 24), t, b * 1.8, "triangle", 0.20);
      nota(f(ac[0] - 24), t + b * 2, b * 1.6, "triangle", 0.16);
      // arpejo
      const arp = [ac[0], ac[1], ac[2], ac[1]];
      for (let k = 0; k < 8; k++) {
        const nt = arp[k % 4] + (k >= 4 ? 12 : 0);
        nota(f(nt), t + k * b * 0.5, b * 0.45, "sine", 0.11);
      }
    });
    return b * 16;
  }

  // 2) "Relógio" — pulsante, tensa, menor (boa pros últimos segundos)
  function trilhaRelogio(t0) {
    const bpm = 112, b = 60 / bpm;
    const base = [57, 57, 60, 55];
    base.forEach((raiz, i) => {
      const t = t0 + i * b * 4;
      nota(f(raiz - 24), t, b * 3.5, "sawtooth", 0.10);
      for (let k = 0; k < 4; k++) {
        nota(f(raiz + 12), t + k * b, b * 0.25, "square", 0.055);
      }
      nota(f(raiz + 15), t + b * 2, b * 1.2, "sine", 0.10);
      nota(f(raiz + 19), t + b * 3, b * 0.9, "sine", 0.09);
    });
    return b * 16;
  }

  // 3) "Bosque" — ambiente calmo, notas espaçadas
  function trilhaBosque(t0) {
    const b = 0.75;
    const esc = [60, 62, 65, 67, 69, 72, 74];
    for (let i = 0; i < 16; i++) {
      const t = t0 + i * b;
      if (i % 4 === 0) nota(f(48 + (i % 8)), t, b * 3, "sine", 0.16);
      const n = esc[(i * 3) % esc.length];
      nota(f(n), t, b * 1.4, "sine", 0.085);
      if (i % 3 === 0) nota(f(n + 12), t + b * 0.5, b * 0.9, "triangle", 0.05);
    }
    return b * 16;
  }

  const TRILHAS = [
    { nome: "Passeio", fn: trilhaPasseio },
    { nome: "Relógio", fn: trilhaRelogio },
    { nome: "Bosque", fn: trilhaBosque },
  ];

  function nomesTrilhas() { return TRILHAS.map(t => t.nome); }

  // ---------- controle de música ----------
  function tocarMusica(indice) {
    destravar();
    if (!cfg.musicaOn) return;
    pararMusica();
    if (usandoMp3 && mp3El) {
      mp3El.volume = cfg.volMusica;
      mp3El.loop = true;
      mp3El.play().catch(() => {});
      tocando = true;
      return;
    }
    if (!ctx) return;
    trilhaAtual = (indice != null) ? indice : trilhaAtual;
    tocando = true;
    const agenda = () => {
      if (!tocando || !ctx) return;
      const dur = TRILHAS[trilhaAtual].fn(ctx.currentTime + 0.05);
      loopTimer = setTimeout(agenda, dur * 1000 - 80);
    };
    agenda();
  }

  function pararMusica() {
    tocando = false;
    if (loopTimer) { clearTimeout(loopTimer); loopTimer = null; }
    if (mp3El) { try { mp3El.pause(); } catch (e) {} }
  }

  function carregarMp3(file) {
    const url = URL.createObjectURL(file);
    if (!mp3El) mp3El = new Audio();
    mp3El.src = url;
    usandoMp3 = true;
    return file.name;
  }

  function usarTrilhaInterna(i) {
    usandoMp3 = false;
    trilhaAtual = i;
  }

  // ---------- efeitos sonoros ----------
  function sfx(tipo) {
    if (!cfg.sfxOn) return;
    destravar();
    if (!ctx) return;
    const t = ctx.currentTime;
    if (tipo === "select") {
      nota(f(72), t, 0.07, "sine", 0.16, sfxGain);
    } else if (tipo === "valida") {
      [72, 76, 79].forEach((n, i) =>
        nota(f(n), t + i * 0.05, 0.18, "sine", 0.16, sfxGain));
    } else if (tipo === "invalida") {
      nota(f(55), t, 0.16, "sawtooth", 0.10, sfxGain);
      nota(f(52), t + 0.07, 0.18, "sawtooth", 0.09, sfxGain);
    } else if (tipo === "repetida") {
      nota(f(64), t, 0.10, "triangle", 0.10, sfxGain);
    } else if (tipo === "inicio") {
      [60, 64, 67, 72].forEach((n, i) =>
        nota(f(n), t + i * 0.09, 0.3, "triangle", 0.16, sfxGain));
    } else if (tipo === "fim") {
      [72, 67, 64, 60].forEach((n, i) =>
        nota(f(n), t + i * 0.12, 0.45, "sine", 0.18, sfxGain));
    } else if (tipo === "tique") {
      ruido(t, 0.04, 0.10);
    } else if (tipo === "vitoria") {
      [60, 64, 67, 72, 76].forEach((n, i) =>
        nota(f(n), t + i * 0.1, 0.5, "triangle", 0.17, sfxGain));
    }
  }

  // ---------- config ----------
  function setMusica(on) {
    cfg.musicaOn = on;
    if (!on) pararMusica();
  }
  function setSfx(on) { cfg.sfxOn = on; }
  function setVolMusica(v) {
    cfg.volMusica = v;
    if (musicaGain) musicaGain.gain.value = v;
    if (mp3El) mp3El.volume = v;
  }
  function setVolSfx(v) {
    cfg.volSfx = v;
    if (sfxGain) sfxGain.gain.value = v;
  }
  function estaTocando() { return tocando; }

  return {
    destravar, tocarMusica, pararMusica, sfx,
    setMusica, setSfx, setVolMusica, setVolSfx,
    nomesTrilhas, usarTrilhaInterna, carregarMp3, estaTocando,
    cfg,
  };
})();

'use strict';

const $ = (s) => document.querySelector(s);
const el = (tag, cls, txt) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (txt !== undefined) n.textContent = txt;
  return n;
};
const num = (v, d = 5) => (v === null || v === undefined) ? '—'
  : Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: d });

const state = {
  snapshot: null,
  recent: [],
  open: [],
  assets: [],
};
window.__sigState = state;

// ---------- tabs ----------
document.querySelectorAll('.tab').forEach((t) => {
  t.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach((x) => x.classList.remove('active'));
    document.querySelectorAll('.view').forEach((x) => x.classList.remove('active'));
    t.classList.add('active');
    $('#view-' + t.dataset.view).classList.add('active');
    if (t.dataset.view === 'stats') loadStats();
    if (t.dataset.view === 'history') loadHistory();
  });
});

// ---------- websocket ----------
let ws;
function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => { $('#conn').className = 'dot on'; };
  ws.onclose = () => {
    $('#conn').className = 'dot off';
    $('#feedTag').textContent = 'reconectando…';
    setTimeout(connect, 2000);
  };
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === 'tick') {
      state.snapshot = msg.data;
      renderLive();
    } else if (msg.type === 'signal') {
      toast(`Novo sinal: ${msg.data.symbol} ${msg.data.direction.toUpperCase()}`);
      loadRecent();
    } else if (msg.type === 'settled') {
      const r = msg.data.result;
      toast(`${msg.data.symbol}: ${r.toUpperCase()}`, r === 'win' ? 'ok' : 'bad');
      loadRecent();
    }
  };
}
connect();

function toast(text, kind) {
  const t = el('div', 'card');
  t.style.cssText = 'position:fixed;right:20px;bottom:20px;z-index:99;min-width:220px;' +
    'border-top:3px solid ' + (kind === 'ok' ? 'var(--call)' :
      kind === 'bad' ? 'var(--put)' : 'var(--accent)');
  t.textContent = text;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

// ---------- render: ao vivo ----------
function renderBands(s) {
  const bar = $('#bandBar');
  const bands = s.confidence_bands || [];
  if (!bands.length) { bar.innerHTML = ''; return; }
  const nomes = { 1: 'M1', 5: 'M5', 15: 'M15' };
  bar.innerHTML = '<span class="lbl">Regra de emissão:</span>' +
    bands.map((b) => {
      const label = nomes[b.expiry_min] || b.expiry_min + 'm';
      return `<span class="band">${label} só acima de <b>${b.above}%</b></span>`;
    }).join('') +
    '<span class="lbl" style="margin-left:auto">abaixo disso não emite</span>';
}

function renderLive() {
  const s = state.snapshot;
  if (!s) return;
  state.assets = s.assets;
  renderBands(s);

  const feeds = s.feeds || {};
  const parts = [];
  if (feeds.iq?.available) parts.push('IQ Option');
  if (feeds.sim_otc?.available) parts.push('OTC sintético');
  $('#feedTag').textContent = parts.length ? 'fontes: ' + parts.join(' · ') : 'sem feeds';

  const open = state.open.length;
  const kpis = [
    { k: 'Ativos monitorados', v: s.assets.length },
    { k: 'Sinais abertos', v: open },
    { k: 'Sinais gravados', v: state.recentCount ?? '—' },
    { k: 'Última varredura',
      v: s.last_scan ? new Date(s.last_scan * 1000).toLocaleTimeString('pt-BR') : '—' },
  ];
  const kp = $('#liveKpis');
  kp.innerHTML = '';
  kpis.forEach((k) => {
    const d = el('div', 'kpi');
    d.append(el('div', 'k', k.k), el('div', 'v', String(k.v)));
    kp.append(d);
  });

  const mf = $('#marketFilter').value;
  const sf = $('#symbolFilter').value.trim().toUpperCase();
  const grid = $('#assetGrid');
  grid.innerHTML = '';
  const list = s.assets.filter((a) =>
    (!mf || a.market === mf) && (!sf || a.symbol.includes(sf)));

  if (!list.length) {
    grid.append(el('div', 'empty', 'Nenhum ativo com esse filtro.'));
    return;
  }

  const bands = s.confidence_bands || [];
  function eligibleExpiry(conf) {
    for (const b of bands) {
      if (conf >= b.above) return b.expiry_min;
    }
    return null;
  }

  list.forEach((a) => {
    const as = s.assessments[a.symbol];
    const dir = as?.direction || 'flat';
    const conf = as?.confidence ?? 0;
    if (dir === 'flat' || eligibleExpiry(conf) === null) return;
    const px = s.prices[a.symbol];
    const card = el('div', 'asset ' + dir);
    const r1 = el('div', 'row1');
    r1.append(el('span', 'sym', a.symbol), el('span', 'px', num(px, 6)));
    card.append(r1);
    card.append(el('div', 'name', a.name));

    const dl = el('div', 'dirline');
    dl.append(el('span', 'dir ' + dir,
      dir === 'call' ? '▲ CALL' : dir === 'put' ? '▼ PUT' : '· neutro'));
    dl.append(el('span', 'meta', conf + '% confiança'));
    card.append(dl);

    const bar = el('div', 'bar');
    const fill = el('i');
    fill.style.width = Math.min(100, conf) + '%';
    bar.append(fill);
    card.append(bar);

    const bd = el('div', 'badges');
    bd.append(el('span', 'badge', a.market));
    bd.append(el('span', 'badge', 'payout ' + a.payout + '%'));
    bd.append(el('span', 'badge ' + (a.verified ? 'ok' : 'no'),
      a.verified ? 'auditável' : 'não auditável'));
    card.append(bd);

    if (as?.reasons?.length) {
      const ul = el('ul', 'reasons');
      as.reasons.slice(0, 3).forEach((r) => ul.append(el('li', '', r)));
      card.append(ul);
    }
    grid.append(card);
  });

  const errs = Object.entries(s.errors || {});
  $('#scanInfo').textContent = errs.length
    ? errs.length + ' ativo(s) sem dados'
    : 'todos os ativos respondendo';
}

function signalCard(sg) {
  const c = el('div', 'card ' + (sg.direction || (sg.result === 'win' ? '' : 'put')));
  const head = el('div', 'head');
  head.append(el('span', 't', sg.symbol), el('span', 'd',
    new Date(sg.opened_at * 1000).toLocaleString('pt-BR')));
  c.append(head);

  const dl = el('div', 'dirline');
  dl.append(el('span', 'pill ' + sg.direction,
    sg.direction === 'call' ? 'CALL' : 'PUT'));
  dl.append(el('span', 'meta', `${sg.expiry_min} min · ${sg.confidence}%`));
  if (sg.result) {
    dl.append(el('span', 'pill ' + sg.result,
      sg.result === 'win' ? 'GANHO' : sg.result === 'loss' ? 'PERDA' : 'EMPATE'));
  } else {
    dl.append(el('span', 'pill open', 'ABERTO'));
  }
  c.append(dl);

  const m = el('div', 'meta');
  m.textContent = `Entrada ${num(sg.entry_price, 6)}` +
    (sg.exit_price ? ` → saída ${num(sg.exit_price, 6)}` : '') +
    ` · ${sg.source}` + (sg.verified ? '' : ' · não auditável');
  c.append(m);

  if (sg.expires_at && !sg.result) {
    const left = el('div', 'meta');
    left.dataset.expires = sg.expires_at;
    c.append(left);
  }

  if (sg.reasons?.length) {
    const ul = el('ul', 'reasons');
    sg.reasons.slice(0, 3).forEach((r) => ul.append(el('li', '', r)));
    c.append(ul);
  }
  return c;
}

function minConfForExpiry(expiryMin) {
  const bands = (state.snapshot && state.snapshot.confidence_bands) || [];
  for (const b of bands) {
    if (b.expiry_min === expiryMin) return b.above;
  }
  if (expiryMin <= 1) return 95;
  return 80;
}

function passesConfidenceFilter(sg) {
  const threshold = minConfForExpiry(sg.expiry_min);
  return (sg.confidence ?? 0) >= threshold;
}

async function renderSignals() {
  const o = $('#openSignals');
  o.innerHTML = '';
  try {
    const res = await fetch('/api/signals/open');
    const j = await res.json();
    const open = (j.signals || []).filter(passesConfidenceFilter);
    state.open = open;
    if (!open.length) o.append(el('div', 'empty', 'Nenhum sinal aberto agora.'));
    else open.forEach((sg) => o.append(signalCard(sg)));
  } catch {
    o.append(el('div', 'empty', 'Não foi possível carregar sinais abertos.'));
  }

  const r = $('#recentSignals');
  r.innerHTML = '';
  const settled = state.recent
    .filter((x) => x.status !== 'open' && passesConfidenceFilter(x))
    .slice(0, 12);
  if (!settled.length) {
    r.append(el('div', 'empty',
      'Ainda sem sinais liquidados acima do limiar de confiança.'));
  }
  settled.forEach((sg) => r.append(signalCard(sg)));
}

async function loadRecent() {
  const res = await fetch('/api/signals?limit=60');
  const j = await res.json();
  state.recent = j.signals;
  state.recentCount = j.signals.length;
  renderSignals();
}

// ---------- historico ----------
async function loadHistory() {
  const sym = $('#histSymbol').value.trim().toUpperCase();
  const lim = $('#histLimit').value;
  const url = '/api/signals?limit=' + lim + (sym ? '&symbol=' + sym : '');
  const j = await (await fetch(url)).json();
  const wrap = $('#historyTable');
  if (!j.signals.length) {
    wrap.innerHTML = '<div class="empty">Nenhum sinal registrado ainda.</div>';
    return;
  }
  const t = el('table');
  t.innerHTML = '<thead><tr><th>#</th><th>Ativo</th><th>Hora</th>' +
    '<th>Direção</th><th>Exp</th><th>Conf</th><th>Entrada</th>' +
    '<th>Saída</th><th>Resultado</th><th>Fonte</th></tr></thead>';
  const tb = el('tbody');
  j.signals.forEach((s) => {
    const tr = el('tr');
    tr.innerHTML =
      `<td>${s.id}</td><td>${s.symbol}</td>` +
      `<td>${new Date(s.opened_at * 1000).toLocaleString('pt-BR')}</td>` +
      `<td><span class="pill ${s.direction}">${s.direction.toUpperCase()}</span></td>` +
      `<td>${s.expiry_min}m</td><td>${s.confidence}%</td>` +
      `<td>${num(s.entry_price, 6)}</td><td>${s.exit_price ? num(s.exit_price, 6) : '—'}</td>` +
      `<td>${s.result ? `<span class="pill ${s.result}">${s.result.toUpperCase()}</span>` :
        '<span class="pill open">ABERTO</span>'}</td>` +
      `<td>${s.source}${s.verified ? '' : ' ⚠'}</td>`;
    tb.append(tr);
  });
  t.append(tb);
  wrap.innerHTML = '';
  wrap.append(t);
}
$('#histLoad').addEventListener('click', loadHistory);

// ---------- track record ----------
async function loadStats() {
  const j = await (await fetch('/api/stats')).json();
  const kp = $('#statKpis');
  kp.innerHTML = '';
  const items = [
    { k: 'Taxa de acerto', v: j.win_rate + '%', s: `${j.wins}W / ${j.losses}L` },
    { k: 'Sinais liquidados', v: j.settled, s: j.open + ' em aberto' },
    { k: 'Empates', v: j.ties, s: 'fora do denominador' },
    { k: 'Base decidida', v: j.decided, s: 'ganhos + perdas' },
  ];
  items.forEach((i) => {
    const d = el('div', 'kpi');
    d.append(el('div', 'k', i.k), el('div', 'v', String(i.v)),
      el('div', 's', i.s));
    kp.append(d);
  });

  const bm = $('#marketBreakdown');
  bm.innerHTML = '';
  const keys = Object.keys(j.by_market || {});
  if (!keys.length) {
    bm.innerHTML = '<div class="empty">Sem resultados liquidados ainda.</div>';
    return;
  }
  const t = el('table');
  t.innerHTML = '<thead><tr><th>Mercado</th><th>Ganhos</th><th>Perdas</th>' +
    '<th>Empates</th><th>Taxa</th></tr></thead>';
  const tb = el('tbody');
  keys.forEach((k) => {
    const m = j.by_market[k];
    const tr = el('tr');
    tr.innerHTML = `<td>${k}</td><td>${m.win}</td><td>${m.loss}</td>` +
      `<td>${m.tie}</td><td>${m.win_rate}%</td>`;
    tb.append(tr);
  });
  t.append(tb);
  bm.append(t);
}

// ---------- backtest ----------
function fillSymbolSelect() {
  const sel = $('#btSymbol');
  if (sel.options.length) return;
  fetch('/api/assets').then((r) => r.json()).then((j) => {
    j.assets.forEach((a) => {
      const o = el('option', '', a.symbol);
      o.value = a.symbol;
      sel.append(o);
    });
  });
}
fillSymbolSelect();

$('#backtestForm').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const out = $('#backtestOut');
  out.innerHTML = '<div class="empty">Rodando…</div>';
  const body = {
    symbol: $('#btSymbol').value,
    expiry_min: +$('#btExpiry').value,
    min_confidence: +$('#btConf').value,
    payout_pct: +$('#btPayout').value,
    bars: +$('#btBars').value,
  };
  const res = await fetch('/api/backtest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    out.innerHTML = `<div class="empty">${err.detail || 'Falha no backtest'}</div>`;
    return;
  }
  const j = await res.json();
  const warn = j.win_rate <= (j.break_even_win_rate ?? 100)
    ? `<div class="warnbox">Taxa de acerto (${j.win_rate}%) abaixo ou igual ao
       ponto de equilíbrio do payout (${j.break_even_win_rate}%).
       Nesta configuração a estratégia perde dinheiro.</div>` : '';
  out.innerHTML = `
    ${warn}
    <div class="kpis">
      <div class="kpi"><div class="k">Operações</div><div class="v">${j.count}</div>
        <div class="s">${j.wins}W / ${j.losses}L / ${j.ties}E</div></div>
      <div class="kpi"><div class="k">Taxa de acerto</div><div class="v">${j.win_rate}%</div>
        <div class="s">equilíbrio: ${j.break_even_win_rate}%</div></div>
      <div class="kpi"><div class="k">Retorno acumulado</div><div class="v">${j.total_return_pct}%</div>
        <div class="s">stake fixo</div></div>
      <div class="kpi"><div class="k">Drawdown máximo</div><div class="v">${j.max_drawdown_pct}%</div>
        <div class="s">pior sequência</div></div>
    </div>
    <div class="panel"><h3>Curva de capital (% sobre stake fixo)</h3>
      ${spark(j.equity_curve)}</div>
    <div class="panel"><h3>${j.symbol} · ${j.candles} barras de 1 min · fonte ${j.source}</h3>
      <div class="muted">${j.disclaimer}</div></div>`;
});

function spark(curve) {
  if (!curve || curve.length < 2) return '<div class="muted">sem trades</div>';
  const w = 900, h = 160, pad = 6;
  const min = Math.min(0, ...curve), max = Math.max(0, ...curve);
  const span = max - min || 1;
  const pts = curve.map((v, i) => {
    const x = pad + (i / (curve.length - 1)) * (w - pad * 2);
    const y = h - pad - ((v - min) / span) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const zeroY = h - pad - ((0 - min) / span) * (h - pad * 2);
  const up = curve[curve.length - 1] >= 0;
  return `<svg viewBox="0 0 ${w} ${h}" style="width:100%;height:160px">
    <line x1="0" y1="${zeroY}" x2="${w}" y2="${zeroY}" stroke="#232b3d" stroke-width="1"/>
    <polyline points="${pts}" fill="none"
      stroke="${up ? '#2ecc8f' : '#ef5b6b'}" stroke-width="2"/></svg>`;
}

// ---------- calculadoras ----------
const toolRoutes = {
  staking: { url: '/api/binary-staking', method: 'GET' },
  pip: { url: '/api/pip-value', method: 'GET' },
  dd: { url: '/api/drawdown-recovery', method: 'GET' },
  margin: { url: '/api/margin', method: 'GET' },
  risk: { url: '/api/risk-plan', method: 'POST' },
};

document.querySelectorAll('form[data-tool]').forEach((form) => {
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const route = toolRoutes[form.dataset.tool];
    const out = form.querySelector('.out');
    const data = {};
    new FormData(form).forEach((v, k) => {
      const n = Number(v);
      data[k] = (v !== '' && Number.isFinite(n)) ? n : v;
    });

    let res;
    if (route.method === 'POST') {
      res = await fetch(route.url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
    } else {
      res = await fetch(route.url + '?' + new URLSearchParams(data));
    }
    out.textContent = JSON.stringify(await res.json(), null, 2);
  });
});

// ---------- API ----------
const endpoints = [
  ['GET', '/api/health', 'status, feeds, contadores'],
  ['GET', '/api/assets', 'ativos, preços e avaliação atual'],
  ['GET', '/api/snapshot', 'estado completo do motor'],
  ['GET', '/api/signals?limit=50&symbol=', 'sinais recentes'],
  ['GET', '/api/signals/open', 'sinais ainda abertos'],
  ['GET', '/api/stats?market=', 'track record auditável'],
  ['POST', '/api/backtest', 'replay da estratégia'],
  ['GET', '/api/pip-value', 'valor do pip'],
  ['GET', '/api/binary-staking', 'stake e ponto de equilíbrio'],
  ['GET', '/api/drawdown-recovery', 'recuperação de drawdown'],
  ['GET', '/api/margin', 'margem e alavancagem'],
  ['GET', '/api/average-cost', 'custo médio de posição'],
  ['GET', '/api/risk-plan', 'limites de prop firm'],
  ['WS', '/ws', 'feed ao vivo (tick, signal, settled)'],
];
const ul = $('#endpointList');
endpoints.forEach(([m, p, d]) => {
  const li = el('li');
  li.innerHTML = `<code>${m}</code> <code>${p}</code> — ${d}`;
  ul.append(li);
});

// ---------- boot ----------
$('#marketFilter').addEventListener('change', renderLive);
$('#symbolFilter').addEventListener('input', renderLive);

// Um unico timer para todos os contadores de expiracao. Antes cada card
// criava seu proprio setInterval e nunca o limpava, o que acumulava timers
// a cada re-render e travava a aba depois de alguns minutos.
setInterval(() => {
  document.querySelectorAll('[data-expires]').forEach((n) => {
    const exp = Number(n.dataset.expires);
    const s = Math.max(0, Math.round(exp - Date.now() / 1000));
    n.textContent = s > 0 ? `fecha em ${s}s` : 'aguardando liquidação…';
  });
}, 1000);

loadRecent();
setInterval(loadRecent, 30000);

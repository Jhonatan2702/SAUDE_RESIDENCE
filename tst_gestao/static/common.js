/* Utilitários compartilhados por todas as páginas do TST-GESTÃO. */
const CSRF = document.querySelector('meta[name=csrf]')?.content || '';

async function api(url, method = 'GET', body) {
  const opt = {method, headers: {'X-CSRF-Token': CSRF}};
  if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  const r = await fetch(url, opt);
  if (r.status === 401) { location.href = '/login'; throw new Error('Sessão expirada.'); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.erro || 'Erro inesperado.');
  return data;
}

const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const fmt = v => Number(v || 0).toLocaleString('pt-BR');
const fmtPct = v => Number(v || 0).toLocaleString('pt-BR', {maximumFractionDigits: 2}) + '%';
const fmtData = v => /^\d{4}-\d{2}-\d{2}/.test(v || '') ? v.slice(0, 10).split('-').reverse().join('/') : (v || '');
const ic = n => `<svg class="ic"><use href="#i-${n}"/></svg>`;
const $ = id => document.getElementById(id);
const MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
const nomeMes = m => ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'][+m.slice(5) - 1] + '/' + m.slice(2, 4);
const COR_TERAPIA = {FISIO: 'var(--t-fisio)', FONO: 'var(--t-fono)', TO: 'var(--t-to)', NUTRI: 'var(--t-nutri)', PSICO: 'var(--t-psico)'};
const corTerapia = t => COR_TERAPIA[t] || 'var(--s7)';

function toast(msg, erro = false) {
  const t = $('toast');
  t.textContent = msg; t.className = 'show' + (erro ? ' err' : '');
  clearTimeout(t._h); t._h = setTimeout(() => { t.className = ''; }, 3600);
}

/* ⓘ: um único balão posicionado sobre a página (mouse e teclado) */
(() => {
  const b = document.createElement('div'); b.className = 'balao'; document.body.append(b);
  const mostrar = a => {
    b.textContent = a.dataset.info; b.classList.add('on');
    const r = a.getBoundingClientRect(), w = b.offsetWidth, h = b.offsetHeight;
    b.style.left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), innerWidth - w - 8) + 'px';
    b.style.top = (r.top - h - 10 < 8 ? r.bottom + 10 : r.top - h - 10) + 'px';
  };
  const esconder = () => b.classList.remove('on');
  document.addEventListener('mouseover', e => { const a = e.target.closest('[data-info]'); a ? mostrar(a) : esconder(); });
  document.addEventListener('focusin', e => { const a = e.target.closest('[data-info]'); if (a) mostrar(a); });
  document.addEventListener('focusout', esconder);
  addEventListener('scroll', esconder, true);
})();

/* Abas: lembra a aba no endereço (#aba) para que o menu e o botão Voltar funcionem. */
function Abas(aoTrocar) {
  const botoes = [...document.querySelectorAll('.abas [data-aba]')];
  const valida = n => botoes.some(b => b.dataset.aba === n) ? n : botoes[0].dataset.aba;
  function ativar(nome) {
    nome = valida(nome);
    botoes.forEach(b => { b.classList.toggle('on', b.dataset.aba === nome); b.setAttribute('aria-selected', b.dataset.aba === nome); });
    document.querySelectorAll('.aba').forEach(s => s.classList.toggle('on', s.id === 'aba-' + nome));
    document.querySelectorAll('[data-menu-aba]').forEach(a => a.classList.toggle('on', a.dataset.menuAba === nome));
    if (location.hash.slice(1) !== nome) history.replaceState(null, '', location.pathname + location.search + '#' + nome);
    aoTrocar?.(nome);
    document.dispatchEvent(new CustomEvent('tst:aba', {detail: nome}));
    window.dispatchEvent(new Event('resize'));  // gráficos que estavam ocultos se ajustam
    return nome;
  }
  botoes.forEach(b => b.onclick = () => ativar(b.dataset.aba));
  addEventListener('hashchange', () => ativar(location.hash.slice(1)));
  return {ativar, atual: () => botoes.find(b => b.classList.contains('on'))?.dataset.aba, inicial: () => ativar(location.hash.slice(1))};
}

/* Período: atalhos + datas. Chama aoMudar({ini, fim}) e guarda a escolha no navegador. */
function Periodo(aoMudar) {
  const box = $('periodo'), iniEl = $('dt-ini'), fimEl = $('dt-fim');
  const botoes = box.querySelectorAll('[data-p]');
  const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const hoje = new Date(box.dataset.hoje + 'T12:00:00');
  const marcar = p => botoes.forEach(b => b.classList.toggle('on', b.dataset.p === p));
  const valor = () => ({ini: iniEl.value, fim: fimEl.value});
  const guardar = p => { try { localStorage.setItem('tst-periodo', JSON.stringify({p, ...valor()})); } catch (e) { /* opcional */ } };
  function aplicar(p) {
    const a = hoje.getFullYear(), m = hoje.getMonth();
    const faixa = {
      'mes': [new Date(a, m, 1), hoje], 'mes-ant': [new Date(a, m - 1, 1), new Date(a, m, 0)],
      '90d': [new Date(a, m, hoje.getDate() - 89), hoje], 'ano': [new Date(a, 0, 1), hoje],
    }[p];
    if (!faixa) return;
    iniEl.value = iso(faixa[0]); fimEl.value = iso(faixa[1]); marcar(p);
  }
  botoes.forEach(b => b.onclick = () => { aplicar(b.dataset.p); guardar(b.dataset.p); aoMudar(valor()); });
  [iniEl, fimEl].forEach(el => el.addEventListener('change', () => {
    if (!iniEl.value || !fimEl.value) return;
    if (iniEl.value > fimEl.value) [iniEl.value, fimEl.value] = [fimEl.value, iniEl.value];
    marcar(''); guardar(''); aoMudar(valor());
  }));
  let salvo = null;
  try { salvo = JSON.parse(localStorage.getItem('tst-periodo') || 'null'); } catch (e) { salvo = null; }
  if (salvo?.p) aplicar(salvo.p);
  else if (salvo?.ini && salvo?.fim) { iniEl.value = salvo.ini; fimEl.value = salvo.fim; marcar(''); }
  else aplicar(box.dataset.padrao || 'mes');
  return {valor, rotulo: () => rotuloPeriodo(valor())};
}

function rotuloPeriodo(P) {
  const br = s => s.split('-').reverse().join('/');
  if (P.ini.slice(0, 7) === P.fim.slice(0, 7) && P.ini.endsWith('-01')) {
    const nome = `${MESES[+P.ini.slice(5, 7) - 1]} de ${P.ini.slice(0, 4)}`;
    const ultimo = new Date(+P.fim.slice(0, 4), +P.fim.slice(5, 7), 0).getDate();
    return (+P.fim.slice(8) < ultimo ? `${nome}, até ${br(P.fim).slice(0, 5)}` : nome);
  }
  return `${br(P.ini)} a ${br(P.fim)}`;
}

/* Tabela com busca, ordenação por coluna, contador e exportação CSV. */
function Tabela(tabelaId, {busca, contador, filtro, aoClicar, numericas = [], formatos = {}, limite = 3000, vazio = 'Nenhum registro.'} = {}) {
  const tab = $(tabelaId);
  let colunas = [], linhas = [], ord = null;
  const buscaEl = busca && $(busca), contEl = contador && $(contador);
  const fmtCel = (v, i) => formatos[i] ? formatos[i](v) : (numericas.includes(i) ? fmt(v) : esc(v));
  function visiveis() {
    const termo = (buscaEl?.value || '').trim().toLowerCase();
    let out = linhas.filter(l => (!filtro || filtro(l)) && (!termo || l.join(' ').toLowerCase().includes(termo)));
    if (ord) {
      const {i, dir} = ord;
      out = [...out].sort((a, b) => (numericas.includes(i) ? (a[i] - b[i]) : String(a[i]).localeCompare(String(b[i]), 'pt-BR', {numeric: true})) * dir);
    }
    return out;
  }
  function desenhar() {
    const vis = visiveis();
    tab.innerHTML = '<thead><tr>' + colunas.map((c, i) => `<th data-ord="${i}"${numericas.includes(i) ? ' class="num"' : ''}>${esc(c)}` +
      (ord?.i === i ? `<span class="seta">${ord.dir > 0 ? '▲' : '▼'}</span>` : '') + '</th>').join('') + '</tr></thead><tbody>' +
      (vis.slice(0, limite).map((l, k) => `<tr data-k="${k}"${aoClicar ? ' class="clicavel"' : ''}>` +
        l.slice(0, colunas.length).map((v, i) => `<td${numericas.includes(i) ? ' class="num"' : ''}>${fmtCel(v, i)}</td>`).join('') + '</tr>').join('') ||
       `<tr><td colspan="${colunas.length || 1}" class="muted">${esc(vazio)}</td></tr>`) + '</tbody>';
    if (contEl) contEl.textContent = (vis.length === linhas.length ? `${fmt(vis.length)} registro(s)` : `${fmt(vis.length)} de ${fmt(linhas.length)}`) +
      (vis.length > limite ? ` · exibindo ${fmt(limite)}` : '');
    tab._vis = vis;
  }
  tab.addEventListener('click', e => {
    const th = e.target.closest('th[data-ord]');
    if (th) { const i = +th.dataset.ord; ord = ord?.i === i ? {i, dir: -ord.dir} : {i, dir: numericas.includes(i) ? -1 : 1}; return desenhar(); }
    const tr = e.target.closest('tr[data-k]');
    if (tr && aoClicar) aoClicar(tab._vis[+tr.dataset.k]);
  });
  buscaEl?.addEventListener('input', desenhar);
  tab._csv = () => ({colunas, linhas: visiveis().map(l => l.slice(0, colunas.length))});
  return {
    dados(c, l) { colunas = c; linhas = l; desenhar(); },
    redesenhar: desenhar,
    linhas: () => linhas,
  };
}

function baixarCSV(nome, colunas, linhas) {
  const cel = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const csv = [colunas, ...linhas].map(l => l.map(cel).join(';')).join('\r\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob(['﻿' + csv], {type: 'text/csv;charset=utf-8'}));
  a.download = nome; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-csv]');
  if (!b) return;
  const t = $(b.dataset.csv);
  if (t?._csv) { const d = t._csv(); baixarCSV(`tst-${b.dataset.csv.replace(/^t-/, '')}.csv`, d.colunas, d.linhas); }
});

/* Barras em lista: [{rotulo, valor}] → rótulo · barra · valor (+ % opcional). Clique abre o detalhamento. */
function listaBarras(id, itens, {det, valorDet = i => i.rotulo, total, cor, max = 10, rotulo = i => i.rotulo, vazio = 'Sem dados no período.'} = {}) {
  const el = $(id);
  if (!itens.length) { el.innerHTML = `<p class="muted">${esc(vazio)}</p>`; return; }
  const maior = Math.max(1, ...itens.map(i => i.valor));
  el.innerHTML = itens.slice(0, max).map(i => {
    const pct = total ? ` <small>${fmtPct(Math.round(i.valor * 1000 / total) / 10)}</small>` : '';
    const c = typeof cor === 'function' ? cor(i) : (cor || 'var(--acc)');
    return `<div class="lb"${det ? ` data-det="${esc(det)}" data-valor="${esc(valorDet(i))}"` : ''} title="${esc(rotulo(i))}">` +
      `<span>${esc(rotulo(i))}</span><em>${fmt(i.valor)}${pct}</em><div class="trilho"><i style="width:${(i.valor * 100 / maior).toFixed(1)}%;--c:${c}"></i></div></div>`;
  }).join('') + (itens.length > max ? `<div class="mais">+ ${itens.length - max} outros</div>` : '');
}

/* KPI: {tom, icone, rotulo, valor, sufixo, sub, det, valorDet, info, destaque} */
function kpis(id, cards) {
  $(id).innerHTML = cards.map(k => {
    const tag = k.det ? 'button type="button"' : 'div';
    return `<${tag} class="kpi tom-${k.tom || 'neutro'}${k.destaque ? ' destaque' : ''}"${k.det ? ` data-det="${esc(k.det)}" data-valor="${esc(k.valorDet || '')}"` : ''}>` +
      `<span class="k-rot">${ic(k.icone || 'info')}${esc(k.rotulo)}${k.info ? `<span class="info" tabindex="0" data-info="${esc(k.info)}">${ic('info')}</span>` : ''}</span>` +
      `<span class="k-val">${esc(k.valor)}${k.sufixo ? `<small>${esc(k.sufixo)}</small>` : ''}</span>` +
      (k.sub ? `<span class="k-sub">${k.sub}</span>` : '') + (k.det ? `<span class="k-link">${esc(k.link || 'Ver pacientes')} →</span>` : '') +
      `</${k.det ? 'button' : 'div'}>`;
  }).join('');
}

/* Janela de detalhamento: abre a lista por trás de um número, com busca, CSV e navegação (Voltar). */
function Detalhe(buscar) {
  const dlg = $('dlg-det'), buscaEl = $('det-busca');
  const pilha = [];
  let atual = null;
  async function abrir(tipo, valor = '', empilhar = true) {
    try {
      const r = await buscar(tipo, valor);
      if (!r) return;  // tratado por outro componente (ex.: ficha do bairro)
      if (empilhar) pilha.push({tipo, valor});
      atual = r; buscaEl.value = ''; desenhar();
      if (!dlg.open) dlg.showModal();
    } catch (e) { toast(e.message, true); }
  }
  function desenhar() {
    const r = atual, termo = buscaEl.value.trim().toLowerCase();
    const linhas = termo ? r.linhas.filter(l => l.join(' ').toLowerCase().includes(termo)) : r.linhas;
    $('det-t').textContent = r.titulo;
    $('det-n').textContent = termo ? `${fmt(linhas.length)} de ${fmt(r.total)}` : `${fmt(r.total)} registro(s)` + (r.truncado ? ` · exibindo ${fmt(r.linhas.length)}` : '');
    $('det-h').innerHTML = '<tr>' + r.colunas.map(c => `<th>${esc(c)}</th>`).join('') + '</tr>';
    $('det-b').innerHTML = linhas.map(l => {
      const alvo = r.drill ? ` data-drill="${esc(r.drill.tipo)}" data-valor="${esc(l[r.drill.col])}" class="clicavel" title="Ver histórico"` : '';
      return `<tr${alvo}>${l.map(c => `<td>${esc(c)}</td>`).join('')}</tr>`;
    }).join('') || `<tr><td colspan="${r.colunas.length}" class="muted">Nenhum registro.</td></tr>`;
    $('det-voltar').hidden = pilha.length < 2;
  }
  buscaEl.addEventListener('input', () => atual && desenhar());
  $('det-fechar').onclick = () => dlg.close();
  dlg.addEventListener('close', () => { pilha.length = 0; });
  $('det-voltar').onclick = () => { pilha.pop(); const ant = pilha.pop(); if (ant) abrir(ant.tipo, ant.valor); };
  $('det-csv').onclick = () => atual && baixarCSV('tst-detalhe.csv', atual.colunas, atual.linhas);
  $('det-b').addEventListener('click', e => { const tr = e.target.closest('[data-drill]'); if (tr) abrir(tr.dataset.drill, tr.dataset.valor); });
  document.addEventListener('click', e => {
    if (e.target.closest('.info') || dlg.contains(e.target)) return;
    const alvo = e.target.closest('[data-det]');
    if (alvo) abrir(alvo.dataset.det, alvo.dataset.valor || '');
  });
  return {abrir};
}

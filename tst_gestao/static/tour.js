/* Tour guiado: destaca uma parte da tela por vez, com explicação, navegação e progresso.
   O conteúdo de cada tour está em guia.js (GUIA). Cada usuário vê a boas-vindas e o convite de cada aba uma única vez;
   o botão "Tour desta tela" refaz o tour quando quiser. */
const Tour = (() => {
  const VERSAO = 'v1';
  const usuario = document.querySelector('meta[name=usuario]')?.content || 'anon';
  const chave = id => `tst-tour:${usuario}:${id}:${VERSAO}`;
  const visto = id => { try { return localStorage.getItem(chave(id)) === '1'; } catch (e) { return false; } };
  const marcar = id => { try { localStorage.setItem(chave(id), '1'); } catch (e) { /* opcional */ } };

  let passos = [], i = 0, idAtual = null, el = {};

  function montar() {
    if (el.fundo) return;
    el.fundo = Object.assign(document.createElement('div'), {className: 'tour-fundo'});
    el.foco = Object.assign(document.createElement('div'), {className: 'tour-foco'});
    el.caixa = Object.assign(document.createElement('div'), {className: 'tour-caixa'});
    el.caixa.setAttribute('role', 'dialog');
    el.caixa.setAttribute('aria-live', 'polite');
    document.body.append(el.fundo, el.foco, el.caixa);
    el.fundo.onclick = fechar;
    el.caixa.addEventListener('click', e => {
      const b = e.target.closest('[data-tour]');
      if (!b) return;
      if (b.dataset.tour === 'prox') ir(i + 1);
      else if (b.dataset.tour === 'volta') ir(i - 1, -1);
      else fechar();
    });
    addEventListener('resize', () => idAtual && posicionar());
    addEventListener('scroll', () => idAtual && posicionar(), true);
    document.addEventListener('keydown', e => {
      if (!idAtual) return;
      if (e.key === 'Escape') fechar();
      else if (e.key === 'ArrowRight' || e.key === 'Enter') { e.preventDefault(); ir(i + 1); }
      else if (e.key === 'ArrowLeft') ir(i - 1, -1);
    });
  }

  function alvoDe(p) {
    if (!p.alvo) return null;
    let alvo = document.querySelector(p.alvo);
    if (alvo && p.card) alvo = alvo.closest('.card, .kpi, .ter, .nv') || alvo;
    if (!alvo) return null;
    const r = alvo.getBoundingClientRect();
    return r.width || r.height ? alvo : null;  // elemento oculto: pula o passo
  }

  function ir(n, dir = 1) {
    if (n >= passos.length) return fechar(true);
    if (n < 0) return;
    const p = passos[n];
    if (p.aba && window.ABAS && window.ABAS.atual() !== p.aba) window.ABAS.ativar(p.aba);
    i = n;
    const alvo = alvoDe(p);
    if (p.alvo && !alvo) return ir(n + dir, dir);
    if (alvo) alvo.scrollIntoView({block: p.bloco || 'center', behavior: 'instant'});
    const ultimo = n === passos.length - 1;
    el.caixa.innerHTML =
      `<div class="tour-topo"><span class="tour-passo">${n + 1} de ${passos.length}</span><button type="button" class="tour-x" data-tour="fechar" aria-label="Fechar tour">×</button></div>` +
      `<h3>${p.titulo}</h3><div class="tour-texto">${p.texto}</div>` +
      `<div class="tour-pontos">${passos.map((_, k) => `<i class="${k === n ? 'on' : k < n ? 'feito' : ''}"></i>`).join('')}</div>` +
      `<div class="tour-acoes"><button type="button" class="btn sm" data-tour="volta"${n ? '' : ' disabled'}>← Voltar</button>` +
      `<button type="button" class="btn primario sm" data-tour="prox">${ultimo ? 'Concluir ✓' : 'Próximo →'}</button></div>`;
    el.alvo = alvo;
    posicionar();
    el.caixa.querySelector('[data-tour=prox]').focus({preventScroll: true});
  }

  function posicionar() {
    const caixa = el.caixa, alvo = el.alvo, m = 10;
    caixa.style.maxWidth = '380px';
    if (!alvo) {  // passo sem alvo: caixa centralizada
      el.foco.style.cssText = 'left:50%;top:50%;width:0;height:0';
      caixa.style.left = (innerWidth - caixa.offsetWidth) / 2 + 'px';
      caixa.style.top = Math.max(20, (innerHeight - caixa.offsetHeight) / 2) + 'px';
      return;
    }
    const r = alvo.getBoundingClientRect();
    Object.assign(el.foco.style, {left: r.left - 6 + 'px', top: r.top - 6 + 'px', width: r.width + 12 + 'px', height: r.height + 12 + 'px'});
    const w = caixa.offsetWidth, h = caixa.offsetHeight;
    const lugares = [
      {x: r.right + m + 6, y: r.top, ok: r.right + m + w < innerWidth},
      {x: r.left, y: r.bottom + m + 6, ok: r.bottom + m + h < innerHeight},
      {x: r.left, y: r.top - h - m - 6, ok: r.top - h - m > 0},
      {x: r.left - w - m - 6, y: r.top, ok: r.left - w - m > 0},
    ];
    const lugar = lugares.find(l => l.ok) || {x: innerWidth - w - 16, y: innerHeight - h - 16};
    caixa.style.left = Math.min(Math.max(12, lugar.x), innerWidth - w - 12) + 'px';
    caixa.style.top = Math.min(Math.max(12, lugar.y), innerHeight - h - 12) + 'px';
  }

  function iniciar(id) {
    const def = (window.GUIA || {})[id];
    if (!def) return toast('Ainda não há tour para esta tela.');
    convite.esconder();
    montar();
    // só os passos que existem nesta tela e no perfil do usuário (o contador "1 de N" fica exato)
    passos = def.passos.filter(p => (!p.nivel || window.NIVEL >= p.nivel) && (!p.alvo || document.querySelector(p.alvo)));
    if (!passos.length) return toast('Ainda não há tour para esta tela.');
    idAtual = id;
    document.body.classList.add('tour-ativo');
    ir(0);
  }

  function fechar(concluiu = false) {
    if (!idAtual) return;
    marcar(idAtual);
    document.body.classList.remove('tour-ativo');
    el.caixa.innerHTML = ''; el.foco.style.cssText = ''; el.alvo = null;
    const terminou = idAtual;
    idAtual = null;
    if (concluiu === true && terminou === 'boas-vindas') setTimeout(() => sugerirAba(true), 400);
  }

  // convite discreto na primeira visita a cada aba
  const convite = (() => {
    const box = Object.assign(document.createElement('div'), {className: 'tour-convite'});
    box.setAttribute('role', 'status');
    document.body.append(box);
    let id = null;
    box.addEventListener('click', e => {
      const b = e.target.closest('[data-convite]');
      if (!b) return;
      if (b.dataset.convite === 'sim') iniciar(id); else { marcar(id); esconder(); }
    });
    function mostrar(novoId) {
      const def = window.GUIA?.[novoId];
      if (!def) return;
      id = novoId;
      box.innerHTML = `<b>Primeira vez em “${esc(def.nome)}”?</b><span>${esc(def.resumo)}</span>` +
        `<div><button type="button" class="btn primario sm" data-convite="sim">Fazer o tour (${def.passos.length} passos)</button>` +
        `<button type="button" class="btn sm" data-convite="nao">Agora não</button></div>`;
      box.classList.add('on');
    }
    function esconder() { box.classList.remove('on'); }
    return {mostrar, esconder};
  })();

  const idTela = () => window.PAGINA + (window.ABAS ? ':' + window.ABAS.atual() : '');

  function sugerirAba(forcar = false) {
    if (idAtual || !window.PAGINA) return;
    const id = idTela();
    if (window.GUIA?.[id] && (forcar || !visto(id))) convite.mostrar(id); else convite.esconder();
  }

  // chama fn quando o seletor existir na tela (dados carregados) ou após 5 s, o que vier primeiro
  function esperar(seletor, fn, inicio = Date.now()) {
    if (document.querySelector(seletor) || Date.now() - inicio > 5000) return setTimeout(fn, 300);
    setTimeout(() => esperar(seletor, fn, inicio), 150);
  }

  function automatico() {
    const pedido = new URLSearchParams(location.search).get('tour');
    if (pedido) {
      history.replaceState(null, '', location.pathname + location.hash);
      return esperar('.kpi, .card', () => iniciar(pedido === '1' ? idTela() : pedido));
    }
    // a boas-vindas abre sozinha só nos painéis (página inicial de cada perfil), depois que os cards foram desenhados
    if (!visto('boas-vindas') && window.ABAS && window.GUIA?.['boas-vindas']) return esperar('.kpi', () => iniciar('boas-vindas'));
    setTimeout(() => sugerirAba(), 1200);
  }

  document.addEventListener('tst:aba', () => setTimeout(() => sugerirAba(), 700));
  document.addEventListener('click', e => { if (e.target.closest('#btn-tour')) iniciar(idTela()); });
  addEventListener('load', () => {
    const b = document.getElementById('btn-tour');
    if (b && !window.GUIA?.[idTela()]) b.hidden = true;
    automatico();
  });
  return {iniciar, sugerirAba};
})();

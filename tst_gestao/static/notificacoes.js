/* Avisos da sincronização: pop-up no canto da tela + sino com histórico no menu.
   Críticos ficam até a pessoa fechar; atenção e informação somem sozinhos. Cada usuário marca o que já leu
   (guardado no navegador). Novos avisos são consultados a cada minuto. */
(() => {
  const usuario = document.querySelector('meta[name=usuario]')?.content;
  const sino = document.getElementById('sino');
  if (!usuario || !sino) return;
  const CHAVE = `tst-notif-lido:${usuario}`;
  const TEMPO = {info: 10000, warn: 15000};  // crit: não some sozinho
  const ICONE = {crit: 'aviso', warn: 'pendencia', info: 'info'};
  const ROTULO = {crit: 'Crítico', warn: 'Atenção', info: 'Informação'};
  const ABAS = {painel: ['geral', 'mapa', 'terapias', 'complexidade', 'movimentacao', 'perfil', 'profissionais'],
                operacional: ['relatorios', 'profissional', 'abrangencia', 'fichas', 'precos']};
  let todas = [], lido = 0;
  try { lido = +(localStorage.getItem(CHAVE) || 0); } catch (e) { lido = 0; }
  const mostradas = new Set();
  const pilha = Object.assign(document.createElement('div'), {className: 'notif-pilha'});
  pilha.setAttribute('aria-live', 'polite');
  document.body.append(pilha);
  const painel = document.getElementById('notif-painel');

  const quando = s => { const d = new Date(s); const min = Math.round((Date.now() - d) / 60000);
    return min < 1 ? 'agora' : min < 60 ? `há ${min} min` : min < 1440 ? `há ${Math.round(min / 60)} h` : fmtData(s); };
  function marcarLido(id) {
    if (id <= lido) return;
    lido = id;
    try { localStorage.setItem(CHAVE, String(lido)); } catch (e) { /* opcional */ }
    contador();
  }
  function contador() {
    const n = todas.filter(x => x.id > lido).length;
    sino.querySelector('.sino-n').textContent = n > 9 ? '9+' : n;
    sino.classList.toggle('tem', n > 0);
    sino.title = n ? `${n} aviso(s) não lido(s)` : 'Avisos da sincronização';
  }

  // "Ver": abre a ficha/aba certa conforme o perfil (operacional não acessa o Painel BI)
  function abrir(link) {
    if (link.url) { location.href = link.url; return; }
    let pagina = link.pagina || (window.NIVEL >= 2 ? 'painel' : 'operacional');
    if (pagina === 'painel' && window.NIVEL < 2) pagina = 'operacional';
    const aba = ABAS[pagina].includes(link.aba) ? link.aba : '';
    const ficha = ['paciente', 'bairro', 'profissional'].find(t => link[t]);
    if (location.pathname === '/' + pagina && window.Ficha) {
      if (aba && window.ABAS) window.ABAS.ativar(aba);
      if (ficha) window.Ficha.abrir(ficha, link[ficha]);
      return;
    }
    location.href = `/${pagina}` + (ficha ? `?${ficha}=${encodeURIComponent(link[ficha])}` : '') + (aba ? `#${aba}` : '');
  }

  const html = n => `<div class="notif-ic">${ic(ICONE[n.gravidade] || 'info')}</div><div class="notif-corpo">` +
    `<span class="notif-rot">${ROTULO[n.gravidade] || ''} · ${esc(quando(n.criado_em))}</span><b>${esc(n.titulo)}</b>` +
    (n.texto ? `<p>${esc(n.texto)}</p>` : '') + '</div>';

  function popup(n) {
    if (mostradas.has(n.id)) return;
    mostradas.add(n.id);
    const card = Object.assign(document.createElement('div'), {className: `notif g-${n.gravidade}`});
    card.setAttribute('role', n.gravidade === 'crit' ? 'alert' : 'status');
    card.innerHTML = html(n) + `<div class="notif-acoes"><button type="button" class="btn primario sm" data-a="ver">Ver</button>` +
      `<button type="button" class="notif-x" data-a="fechar" aria-label="Fechar">×</button></div>`;
    const fechar = () => { card.classList.add('saindo'); setTimeout(() => card.remove(), 250); };
    card.onclick = e => {
      const a = e.target.closest('[data-a]')?.dataset.a;
      if (!a) return;
      marcarLido(n.id); fechar();
      if (a === 'ver') abrir(n.link || {});
    };
    pilha.prepend(card);
    while (pilha.querySelectorAll('.notif').length > 3) pilha.querySelector('.notif:last-of-type').remove();  // no máximo 3 na tela
    if (TEMPO[n.gravidade]) setTimeout(fechar, TEMPO[n.gravidade]);
  }

  // cartão-resumo quando há mais avisos do que cabem na tela
  function resto(qtd) {
    pilha.querySelector('.notif-resto')?.remove();
    const b = Object.assign(document.createElement('button'), {type: 'button', className: 'notif-resto',
      textContent: `+ ${qtd} aviso(s) no sino — ver todos`});
    b.onclick = e => { e.stopPropagation(); b.remove(); sino.click(); };
    pilha.append(b);
  }

  function desenharPainel() {
    painel.querySelector('.notif-lista').innerHTML = todas.length ? todas.map(n =>
      `<button type="button" class="notif-item g-${n.gravidade}${n.id > lido ? ' novo' : ''}" data-id="${n.id}">${html(n)}</button>`).join('')
      : '<p class="muted" style="padding:12px">Nenhum aviso ainda. Eles aparecem aqui após cada sincronização com a URL.</p>';
  }
  sino.onclick = e => {
    e.stopPropagation();
    painel.hidden = !painel.hidden;
    if (!painel.hidden) { desenharPainel(); marcarLido(todas[0]?.id || 0); }
  };
  painel.onclick = e => {
    e.stopPropagation();
    const item = e.target.closest('[data-id]');
    if (item) { painel.hidden = true; abrir(todas.find(n => n.id === +item.dataset.id)?.link || {}); }
  };
  document.addEventListener('click', () => { painel.hidden = true; });

  async function buscar(primeira = false) {
    try {
      const desde = primeira ? 0 : (todas[0]?.id || 0);
      const novas = await api(`/api/notificacoes?desde=${desde}`);
      if (!novas.length) return contador();
      todas = primeira ? novas : [...novas, ...todas].slice(0, 30);
      contador();
      // pop-up do que ainda não foi lido e é recente (24 h): os mais graves primeiro, no máximo 3; o resto fica no sino
      const limite = Date.now() - 24 * 3600 * 1000, peso = {crit: 0, warn: 1, info: 2};
      const fila = novas.filter(n => n.id > lido && new Date(n.criado_em) > limite && !mostradas.has(n.id))
        .sort((a, b) => (peso[a.gravidade] - peso[b.gravidade]) || b.id - a.id);
      fila.slice(0, 3).reverse().forEach(popup);
      if (fila.length > 3) resto(fila.length - 3);
    } catch (e) { /* sem conexão: tenta de novo no próximo minuto */ }
  }
  buscar(true);
  setInterval(buscar, 60000);
})();

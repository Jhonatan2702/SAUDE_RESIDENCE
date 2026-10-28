(() => {
  const cod = window.CODIGO, base = '/api/prontuario/' + encodeURIComponent(cod);
  const $ = id => document.getElementById(id);
  let D = null, filtro = 'todos';
  const CORES = {Evolução: '#1ea7f0', Movimentação: '#6366f1', Terapia: '#14b8a6', Anexo: '#f59e0b'};

  const idade = n => { if (!n) return '—'; const b = new Date(n), h = new Date(); let a = h.getFullYear() - b.getFullYear(); if (h < new Date(h.getFullYear(), b.getMonth(), b.getDate())) a--; return isNaN(a) ? '—' : a + ' anos'; };
  const tam = b => b > 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB';
  const url = a => '/anexos/' + a.id;
  const fmtDT = s => (s || '').replace('T', ' ').slice(0, 16).split(' ').map((p, i) => i ? p : fmtData(p)).join(' ');

  function ficha() {
    const p = D.paciente, ativo = !p.data_alta;
    const it = (r, v) => `<div><span>${r}</span><b>${esc(v || '—')}</b></div>`;
    $('ficha').innerHTML = `<div class="ficha-h"><div><h2>${esc(p.nome)}</h2><span class="muted">Código ${esc(p.codigo)}</span></div><span class="tag ${ativo ? '' : 'off'}">${ativo ? 'Ativo' : 'Alta em ' + fmtData(p.data_alta)}</span></div>
      <div class="ficha-g">${it('Idade', idade(p.nascimento))}${it('Nascimento', fmtData(p.nascimento))}${it('Sexo', p.sexo)}${it('Bairro / Cidade', [p.bairro, p.cidade].filter(Boolean).join(' / '))}${it('Endereço', p.endereco)}${it('Telefone', p.telefone)}
      ${it('Operadora', p.operadora)}${it('Diagnóstico', p.diagnostico)}${it('Complexidade', p.complexidade)}${it('Serviço', p.servico)}${it('Admissão', fmtData(p.data_admissao))}${it('Motivo da alta', p.motivo_alta)}</div>`;
  }

  function itens() {
    const l = [];
    D.evolucoes.forEach(e => l.push({k: 'Evolução', data: e.data, sub: e.criado_em, titulo: e.tipo, meta: [e.profissional, e.autor && 'por ' + e.autor].filter(Boolean).join(' · '), texto: e.texto, del: ['/api/evolucoes/' + e.id, 'registro']}));
    D.movimentacao.forEach(m => l.push({k: 'Movimentação', data: m.data, sub: '', titulo: m.evento, meta: m.motivo || '', texto: ''}));
    D.terapias.forEach(t => l.push({k: 'Terapia', data: t.mes + '-01', sub: '', titulo: `${t.terapia} · ${t.situacao || 'sem situação'}`, meta: `Competência ${t.mes.split('-').reverse().join('/')}` + (t.profissional ? ' · ' + t.profissional : '') + (t.sessoes != null ? ` · ${t.sessoes} sessões` : ''), texto: t.observacao || ''}));
    D.anexos.forEach(a => l.push({k: 'Anexo', data: a.data_documento || (a.criado_em || '').slice(0, 10), sub: a.criado_em, titulo: `${a.categoria}: ${a.nome_original}`, meta: [a.descricao, 'enviado por ' + (a.enviado_por || '—')].filter(Boolean).join(' · '), texto: '', link: a}));
    return l.sort((x, y) => (y.data + (y.sub || '')).localeCompare(x.data + (x.sub || '')));
  }

  function acoesAnexo(a) {
    const d = document.createElement('span');
    const v = document.createElement('a'); v.className = 'btn ghost sm'; v.href = url(a); v.target = '_blank'; v.rel = 'noopener'; v.textContent = 'Abrir';
    const b = document.createElement('a'); b.className = 'btn ghost sm'; b.href = url(a) + '?baixar=1'; b.textContent = 'Baixar'; b.style.marginLeft = '4px';
    d.append(v, b);
    if (NIVEL >= 3) d.append(botao('Excluir', () => excluir('/api/anexos/' + a.id, 'anexo'), 'danger'));
    return d;
  }
  function botao(t, fn, cls = '') { const b = document.createElement('button'); b.type = 'button'; b.className = 'btn ghost sm ' + cls; b.textContent = t; b.style.marginLeft = '4px'; b.onclick = fn; return b; }
  async function excluir(u, nome) {
    if (!confirm(`Excluir este ${nome} do prontuário? Esta ação não pode ser desfeita.`)) return;
    try { await api(u, 'DELETE'); toast('Excluído.'); carregar(); } catch (e) { toast(e.message, true); }
  }

  function linha() {
    const todos = itens(), ks = ['todos', ...Object.keys(CORES)];
    $('filtros').innerHTML = '';
    ks.forEach(k => { const b = document.createElement('button'); b.className = 'chip' + (filtro === k ? ' on' : ''); b.textContent = k === 'todos' ? 'Todos' : k; b.onclick = () => { filtro = k; linha(); }; $('filtros').append(b); });
    const tl = $('timeline'); tl.innerHTML = '';
    const lista = todos.filter(i => filtro === 'todos' || i.k === filtro);
    if (!lista.length) tl.innerHTML = '<div class="card empty">Nenhum registro no histórico.</div>';
    lista.forEach(i => {
      const el = document.createElement('div'); el.className = 'tl-item'; el.style.setProperty('--c', CORES[i.k]);
      el.innerHTML = `<div class="tl-data">${fmtData(i.data)}</div><div class="tl-card"><div class="tl-h"><span class="tl-k">${i.k}</span><b>${esc(i.titulo)}</b></div>${i.meta ? `<div class="muted">${esc(i.meta)}</div>` : ''}${i.texto ? `<p class="tl-txt">${esc(i.texto)}</p>` : ''}<div class="tl-a"></div></div>`;
      const a = el.querySelector('.tl-a');
      if (i.link) a.append(acoesAnexo(i.link));
      if (i.del && NIVEL >= 3) a.append(botao('Excluir', () => excluir(i.del[0], i.del[1]), 'danger'));
      tl.append(el);
    });
  }

  function evolucoes() {
    const c = $('p-evolucoes'); c.innerHTML = '';
    if (!D.evolucoes.length) c.innerHTML = '<div class="card empty">Nenhum registro clínico ainda.</div>';
    D.evolucoes.forEach(e => {
      const d = document.createElement('div'); d.className = 'card';
      d.innerHTML = `<h3><span><span class="tag">${esc(e.tipo)}</span> ${fmtData(e.data)}</span><small>${esc([e.profissional, e.autor && 'registrado por ' + e.autor, fmtDT(e.criado_em)].filter(Boolean).join(' · '))}</small></h3><p class="tl-txt">${esc(e.texto)}</p>`;
      if (NIVEL >= 3) d.append(botao('Excluir', () => excluir('/api/evolucoes/' + e.id, 'registro'), 'danger'));
      c.append(d);
    });
  }

  function anexos() {
    const tb = $('tb-anx'); tb.innerHTML = '';
    $('vazio-anx').classList.toggle('hidden', D.anexos.length > 0);
    D.anexos.forEach(a => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td><span class="tag">${esc(a.categoria)}</span></td><td>${esc(a.descricao || '')}</td><td>${esc(a.nome_original)}</td><td>${fmtData(a.data_documento) || fmtData((a.criado_em || '').slice(0, 10))}</td><td>${tam(a.tamanho)}</td><td>${esc(a.enviado_por || '')}</td><td class="r"></td>`;
      tr.lastChild.append(acoesAnexo(a)); tb.append(tr);
    });
  }

  function opcoes(sel, lista, vazio) {
    sel.innerHTML = ''; if (vazio) sel.add(new Option('— selecione —', ''));
    lista.forEach(v => sel.add(new Option(v, v)));
  }

  async function carregar() {
    try { D = await api(base); } catch (e) { toast(e.message, true); return; }
    ficha(); linha(); evolucoes(); anexos();
    opcoes($('evo-tipo'), D.opcoes.tipos); opcoes($('evo-prof'), D.opcoes.profissionais, true); opcoes($('anx-cat'), D.opcoes.categorias);
  }

  document.querySelectorAll('.tab').forEach(t => t.onclick = () => {
    document.querySelectorAll('.tab').forEach(o => o.classList.toggle('on', o === t));
    ['linha', 'evolucoes', 'anexos'].forEach(k => $('p-' + k).classList.toggle('hidden', k !== t.dataset.tab));
  });
  document.querySelectorAll('[data-fechar]').forEach(b => b.onclick = () => $(b.dataset.fechar).close());
  $('b-evo')?.addEventListener('click', () => { $('f-evo').reset(); $('erro-evo').classList.add('hidden'); $('dlg-evo').showModal(); });
  $('b-anx')?.addEventListener('click', () => { $('f-anx').reset(); $('erro-anx').classList.add('hidden'); $('dlg-anx').showModal(); });

  $('f-evo').onsubmit = async e => {
    e.preventDefault();
    try { await api(base + '/evolucoes', 'POST', Object.fromEntries(new FormData($('f-evo')))); $('dlg-evo').close(); toast('Registro salvo.'); carregar(); }
    catch (err) { $('erro-evo').textContent = err.message; $('erro-evo').classList.remove('hidden'); }
  };
  $('f-anx').onsubmit = async e => {
    e.preventDefault();
    const btn = $('btn-anx'); btn.disabled = true; btn.textContent = 'Enviando…';
    try {
      const r = await fetch(base + '/anexos', {method: 'POST', headers: {'X-CSRF-Token': CSRF}, body: new FormData($('f-anx'))});
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.erro || 'Falha no envio.');
      $('dlg-anx').close(); toast('Anexo enviado.'); carregar();
    } catch (err) { $('erro-anx').textContent = err.message; $('erro-anx').classList.remove('hidden'); }
    finally { btn.disabled = false; btn.textContent = 'Enviar'; }
  };
  carregar();
})();

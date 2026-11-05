(() => {
  const fmt = v => Number(v || 0).toLocaleString('pt-BR');
  const cores = ['#2563eb', '#0d9488', '#7c3aed', '#f97316', '#e11d48', '#16a34a', '#1e293b', '#0ea5e9', '#a855f7', '#eab308'];
  const MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
  const nomeMes = m => ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'][+m.slice(5) - 1] + '/' + m.slice(2, 4);
  const fmtD = s => s.split('-').reverse().join('/');
  const ultimoDiaIso = s => `${s.slice(0, 8)}${String(new Date(+s.slice(0, 4), +s.slice(5, 7), 0).getDate()).padStart(2, '0')}`;
  const rotuloPeriodo = P => (P.ini.slice(0, 7) === P.fim.slice(0, 7) && P.ini.endsWith('-01')
    ? `${MESES[+P.ini.slice(5, 7) - 1]} de ${P.ini.slice(0, 4)}${P.fim < ultimoDiaIso(P.fim) ? ` · até ${fmtD(P.fim).slice(0, 5)}` : ''}`
    : `${fmtD(P.ini)} a ${fmtD(P.fim)}`);
  const fonte = getComputedStyle(document.body).fontFamily;
  Chart.defaults.font.family = fonte;
  Chart.defaults.color = '#64748b';

  // valores escritos dentro da barra (no topo); se a barra for curta, ficam logo acima dela
  Chart.register({
    id: 'valores',
    afterDatasetsDraw(ch) {
      const {ctx} = ch, tipo = ch.config.type, horiz = ch.options.indexAxis === 'y';
      ctx.save();
      ctx.font = `700 11.5px ${fonte}`;
      ch.data.datasets.forEach((ds, di) => {
        const meta = ch.getDatasetMeta(di);
        if (meta.hidden) return;
        const total = tipo === 'doughnut' ? ds.data.reduce((a, b) => a + b, 0) : 0;
        meta.data.forEach((el, i) => {
          const v = ds.data[i];
          if (!v) return;
          const txt = fmt(v), w = ctx.measureText(txt).width;
          if (tipo === 'bar' && horiz) {
            ctx.textBaseline = 'middle';
            const cabe = Math.abs(el.x - el.base) >= w + 14;
            ctx.fillStyle = cabe ? '#fff' : '#0f172a'; ctx.textAlign = cabe ? 'right' : 'left';
            ctx.fillText(txt, cabe ? el.x - 6 : el.x + 6, el.y);
          } else if (tipo === 'bar') {
            ctx.textAlign = 'center';
            const cabe = Math.abs(el.base - el.y) >= 22 && el.width >= w + 4;
            ctx.fillStyle = cabe ? '#fff' : '#0f172a'; ctx.textBaseline = cabe ? 'top' : 'bottom';
            ctx.fillText(txt, el.x, cabe ? el.y + 5 : el.y - 4);
          } else if (tipo === 'line') {
            ctx.fillStyle = '#0f172a'; ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
            ctx.fillText(txt, el.x, el.y - 8);
          } else if (tipo === 'doughnut' && v / total >= 0.06) {
            const p = el.getCenterPoint();
            ctx.fillStyle = '#fff'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
            ctx.fillText(txt, p.x, p.y);
          }
        });
        if (tipo === 'doughnut') {
          const a = ch.chartArea, x = (a.left + a.right) / 2, y = (a.top + a.bottom) / 2;
          ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
          ctx.fillStyle = '#0f172a'; ctx.font = `800 22px ${fonte}`; ctx.fillText(fmt(total), x, y - 6);
          ctx.fillStyle = '#64748b'; ctx.font = `600 11px ${fonte}`; ctx.fillText('total', x, y + 14);
        }
      });
      ctx.restore();
    },
  });

  const charts = {};
  function grafico(id, config, aoClicar) {
    charts[id]?.destroy();
    config.options = Object.assign({maintainAspectRatio: false}, config.options);
    config.options.onHover = (e, els) => { e.native.target.style.cursor = els.length ? 'pointer' : 'default'; };
    config.options.onClick = (_e, els) => { if (els.length) aoClicar(els[0].index, els[0].datasetIndex); };
    charts[id] = new Chart(document.getElementById(id), config);
  }
  const barras = (id, itens, tipo, rot = i => i.rotulo) => grafico(id, {
    type: 'bar',
    data: {labels: itens.map(rot), datasets: [{data: itens.map(i => i.valor), backgroundColor: cores[0], borderRadius: 6}]},
    options: {indexAxis: 'y', plugins: {legend: {display: false}}},
  }, i => abrir(tipo, itens[i].rotulo));
  const rosca = (id, itens, tipo) => grafico(id, {
    type: 'doughnut',
    data: {labels: itens.map(i => `${i.rotulo} · ${fmt(i.valor)}`), datasets: [{data: itens.map(i => i.valor), backgroundColor: cores, borderWidth: 0}]},
    options: {cutout: '62%', plugins: {legend: {position: 'right', labels: {boxWidth: 10}}}},
  }, i => abrir(tipo, itens[i].rotulo));

  // mapa de Fortaleza (SVG sem biblioteca); contornos em static/fortaleza-bairros.geojson
  let geoBairros = null;
  const semAcento = s => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase().trim();
  async function desenharMapa(d) {
    const svg = document.getElementById('mapa-for');
    if (!geoBairros) geoBairros = await fetch('/static/fortaleza-bairros.geojson').then(r => r.json()).catch(() => null);
    if (!geoBairros) return;
    const bairrosValidos = geoBairros.features.every(f =>
      typeof f.properties?.bairro === 'string' && f.properties.bairro.trim());
    const wrapper = svg.closest('.mapa-wrap');
    const total = d.bairros.reduce((s, b) => s + b.valor, 0);
    if (!bairrosValidos) {
      svg.hidden = true;
      wrapper.classList.add('mapa-indisponivel');
      document.getElementById('mapa-nota').textContent = total
        ? `${fmt(total)} atendimentos ativos localizados · ${fmt(d.sem_localizacao)} sem bairro`
        : 'Sem dados de bairro na API';
      document.getElementById('mapa-lista').innerHTML = total
        ? '<p class="desc">O mapa está indisponível porque a base cartográfica não contém nomes de bairros. Dados recebidos por bairro:</p>' +
          '<b>Top bairros</b>' + d.bairros.slice(0, 20).map(b =>
            `<div data-det="bairro" data-valor="${esc(b.rotulo)}"><span>${esc(b.rotulo)}</span><b>${fmt(b.valor)}</b></div>`).join('')
        : '<p class="desc">Sem dados de bairro para exibir.</p>';
      return;
    }
    svg.hidden = false;
    wrapper.classList.remove('mapa-indisponivel');
    const qtd = new Map(d.bairros.map(b => [semAcento(b.rotulo), b.valor]));
    const max = Math.max(1, ...qtd.values());
    const pts = geoBairros.features.flatMap(f => f.geometry.coordinates.flat());
    const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
    const x0 = Math.min(...xs), y1 = Math.max(...ys), k = Math.cos(-3.76 * Math.PI / 180);
    const w = (Math.max(...xs) - x0) * k, h = y1 - Math.min(...ys), ea = 100 / Math.max(w, h);
    svg.setAttribute('viewBox', `0 0 ${(w * ea).toFixed(2)} ${(h * ea).toFixed(2)}`);
    svg.innerHTML = geoBairros.features.map(f => {
      const nome = f.properties.bairro, v = qtd.get(semAcento(nome)) || 0;
      const path = f.geometry.coordinates.map(a => 'M' + a.map(p => `${((p[0] - x0) * k * ea).toFixed(2)},${((y1 - p[1]) * ea).toFixed(2)}`).join('L') + 'Z').join('');
      const fill = v ? `rgba(37,99,235,${(0.2 + 0.8 * v / max).toFixed(2)})` : '#e2e8f0';
      return `<path d="${path}" fill="${fill}" fill-rule="evenodd" stroke="#fff" stroke-width=".25"${v ? ` data-det="bairro" data-valor="${esc(nome)}"` : ''}><title>${esc(nome)} · ${fmt(v)} atendimento(s)</title></path>`;
    }).join('');
    document.getElementById('mapa-nota').textContent = total ? `${fmt(total)} ativos localizados · ${fmt(d.sem_localizacao)} sem bairro` : 'Sem dados de bairro na API';
    document.getElementById('mapa-lista').innerHTML = total
      ? '<b>Top bairros</b>' + d.bairros.slice(0, 10).map(b => `<div data-det="bairro" data-valor="${esc(b.rotulo)}"><span>${esc(b.rotulo)}</span><b>${fmt(b.valor)}</b></div>`).join('')
      : '<p class="desc">Aguardando a API enviar bairro/cidade dos atendimentos. Assim que houver dados, os bairros serão pintados aqui automaticamente.</p>';
  }

  let dados = null, escMotivo = 'mes';
  function desenharMotivos() {
    document.querySelectorAll('#mot-esc button').forEach(b => b.classList.toggle('on', b.dataset.esc === escMotivo));
    const itens = dados.motivos[escMotivo];
    if (!itens.length) { charts['c-motivo']?.destroy(); delete charts['c-motivo']; }
    else barras('c-motivo', itens.map(i => ({...i, rotulo: `${escMotivo}|${i.rotulo}`})), 'motivo', i => i.rotulo.split('|')[1]);
  }
  document.addEventListener('click', e => {
    const b = e.target.closest('#mot-esc button');
    if (b && dados) { escMotivo = b.dataset.esc; desenharMotivos(); }
  });
  function render(d) {
    dados = d;
    const k = d.kpis, meses = d.meses.map(nomeMes);
    document.getElementById('per-rotulo').textContent = (r => r[0].toUpperCase() + r.slice(1))(rotuloPeriodo(d.periodo));
    document.getElementById('atualizado').textContent = d.atualizado_em
      ? 'Dados da API sincronizados em ' + d.atualizado_em.replace('T', ' ') + ' (separados do cadastro principal). Clique nos cards, barras e fatias para ver os registros.'
      : 'Sem sincronização da API.';
    // [cor, título, valor, tipo do detalhe, subitens [rótulo, valor, tipo], explicação]
    const cards = [
      ['azul', 'Atendimentos ativos', k.ativos, 'ativos', [['Admissões', fmt(k.admissoes), 'admissoes'], ['Altas', fmt(k.altas), 'altas']],
        'Atendimentos sem alta na data final do período. Admissões e Altas contam os atendimentos admitidos e com alta dentro do período.'],
      ['agua', 'Visitas no período', fmt(k.visitas), 'visitas', [['Por ativo', k.visitas_por_ativo.toLocaleString('pt-BR'), 'visitas']],
        'Total de visitas realizadas dentro do período. Por ativo = visitas ÷ atendimentos ativos.'],
      ['verde', 'Permanência média', k.permanencia_media + ' d', 'altas', [['Ativos hoje', k.tempo_medio_ativos + ' d', 'ativos']],
        'Média de dias entre admissão e alta dos atendimentos com alta no período. Ativos hoje = média de dias desde a admissão dos atendimentos ativos.'],
      ['navy', 'Profissionais', k.profissionais, 'profissionais', [['No período', 'com visitas', 'profissionais']],
        'Quantidade de profissionais diferentes que registraram ao menos uma visita no período.'],
      ['red', 'Ativos sem visita', k.ativos_sem_visita, 'sem_visita', [['De', fmt(k.ativos), 'ativos']],
        'Atendimentos ativos que não tiveram nenhuma visita no período. Serve como alerta de acompanhamento.'],
      ['verde', 'Monitoramento com terapias', k.monitoramento_terapias, 'monit_terapias', [['Monitoramento', fmt(k.monitoramento_ativos), 'monit_terapias'], ['Com terapias', fmt(k.com_terapias), 'monit_terapias']],
        'Pacientes ativos no serviço de Monitoramento que a API marca com terapias (possui terapias = SIM). Monitoramento e Com terapias mostram os totais de ativos de cada grupo.'],
      ['red', 'Mortalidade', k.mortalidade.toLocaleString('pt-BR') + '%', 'obitos', [['Óbitos', fmt(k.obitos), 'obitos'], ['Atendidos', fmt(k.atendidos), 'obitos']],
        'Óbitos do período ÷ pacientes atendidos no período (admitidos até o fim do período e sem alta antes do início). Óbito = condição de alta "Óbito". Clique para ver quem foi a óbito.'],
      ['azul', 'Terapias pendentes', k.terapias_pendentes, 'pendentes', [['De', fmt(k.com_terapias) + ' com terapias', 'pendentes']],
        `Pacientes ativos com terapias (possui terapias = SIM) sem nenhuma visita nos últimos ${d.janela_terapia} dias. Aproximação: a API não informa a situação da terapia.`],
      ['ambar', 'Relatórios pendentes', fmt(k.relatorios_pendentes), 'relatorios_especialidade', [['Na lista atual', 'da API', 'relatorios_especialidade']],
        'Quantidade de relatórios pendentes informados pela lista atual da API. Não depende do filtro de período.'],
      ['agua', 'Idade média dos ativos', k.idade_media.toLocaleString('pt-BR') + ' anos', 'idade', [['60+ anos', fmt(k.idosos), 'idade'], ['Com idade', fmt(k.idade_informada), 'idade']],
        'Média da idade informada pela API nos atendimentos ativos na data final. 60+ anos conta os ativos idosos; Com idade mostra quantos têm idade válida. Clique para ver os atendimentos.'],
    ];
    document.getElementById('kpis').innerHTML = cards.map(([cor, rot, val, tipo, sub, explica]) =>
      `<div class="kpi ${cor}" data-det="${tipo}"><span>${esc(rot)}<span class="info claro" tabindex="0" data-info="${esc(explica)}"><svg class="ic"><use href="#i-info"/></svg></span></span><strong>${esc(val)}</strong>` +
      `<div>${sub.map(([a, b, t]) => `<span data-det="${t}">${esc(a)}<b>${esc(b)}</b></span>`).join('')}</div></div>`).join('');

    grafico('c-visitas', {
      type: 'line',
      data: {labels: meses, datasets: [{label: 'Visitas', data: d.visitas_mes, borderColor: cores[1], backgroundColor: '#0d948833', fill: true, tension: .3, pointRadius: 4, pointHoverRadius: 7}]},
      options: {layout: {padding: {top: 20}}, plugins: {legend: {display: false}}},
    }, i => abrir('mes_visitas', d.meses[i]));
    grafico('c-fluxo', {
      type: 'bar',
      data: {labels: meses, datasets: [
        {label: 'Admissões', data: d.admissoes_mes, backgroundColor: cores[0], borderRadius: 4},
        {label: 'Altas', data: d.altas_mes, backgroundColor: cores[3], borderRadius: 4}]},
    }, (i, ds) => abrir(ds === 0 ? 'mes_admissoes' : 'mes_altas', d.meses[i]));
    rosca('c-esp', d.especialidades, 'especialidade');
    barras('c-oper', d.operadoras_ativos, 'operadora');
    rosca('c-serv', d.servicos_ativos, 'servico');
    barras('c-prof', d.profissionais, 'profissional');
    rosca('c-alta', d.condicao_alta, 'condicao');
    barras('c-terapia', d.terapias, 'terapia');
    barras('c-cx', d.complexidade, 'complexidade', i => `${i.rotulo} · ${i.pct.toLocaleString('pt-BR')}%`);
    barras('c-atraso', d.pendencias_terapia, 'atraso');

    const linhasDma = [
      ['Altas', 'altas', 'dma_altas', fmt], ['Admitidos', 'admissoes', 'dma_admissoes', fmt],
      ['Óbitos', 'obitos', 'dma_obitos', fmt], ['Mortalidade', 'mortalidade', 'dma_obitos', v => v.toLocaleString('pt-BR') + '%']];
    document.getElementById('t-dma').innerHTML = linhasDma.map(([nome, campo, tipo, f]) =>
      `<tr><td>${nome}</td>` + ['dia', 'mes', 'ano'].map(e => `<td class="r" data-det="${tipo}" data-valor="${e}"><b>${f(d.dma[e][campo])}</b></td>`).join('') + '</tr>').join('');
    document.getElementById('dma-nota').textContent = `Dia ${d.dma.dia.rotulo} · Mês ${d.dma.mes.rotulo.split(' até')[0]} · Ano ${d.dma.ano.rotulo.split(' até')[0]}`;
    desenharMapa(d);
    desenharMotivos();
    barras('c-pend', d.pendentes_operadora, 'pendentes');
    barras('c-idade', d.faixas_etarias, 'idade');
    barras('c-diagnostico', d.diagnosticos, 'diagnostico');
    barras('c-complexidade-api', d.complexidade_informada, 'complexidade_informada');
    barras('c-cidade', d.cidades, 'cidade');
    barras('c-relatorios-especialidade', d.relatorios_pendentes_especialidade, 'relatorios_especialidade');
    barras('c-relatorios-profissional', d.relatorios_pendentes_profissional, 'relatorios_profissional');

    document.getElementById('t-prof').innerHTML = d.profissionais_atend.map(p =>
      `<tr data-det="profissional" data-valor="${esc(p['Profissional'])}"><td>${esc(p['Profissional'])}</td><td>${esc(p['Especialidade principal'])}</td>` +
      `<td class="r">${fmt(p['Visitas'])}</td><td class="r">${fmt(p['Dias com visita'])}</td><td class="r">${fmt(p['Atendimentos'])}</td><td class="r">${fmt(p['Operadoras'])}</td></tr>`).join('')
      || '<tr><td colspan="6">Nenhuma visita no período.</td></tr>';

    document.getElementById('sv-nota').textContent = fmt(k.ativos_sem_visita) + ' no total';
    document.getElementById('t-sv').innerHTML = d.alerta_sem_visita.map(a =>
      `<tr data-det="atendimento" data-valor="${esc(a.id)}"><td>${esc(a.id)}</td><td>${esc(a.operadora)}</td><td>${esc(a.servico)}</td><td>${esc(fmtData(a.admissao))}</td></tr>`).join('')
      || '<tr><td colspan="4">Nenhum atendimento ativo sem visita.</td></tr>';
  }

  // ---------- detalhamento (drill-down) ----------
  const dlg = document.getElementById('dlg-det'), buscaEl = document.getElementById('det-busca');
  const pilha = [];
  let atual = null;

  async function abrir(tipo, valor = '', empilhar = true) {
    const q = new URLSearchParams({tipo, valor, ini: iniEl.value, fim: fimEl.value});
    try {
      const r = await api('/api/analises/detalhe?' + q);
      if (empilhar) pilha.push({tipo, valor});
      atual = r; buscaEl.value = '';
      desenhar();
      if (!dlg.open) dlg.showModal();
    } catch (e) { toast(e.message, true); }
  }

  function desenhar() {
    const r = atual, termo = buscaEl.value.trim().toLowerCase();
    const linhas = termo ? r.linhas.filter(l => l.join(' ').toLowerCase().includes(termo)) : r.linhas;
    document.getElementById('det-t').textContent = r.titulo;
    document.getElementById('det-n').textContent = termo ? `${fmt(linhas.length)} de ${fmt(r.total)}` : `${fmt(r.total)} registro(s)` + (r.truncado ? ` · exibindo os ${fmt(r.linhas.length)} primeiros` : '');
    document.getElementById('det-h').innerHTML = '<tr>' + r.colunas.map(c => `<th>${esc(c)}</th>`).join('') + '</tr>';
    document.getElementById('det-b').innerHTML = linhas.map(l => {
      const alvo = r.drill ? ` data-drill="${esc(r.drill.tipo)}" data-valor="${esc(l[r.drill.col])}" class="clicavel"` : '';
      return `<tr${alvo}>${l.map(c => `<td>${esc(c)}</td>`).join('')}</tr>`;
    }).join('') || `<tr><td colspan="${r.colunas.length}">Nenhum registro.</td></tr>`;
    document.getElementById('det-voltar').hidden = pilha.length < 2;
  }

  buscaEl.addEventListener('input', () => atual && desenhar());
  document.getElementById('det-fechar').onclick = () => dlg.close();
  dlg.addEventListener('close', () => { pilha.length = 0; });
  document.getElementById('det-voltar').onclick = () => {
    pilha.pop();
    const ant = pilha.pop();
    if (ant) abrir(ant.tipo, ant.valor);
  };
  document.getElementById('det-csv').onclick = () => {
    if (!atual) return;
    const cel = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const csv = [atual.colunas, ...atual.linhas].map(l => l.map(cel).join(';')).join('\r\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob(['\ufeff' + csv], {type: 'text/csv;charset=utf-8'}));
    a.download = 'analises-detalhe.csv'; a.click(); URL.revokeObjectURL(a.href);
  };

  document.addEventListener('click', e => {
    if (e.target.closest('.info')) return;
    const linha = e.target.closest('[data-drill]');
    if (linha) return abrir(linha.dataset.drill, linha.dataset.valor);
    const alvo = e.target.closest('[data-det]');
    if (alvo) abrir(alvo.dataset.det, alvo.dataset.valor || '');
  });

  // ---------- filtro de período (mesmo comportamento do Painel BI) ----------
  const refEl = document.getElementById('ref');
  const iniEl = document.getElementById('dt-ini'), fimEl = document.getElementById('dt-fim');
  const botoes = document.querySelectorAll('#presets button');
  const iso = dt => `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
  const marcar = p => botoes.forEach(b => b.classList.toggle('on', b.dataset.p === p));
  const carregar = () => api(`/api/analises?ini=${iniEl.value}&fim=${fimEl.value}`).then(render).catch(e => toast(e.message, true));

  function aplicarPreset(p) {
    const h = new Date(refEl.value + 'T12:00:00'), a = h.getFullYear(), m = h.getMonth();
    const faixa = {
      'mes': [new Date(a, m, 1), h],
      'mes-ant': [new Date(a, m - 1, 1), new Date(a, m, 0)],
      'tri': [new Date(a, m - 2, 1), h],
      'ano': [new Date(a, 0, 1), h],
    }[p];
    if (faixa) { iniEl.value = iso(faixa[0]); fimEl.value = iso(faixa[1]); }
    marcar(p);
    if (p === 'custom') iniEl.focus();
  }
  botoes.forEach(b => b.onclick = () => { aplicarPreset(b.dataset.p); if (b.dataset.p !== 'custom') carregar(); });
  [iniEl, fimEl].forEach(el => el.addEventListener('change', () => {
    if (!iniEl.value || !fimEl.value) return;
    marcar('custom');
    carregar();
  }));
  aplicarPreset('mes');
  carregar();

  // balão do ⓘ: um só, posicionado sobre a página
  const balao = document.createElement('div'); balao.className = 'balao'; document.body.append(balao);
  const mostrar = alvo => {
    balao.textContent = alvo.dataset.info; balao.classList.add('on');
    const r = alvo.getBoundingClientRect(), w = balao.offsetWidth, h = balao.offsetHeight;
    balao.style.left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), innerWidth - w - 8) + 'px';
    balao.style.top = (r.top - h - 10 < 8 ? r.bottom + 10 : r.top - h - 10) + 'px';
  };
  const esconder = () => balao.classList.remove('on');
  document.addEventListener('mouseover', e => { const a = e.target.closest('[data-info]'); a ? mostrar(a) : esconder(); });
  document.addEventListener('focusin', e => { const a = e.target.closest('[data-info]'); if (a) mostrar(a); });
  document.addEventListener('focusout', esconder);
  addEventListener('scroll', esconder, true);
})();

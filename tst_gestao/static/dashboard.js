(() => {
  // pares [cor clara, cor forte] usados nos degradês
  const G = {
    azul: ['#7dd3fc', '#2563eb'], agua: ['#5eead4', '#0d9488'], roxo: ['#c4b5fd', '#7c3aed'], laranja: ['#fde68a', '#f97316'],
    rosa: ['#fda4af', '#e11d48'], verde: ['#86efac', '#16a34a'], navy: ['#94a3b8', '#1e293b'], cinza: ['#e2e8f0', '#cbd5e1'],
  };
  const TERAPIA = {FISIO: 'azul', FONO: 'roxo', NUTRI: 'verde', TO: 'laranja', PSICO: 'agua'};
  const SEQ = ['azul', 'agua', 'roxo', 'laranja', 'rosa', 'verde', 'navy'];
  const corTer = (t, i) => TERAPIA[String(t).toUpperCase()] || SEQ[i % SEQ.length];
  const charts = {};
  const refEl = document.getElementById('ref'), perEl = document.getElementById('per-mot');
  const fonte = getComputedStyle(document.body).fontFamily;
  Object.assign(Chart.defaults, {color: '#64748b'});
  Chart.defaults.font.family = fonte; Chart.defaults.font.size = 12;
  Object.assign(Chart.defaults.plugins.tooltip, {backgroundColor: '#0b1424', padding: 10, cornerRadius: 8, titleFont: {weight: 700}, boxPadding: 4});
  const fmt = v => Number(v || 0).toLocaleString('pt-BR');
  const pct = v => Number(v || 0).toLocaleString('pt-BR', {maximumFractionDigits: 1}) + '%';
  const nomeMes = m => ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'][+m.slice(5) - 1] + '/' + m.slice(2, 4);
  const ic = n => `<svg class="ic"><use href="#i-${n}"/></svg>`;
  const fmtD = s => s.split('-').reverse().join('/');
  const ultimoDiaIso = s => `${s.slice(0, 8)}${String(new Date(+s.slice(0, 4), +s.slice(5, 7), 0).getDate()).padStart(2, '0')}`;
  // período = um único mês começando no dia 1 (mês inteiro ou mês corrente até hoje)
  const periodoEhMes = P => P.ini.slice(0, 7) === P.fim.slice(0, 7) && P.ini.endsWith('-01');
  const MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
  const rotuloPeriodo = P => (periodoEhMes(P)
    ? `${MESES[+P.ini.slice(5, 7) - 1]} de ${P.ini.slice(0, 4)}${P.fim < ultimoDiaIso(P.fim) ? ` · até ${fmtD(P.fim).slice(0, 5)}` : ''}`
    : `${fmtD(P.ini)} a ${fmtD(P.fim)}`);
  const rotuloMeses = r => (r.mes_ini === r.mes_fim ? nomeMes(r.mes_fim) : `${nomeMes(r.mes_ini)} a ${nomeMes(r.mes_fim)}`);

  // degradê que acompanha a área do gráfico (vertical nas colunas, horizontal nas barras deitadas)
  function grad(par, horiz = false, alfa = '') {
    return ctx => {
      const {chart} = ctx, a = chart.chartArea;
      if (!a) return par[1];
      const g = horiz ? chart.ctx.createLinearGradient(a.left, 0, a.right, 0) : chart.ctx.createLinearGradient(0, a.bottom, 0, a.top);
      g.addColorStop(0, par[0] + alfa); g.addColorStop(1, par[1] + alfa);
      return g;
    };
  }

  // valores nas barras (ou no topo da pilha) e total no centro das roscas
  const rotulos = {
    id: 'rotulos',
    afterDatasetsDraw(ch, _a, o) {
      if (o.off) return;
      const {ctx} = ch;
      ctx.save();
      if (ch.config.type === 'bar') {
        const horiz = ch.options.indexAxis === 'y', empilhado = ch.data.datasets.length > 1;
        ctx.font = `700 12px ${fonte}`; ctx.fillStyle = '#0f172a';
        ctx.textAlign = horiz ? 'left' : 'center'; ctx.textBaseline = horiz ? 'middle' : 'bottom';
        const metas = ch.data.datasets.map((_, i) => ch.getDatasetMeta(i)).filter(m => !m.hidden && m.type === 'bar');
        if (!metas.length) return ctx.restore();
        metas[metas.length - 1].data.forEach((el, i) => {
          const v = empilhado ? metas.reduce((s, m) => s + (ch.data.datasets[m.index].data[i] || 0), 0) : ch.data.datasets[0].data[i];
          if (v) ctx.fillText(fmt(v), horiz ? el.x + 6 : el.x, horiz ? el.y : el.y - 5);
        });
      } else if (o.centro) {
        const {left, right, top, bottom} = ch.chartArea, x = (left + right) / 2, y = (top + bottom) / 2;
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.font = `800 26px ${fonte}`; ctx.fillStyle = '#0f172a'; ctx.fillText(o.centro[0], x, y - 8);
        ctx.font = `700 10px ${fonte}`; ctx.fillStyle = '#64748b'; ctx.fillText(o.centro[1], x, y + 14);
      }
      ctx.restore();
    },
  };
  Chart.register(rotulos);

  function novo(id, cfg) { charts[id]?.destroy(); charts[id] = new Chart(document.getElementById(id), cfg); return charts[id]; }

  // aviso quando o dado não foi cadastrado (só "Não informado" ou vazio)
  function aviso(id, dados, oque) {
    const box = document.getElementById(id).parentElement;
    box.querySelector('.vazio-cad')?.remove();
    const util = dados.filter(d => d.total > 0 && !/^(não|sem) informa/i.test(d.label));
    if (util.length) { document.getElementById(id).style.visibility = ''; return false; }
    charts[id]?.destroy(); document.getElementById(id).style.visibility = 'hidden';
    const falta = dados.reduce((s, d) => s + d.total, 0) || aviso.ativos || 0;
    const div = document.createElement('div'); div.className = 'vazio-cad';
    div.innerHTML = `<i class="vc-ic">${ic('aviso')}</i><b>${oque} não preenchido</b><span>${falta ? fmt(falta) + ' pacientes ativos sem esta informação.' : 'Sem dados no período.'}</span>` +
      (falta ? '<a class="btn ghost sm" href="/cadastro/pacientes">Completar cadastro</a>' : '');
    box.append(div);
    return true;
  }

  const semInfo = l => /^(não|sem) informa/i.test(l);
  function barras(id, dados, cor = 'azul', horiz = false, opt = {}) {
    if (opt.aviso && aviso(id, dados, opt.aviso)) return;
    const cores = dados.map((d, i) => (semInfo(d.label) ? G.cinza : opt.porItem ? G[corTer(d.label, i)] : G[cor]));
    novo(id, {
      type: 'bar',
      data: {labels: dados.map(d => d.label), datasets: [{data: dados.map(d => d.total),
        backgroundColor: ctx => grad(cores[ctx.dataIndex] || G[cor], horiz)(ctx), borderRadius: 8, borderSkipped: false,
        maxBarThickness: horiz ? 20 : 48}]},
      options: {
        indexAxis: horiz ? 'y' : 'x', responsive: true, maintainAspectRatio: false,
        layout: {padding: horiz ? {right: 36} : {top: 24}}, plugins: {legend: {display: false}},
        scales: {
          [horiz ? 'x' : 'y']: {display: !horiz, beginAtZero: true, grace: '10%', grid: {color: '#eef2f7'}, border: {display: false}, ticks: {precision: 0}},
          [horiz ? 'y' : 'x']: {grid: {display: false}, border: {display: false}, ticks: {color: '#334155', font: {weight: 600}, autoSkip: false}},
        },
      },
    });
  }

  function rosca(id, dados, centro, opt = {}) {
    if (opt.aviso && aviso(id, dados, opt.aviso)) return;
    const total = dados.reduce((s, d) => s + d.total, 0);
    novo(id, {
      type: 'doughnut',
      data: {labels: dados.map(d => d.label), datasets: [{data: dados.map(d => d.total), borderWidth: 0, spacing: 3, borderRadius: 6, hoverOffset: 8,
        backgroundColor: dados.map((d, i) => (semInfo(d.label) ? '#cbd5e1' : (opt.cores ? opt.cores[i] : G[SEQ[i % SEQ.length]][1])))}]},
      options: {responsive: true, maintainAspectRatio: false, cutout: '70%',
        plugins: {rotulos: {centro: centro || [fmt(total), 'PACIENTES']},
          legend: {display: !opt.semLegenda, position: 'bottom', labels: {usePointStyle: true, pointStyle: 'circle', boxWidth: 8, padding: 12, color: '#0f172a', font: {size: 11.5}}},
          tooltip: {callbacks: {label: c => ` ${c.label}: ${fmt(c.raw)} (${pct(c.raw * 100 / (total || 1))})`}}}},
    });
  }

  function sparkline(canvas, valores, cor = '#2563eb') {
    return new Chart(canvas, {
      type: 'line',
      data: {labels: valores.map((_, i) => i), datasets: [{data: valores, borderColor: cor, borderWidth: 2, tension: .42, fill: true,
        backgroundColor: c => { const a = c.chart.chartArea; if (!a) return cor + '22'; const g = c.chart.ctx.createLinearGradient(0, a.top, 0, a.bottom); g.addColorStop(0, cor + '40'); g.addColorStop(1, cor + '00'); return g; },
        pointRadius: valores.map((_, i) => (i === valores.length - 1 ? 3 : 0)), pointBackgroundColor: cor}]},
      options: {responsive: true, maintainAspectRatio: false, animation: {duration: 900}, layout: {padding: {top: 6, bottom: 2, left: 0, right: 4}},
        plugins: {legend: {display: false}, tooltip: {enabled: false}, rotulos: {off: true}}, scales: {x: {display: false}, y: {display: false, grace: '15%'}}},
    });
  }

  function variacao(atual, anterior, subirEhBom) {
    const dif = atual - anterior;
    if (!dif) return `<span class="var neutra">= mês anterior</span>`;
    const bom = subirEhBom === null ? null : (dif > 0) === subirEhBom;
    return `<span class="var ${bom === null ? 'neutra' : bom ? '' : 'ruim'}">${ic(dif > 0 ? 'sobe' : 'desce')}${dif > 0 ? '+' : ''}${fmt(dif)} vs mês ant.</span>`;
  }

  function kpis(d) {
    const P = d.periodo, A = P.anterior, umMes = periodoEhMes(P);
    const nome = umMes ? 'mês' : 'período', txtPer = umMes ? 'no mês' : 'no período';
    const cards = [
      {i: 'ativos', t: 'Pacientes ativos', v: fmt(P.ativos), dif: P.ativos - A.ativos},
      {i: 'admissao', t: `Admissões ${txtPer}`, v: fmt(P.admissoes), dif: P.admissoes - A.admissoes},
      {i: 'alta', t: `Altas ${txtPer}`, v: fmt(P.altas), dif: P.altas - A.altas},
      {i: 'obito', t: `Óbitos ${txtPer}`, v: fmt(P.obitos), dif: P.obitos - A.obitos},
      {i: 'mortalidade', t: `Mortalidade ${txtPer}`, v: pct(P.mortalidade.taxa), dif: null},
    ];
    // cor forte por card, no modelo "Overview": [início do degradê, fim]
    const COR = [['#3b82f6', '#1d4ed8'], ['#22c55e', '#15803d'], ['#8b5cf6', '#6d28d9'], ['#fb923c', '#ea580c'], ['#14b8a6', '#0e7490']];
    const linha = c => (c.dif === null
      ? `${pct(A.mortalidade.taxa)} no ${nome} anterior · ${pct(d.mortalidade.ano.taxa)} no ano`
      : !c.dif ? `= ${nome} anterior` : `${ic(c.dif > 0 ? 'sobe' : 'desce')}${c.dif > 0 ? '+' : ''}${fmt(c.dif)} vs ${nome} anterior`);
    const ant = `${fmtD(A.ini)} a ${fmtD(A.fim)}`;
    // o que cada card mostra (frase curta) e como é calculado (ⓘ ao passar o mouse)
    const EXPLICA = [
      [`Em atendimento em ${fmtD(P.fim)}`, `Pacientes admitidos até ${fmtD(P.fim)} e sem alta até essa data. A variação compara com ${fmtD(A.fim)} (fim do ${nome} anterior).`],
      ['Pacientes que entraram', `Eventos “Admissão” da Movimentação de ${fmtD(P.ini)} a ${fmtD(P.fim)}. ${nome[0].toUpperCase() + nome.slice(1)} anterior (${ant}): ${A.admissoes}.`],
      ['Pacientes que saíram por alta', `Eventos “Alta” da Movimentação no período (óbitos ficam no card ao lado). ${nome[0].toUpperCase() + nome.slice(1)} anterior (${ant}): ${A.altas}.`],
      ['Falecimentos registrados', `Eventos “Óbito” da Movimentação no período. ${nome[0].toUpperCase() + nome.slice(1)} anterior (${ant}): ${A.obitos}.`],
      ['Óbitos ÷ pacientes atendidos', `Óbitos do período ÷ pacientes atendidos no período (${P.mortalidade.obitos}/${fmt(P.mortalidade.base)}). Atendidos = admitidos até o fim do período e sem alta antes do início. No ano: ${d.mortalidade.ano.obitos} óbitos em ${fmt(d.mortalidade.ano.base)} pacientes.`],
    ];
    document.getElementById('kpis').innerHTML = cards.map((c, i) =>
      `<div class="kx" style="--c0:${COR[i][0]};--c:${COR[i][1]}"><span class="kx-ic">${ic(c.i)}</span>` +
      `<div class="kx-c"><span class="kx-t">${c.t}<span class="info claro" tabindex="0" data-info="${esc(EXPLICA[i][1])}">${ic('info')}</span></span>` +
      `<b>${c.v}</b><em>${EXPLICA[i][0]}</em><small>${linha(c)}</small></div></div>`).join('');
  }

  // lista estilo infográfico: rótulo, valor, % e barra de progresso em degradê
  function lista(id, dados, cor = 'azul', opt = {}) {
    const max = opt.max || 10, total = dados.reduce((s, d) => s + d.total, 0), maior = Math.max(1, ...dados.map(d => d.total));
    const itens = dados.filter(d => d.total > 0 || opt.zeros);
    const html = itens.slice(0, max).map((d, i) => {
      const par = semInfo(d.label) ? G.cinza : opt.porItem ? G[corTer(d.label, i)] : G[cor];
      return `<div class="pl-i ${semInfo(d.label) ? 'cinza' : ''}" style="--c0:${par[0]};--c:${par[1]}"><span title="${esc(d.label)}">${esc(d.label)}</span>` +
        `<em><b>${fmt(d.total)}</b>${opt.semPct ? '' : pct(total ? d.total * 100 / total : 0)}</em><div class="pl-b"><i style="width:${d.total * 100 / maior}%"></i></div></div>`;
    }).join('');
    const resto = itens.length - max;
    document.getElementById(id).innerHTML = (html || '<div class="empty" style="padding:24px">Sem dados no período.</div>') +
      (resto > 0 ? `<div class="pl-mais">+ ${resto} outros</div>` : '');
  }

  function aneis(d) {
    const ind = d.evolucao.indicadores;
    const itens = [
      ['azul', 'Terapias ativas', ind.terapias_ativas, 'terapias', 'Das terapias lançadas nos meses do período, quantas estão com situação “Ativa” (em atendimento).'],
      ['verde', 'Agendadas no sistema', ind.agendadas, 'terapias', 'Terapias do período marcadas com “Agendado = Sim”, ou seja, já lançadas na agenda do sistema.'],
      ['roxo', 'Relatórios enviados', ind.relatorios, 'terapias', 'Terapias do período marcadas com “Relatório = Sim” (relatório do profissional já entregue).'],
      ['laranja', 'Cadastro completo', ind.cadastro_completo, 'pacientes ativos', 'Pacientes ativos com data de nascimento, complexidade e diagnóstico preenchidos. Sem esses campos, os gráficos de idade, complexidade e diagnóstico ficam vazios.'],
    ];
    // o que falta para chegar a 100% — é o número que pede ação
    const FALTA = ['não estão ativas', 'sem agendamento', 'sem relatório', 'com cadastro incompleto'];
    const FUNDO = {azul: '#eff6ff', verde: '#f0fdf4', roxo: '#f5f3ff', laranja: '#fff7ed'};
    document.getElementById('aneis').innerHTML = itens.map(([c, t, v, base, calc], i) => {
      const falta = Math.max(0, (v.total || 0) - (v.parte || 0));
      return `<div class="anel" style="--c:${G[c][1]};--c0:${G[c][0]};--bg:${FUNDO[c]}">` +
        `<div class="a-g"><canvas id="an${i}" width="72" height="72"></canvas><b>${Math.round(v.pct)}<small>%</small></b></div>` +
        `<div class="a-t"><h4>${t}<span class="info" tabindex="0" data-info="${esc(calc)}">${ic('info')}</span></h4>` +
        `<p><strong>${fmt(v.parte)}</strong> de ${fmt(v.total)} ${base}</p>` +
        `<span class="a-falta ${falta ? '' : 'ok'}">${falta ? `${ic('aviso')}${fmt(falta)} ${FALTA[i]}` : `${ic('alta')}tudo em dia`}</span></div></div>`;
    }).join('');
    itens.forEach(([c, , v], i) => novo('an' + i, {
      type: 'doughnut',
      data: {datasets: [{data: [v.pct, 100 - v.pct], borderWidth: 0, borderRadius: [20, 0], spacing: 0,
        backgroundColor: ctx => { if (ctx.dataIndex) return '#e9eef5'; const a = ctx.chart.chartArea; if (!a) return G[c][1]; const g = ctx.chart.ctx.createLinearGradient(a.left, a.bottom, a.right, a.top); g.addColorStop(0, G[c][0]); g.addColorStop(1, G[c][1]); return g; }}]},
      options: {cutout: '72%', responsive: false, animation: {duration: 1100}, events: [], plugins: {legend: {display: false}, tooltip: {enabled: false}}},
    }));
  }

  function medidor(d) {
    const cob = d.evolucao.indicadores.cobertura, r = d.evolucao.resumo_terapias;
    novo('c-gauge', {
      type: 'doughnut',
      data: {datasets: [{data: [cob.pct, 100 - cob.pct], borderWidth: 0, borderRadius: [14, 0],
        backgroundColor: ctx => { if (ctx.dataIndex) return '#eef2f7'; const a = ctx.chart.chartArea; if (!a) return G.agua[1]; const g = ctx.chart.ctx.createLinearGradient(a.left, 0, a.right, 0);
          g.addColorStop(0, '#2dd4bf'); g.addColorStop(.6, '#38bdf8'); g.addColorStop(1, '#2563eb'); return g; }}]},
      options: {rotation: -90, circumference: 180, cutout: '78%', responsive: true, maintainAspectRatio: false, animation: {duration: 1300}, events: [],
        layout: {padding: {top: 8, bottom: 4}}, plugins: {legend: {display: false}, tooltip: {enabled: false}}},
    });
    document.getElementById('gauge-txt').innerHTML = `<b>${pct(cob.pct)}</b><span>${fmt(cob.parte)} de ${fmt(cob.total)} pacientes ativos com terapia ativa</span>`;
    document.getElementById('cob-nota').textContent = rotuloMeses(r);
    const tiles = [
      ['terapias', 'Terapias', fmt(r.terapias), G.azul[1], '#e0f2fe'], ['ativos', 'Pacientes', fmt(r.pacientes), G.agua[1], '#ccfbf1'],
      ['sessoes', 'Sessões', fmt(r.sessoes), G.roxo[1], '#ede9fe'],
      ['dinheiro', 'Valor estimado', 'R$ ' + Number(r.valor).toLocaleString('pt-BR', {maximumFractionDigits: 0}), G.laranja[1], '#ffedd5'],
    ];
    document.getElementById('ter-tiles').innerHTML = tiles.map(([i, t, v, c, bg]) => `<div class="tile" style="--c:${c};--bgc:${bg}"><small>${ic(i)}${t}</small><b>${v}</b></div>`).join('');
  }

  function evolucao(d) {
    const s = d.evolucao.carteira, labels = s.map(m => nomeMes(m.mes));
    const series = [['Admissões', 'admissoes', 'agua'], ['Altas', 'altas', 'roxo'], ['Óbitos', 'obitos', 'rosa']];
    document.getElementById('evo-leg').innerHTML = `<span style="--c:${G.azul[1]}"><i></i>Pacientes ativos</span>` +
      series.map(([t, , c]) => `<span style="--c:${G[c][1]}"><i></i>${t}</span>`).join('');
    novo('c-evo', {
      data: {labels, datasets: [
        {type: 'line', label: 'Pacientes ativos', data: s.map(m => m.ativos), yAxisID: 'y', order: 0, borderColor: '#2563eb', borderWidth: 3, tension: .4, fill: true,
          backgroundColor: c => { const a = c.chart.chartArea; if (!a) return '#2563eb22'; const g = c.chart.ctx.createLinearGradient(0, a.top, 0, a.bottom); g.addColorStop(0, '#3b82f655'); g.addColorStop(1, '#3b82f600'); return g; },
          pointRadius: 4, pointHoverRadius: 7, pointBackgroundColor: '#fff', pointBorderColor: '#2563eb', pointBorderWidth: 2.5},
        ...series.map(([t, k, c]) => ({type: 'bar', label: t, data: s.map(m => m[k]), yAxisID: 'y1', order: 1, backgroundColor: grad(G[c]),
          borderRadius: 6, borderSkipped: false, maxBarThickness: 16, categoryPercentage: .55})),
      ]},
      options: {responsive: true, maintainAspectRatio: false, interaction: {mode: 'index', intersect: false},
        plugins: {legend: {display: false}, rotulos: {off: true}},
        scales: {
          x: {grid: {display: false}, border: {display: false}, ticks: {color: '#334155', font: {weight: 600}}},
          y: {position: 'left', beginAtZero: true, grace: '10%', grid: {color: '#eef2f7'}, border: {display: false}, title: {display: true, text: 'ativos', color: '#94a3b8'}},
          y1: {position: 'right', beginAtZero: true, grace: '30%', grid: {display: false}, border: {display: false}, ticks: {precision: 0}, title: {display: true, text: 'eventos', color: '#94a3b8'}},
        }},
    });
  }

  function situacao(d) {
    const dados = d.evolucao.situacao_terapias, total = dados.reduce((s, x) => s + x.total, 0);
    const ativa = dados.find(x => /^ativa$/i.test(x.label))?.total || 0;
    const COR = {ativa: '#16a34a', pendente: '#f59e0b', 'a confirmar': '#94a3b8', hospitalizado: '#7c3aed', 'não prorrogada': '#64748b', cancelada: '#e11d48', 'óbito': '#1e293b', suspensa: '#0ea5e9', encerrada: '#334155'};
    document.getElementById('sit-nota').textContent = `${fmt(total)} terapias · ${rotuloMeses(d.evolucao.resumo_terapias)}`;
    const cores = dados.map((x, i) => COR[x.label.toLowerCase()] || G[SEQ[i % SEQ.length]][1]);
    rosca('c-sit', dados, [pct(total ? ativa * 100 / total : 0), 'ATIVAS'], {cores, semLegenda: true});
    document.getElementById('sit-leg').innerHTML = dados.map((x, i) =>
      `<div style="--c:${cores[i]}"><i></i><span>${esc(x.label)}</span><b>${fmt(x.total)}</b><em>${pct(total ? x.total * 100 / total : 0)}</em></div>`).join('');
  }

  // infográfico: uma coluna colorida por mês, cabeçalho com o mês, total na barra, divisão por tipo embaixo e linha de tendência
  function terapiasMes(d) {
    const e = d.evolucao, n = e.meses.length;
    const ARCO = [['#8b6fd6', '#5b3fa0'], ['#5b8def', '#2f4fb0'], ['#38c3e0', '#118aa8'], ['#58c98a', '#23935a'],
      ['#b5dd5a', '#7fb52c'], ['#ffd95a', '#e8b10f'], ['#ffb04a', '#f07f12'], ['#ff7f5c', '#e0461f']];
    const cor = i => ARCO[Math.round(i * (ARCO.length - 1) / Math.max(1, n - 1))];
    const totais = e.meses.map((_, i) => e.terapias_mes.reduce((s, t) => s + t.valores[i], 0));
    const max = Math.max(1, ...totais), piso = Math.min(...totais) * 0.55;
    const altura = t => Math.max(14, Math.round((t - piso) * 100 / Math.max(1, max - piso)));  // realça a diferença entre os meses
    const curto = t => ({FISIO: 'Fisio', FONO: 'Fono', NUTRI: 'Nutri', TO: 'TO', PSICO: 'Psico'}[String(t).toUpperCase()] || t);
    // de cima para baixo: linha de tendência com a variação em cada ponto → mês → coluna → divisão por tipo
    const estilo = i => `--c0:${cor(i)[0]};--c:${cor(i)[1]};--h:${altura(totais[i])}%`;
    const cols = e.meses.map((m, i) => {
      const tipos = e.terapias_mes.filter(t => t.valores[i]).map(t => `<span><i style="background:${G[corTer(t.terapia, 0)][1]}"></i>${esc(curto(t.terapia))} <b>${t.valores[i]}</b></span>`).join('');
      return `<div class="tmi-col" style="${estilo(i)}"><div class="tmi-cab"><small>${m.slice(0, 4)}</small><b>${MESES[+m.slice(5) - 1].slice(0, 3).toUpperCase()}</b></div>` +
        `<div class="tmi-trilho"><div class="tmi-barra"><b>${fmt(totais[i])}</b></div></div><div class="tmi-base"></div>` +
        `<div class="tmi-leg">${tipos}</div></div>`;
    }).join('');
    // linha de tendência: pontos na altura do total do mês, com a variação sobre o mês anterior escrita no ponto
    const mn = Math.min(...totais), W = 1000, H = 80;
    const pts = totais.map((t, i) => [((i + .5) / n) * W, H - 14 - ((t - mn) / Math.max(1, max - mn)) * (H - 44)]);
    const variacao = i => {
      if (!i) return ['início', ''];
      const dif = totais[i] - totais[i - 1];
      return [dif > 0 ? `▲ +${dif}` : dif < 0 ? `▼ ${dif}` : '= 0', dif > 0 ? 'sobe' : dif < 0 ? 'desce' : ''];
    };
    const svg = `<svg class="tmi-linha" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><defs><linearGradient id="tmi-g" x1="0" x2="1">` +
      ARCO.map((c, i) => `<stop offset="${i / (ARCO.length - 1)}" stop-color="${c[1]}"/>`).join('') + `</linearGradient></defs>` +
      `<polyline points="${pts.map(p => p.join(',')).join(' ')}" fill="none" stroke="url(#tmi-g)" stroke-width="3" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>` +
      `<div class="tmi-pts">${pts.map((p, i) => { const [txt, cls] = variacao(i);
        return `<i style="left:${p[0] / 10}%;top:${p[1] * 100 / H}%;background:${cor(i)[1]}"></i><em class="${cls}" style="left:${p[0] / 10}%;top:${p[1] * 100 / H}%">${txt}</em>`; }).join('')}</div>`;
    document.getElementById('tm-info').innerHTML = `<div class="tmi-tend">${svg}</div><div class="tmi-cols">${cols}</div>`;
  }

  function ranking(d) {
    const lista = d.evolucao.profissionais.slice(0, 7), max = Math.max(1, ...lista.map(p => p.total));
    const cores = ['#2563eb', '#0d9488', '#7c3aed', '#f97316', '#e11d48', '#16a34a', '#0ea5e9', '#334155'];
    document.getElementById('prof-nota').textContent = rotuloMeses(d.evolucao.resumo_terapias);
    document.getElementById('prof-lista').innerHTML = lista.map((p, i) => {
      const ini = p.nome.split(' ').filter(w => w.length > 2).slice(0, 2).map(w => w[0]).join('').toUpperCase() || p.nome[0];
      return `<div class="rk" style="--c:${cores[i % cores.length]}"><span class="pos">${i + 1}º</span><span class="av">${esc(ini)}</span>` +
        `<div class="nm"><b>${esc(p.nome)}</b><small>${esc(p.terapias)}</small><div class="barra"><i style="width:${p.total * 100 / max}%"></i></div></div>` +
        `<div class="nt">${p.total}<small>terapias</small></div></div>`;
    }).join('') || '<div class="empty">Sem terapias com profissional no mês.</div>';
  }

  // ---------- filtro de período ----------
  const iniEl = document.getElementById('dt-ini'), fimEl = document.getElementById('dt-fim');
  const iso = dt => `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
  function aplicarPreset(p) {
    const h = new Date(refEl.value + 'T12:00:00'), a = h.getFullYear(), m = h.getMonth();
    const faixa = {
      'mes': [new Date(a, m, 1), h],
      'mes-ant': [new Date(a, m - 1, 1), new Date(a, m, 0)],
      'tri': [new Date(a, m - 2, 1), h],
      'ano': [new Date(a, 0, 1), h],
    }[p];
    if (faixa) { iniEl.value = iso(faixa[0]); fimEl.value = iso(faixa[1]); }
    document.querySelectorAll('#presets button').forEach(b => b.classList.toggle('on', b.dataset.p === p));
    if (p === 'custom') iniEl.focus();
  }
  document.querySelectorAll('#presets button').forEach(b => b.onclick = () => {
    aplicarPreset(b.dataset.p);
    if (b.dataset.p !== 'custom') carregar().catch(e => toast(e.message, true));
  });
  [iniEl, fimEl].forEach(el => el.addEventListener('change', () => {
    if (!iniEl.value || !fimEl.value) return;
    document.querySelectorAll('#presets button').forEach(b => b.classList.toggle('on', b.dataset.p === 'custom'));
    carregar().catch(e => toast(e.message, true));
  }));
  aplicarPreset('mes');

  async function carregar() {
    const d = await api(`/api/bi?ini=${iniEl.value}&fim=${fimEl.value}`);
    const rot = rotuloPeriodo(d.periodo); document.getElementById('per-rotulo').textContent = rot[0].toUpperCase() + rot.slice(1);
    aviso.ativos = d.ativos; kpis(d); aneis(d); medidor(d); evolucao(d); situacao(d); terapiasMes(d); ranking(d);
    lista('l-pend', d.pendencias, 'laranja', {porItem: true, zeros: true, semPct: true});
    lista('l-mot', d.motivos.dados, 'verde', {max: 8});
    lista('l-bairro', d.bairros, 'azul');
    lista('l-cidade', d.cidades, 'agua');
    lista('l-oper', d.operadoras, 'roxo');
    lista('l-serv', d.servicos, 'laranja');
    rosca('c-cx', d.complexidade.map(c => ({label: c.label, total: c.total})), null, {aviso: 'Complexidade'});
    barras('c-idade', d.idade.faixas, 'laranja', false, {aviso: 'Data de nascimento'});
    document.getElementById('idade-media').textContent = d.idade.media ? `média ${d.idade.media.toLocaleString('pt-BR')} anos` : '';
    barras('c-diag', d.diagnosticos.slice(0, 10), 'verde', true, {aviso: 'Diagnóstico'});
    const tot = d.servico_operadora.reduce((a, r) => a + r.total, 0);
    document.getElementById('so-total').textContent = `${fmt(tot)} pacientes ativos`;
    document.querySelector('#t-so tbody').innerHTML = d.servico_operadora.map(r => {
      const p = tot ? r.total * 100 / tot : 0;
      return `<tr><td class="forte">${esc(r.servico)}</td><td>${esc(r.operadora)}</td><td class="r forte">${r.total}</td>` +
        `<td><div style="display:flex;align-items:center;gap:10px"><div style="flex:1;height:8px;background:#eef2f7;border-radius:99px;overflow:hidden">` +
        `<div style="width:${p}%;height:100%;background:linear-gradient(90deg,#38bdf8,#2563eb);border-radius:99px"></div></div><span class="muted" style="width:48px;text-align:right">${pct(p)}</span></div></td></tr>`;
    }).join('') || '<tr><td colspan="4" class="muted">Sem dados.</td></tr>';
  }

  // balão do ⓘ: um só, posicionado sobre a página (não é cortado pelos cards)
  const balao = document.createElement('div'); balao.className = 'balao'; document.body.append(balao);
  const mostrar = alvo => {
    balao.textContent = alvo.dataset.info; balao.classList.add('on');
    const r = alvo.getBoundingClientRect(), w = balao.offsetWidth, h = balao.offsetHeight;
    const x = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), innerWidth - w - 8);
    const y = r.top - h - 10 < 8 ? r.bottom + 10 : r.top - h - 10;
    balao.style.left = x + 'px'; balao.style.top = y + 'px';
  };
  const esconder = () => balao.classList.remove('on');
  document.addEventListener('mouseover', e => { const a = e.target.closest('[data-info]'); a ? mostrar(a) : esconder(); });
  document.addEventListener('focusin', e => { const a = e.target.closest('[data-info]'); if (a) mostrar(a); });
  document.addEventListener('focusout', esconder);
  addEventListener('scroll', esconder, true);

  carregar().catch(e => toast(e.message, true));
})();

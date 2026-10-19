(() => {
  const PAL = ['#1ea7f0', '#0b84c6', '#14b8a6', '#6366f1', '#f59e0b', '#ef4444', '#8b5cf6', '#64748b', '#22c55e', '#ec4899'];
  const charts = {};
  const refEl = document.getElementById('ref'), perEl = document.getElementById('per-mot');

  function grafico(id, tipo, dados, opt = {}) {
    charts[id]?.destroy();
    const horiz = opt.horizontal;
    charts[id] = new Chart(document.getElementById(id), {
      type: tipo,
      data: {
        labels: dados.map(d => d.label),
        datasets: [{data: dados.map(d => d.total), backgroundColor: tipo === 'bar' ? PAL[0] : PAL, borderWidth: 0, borderRadius: 4}],
      },
      options: {
        indexAxis: horiz ? 'y' : 'x', responsive: true, maintainAspectRatio: false,
        plugins: {legend: {display: tipo !== 'bar', position: window.innerWidth < 700 ? 'bottom' : 'right', labels: {boxWidth: 12}}},
        scales: tipo === 'bar' ? {[horiz ? 'x' : 'y']: {beginAtZero: true, ticks: {precision: 0}}} : {},
      },
    });
  }

  function kpi(titulo, v, extra = '', cls = '') {
    return `<div class="kpi ${cls}"><span>${titulo}</span><strong>${v}</strong>${extra}</div>`;
  }
  const trio = o => `<div><span><b>${o.dia}</b>dia</span><span><b>${o.mes}</b>mês</span><span><b>${o.ano}</b>ano</span></div>`;

  async function carregar() {
    const d = await api(`/api/bi?ref=${refEl.value}&periodo=${perEl.value}`);
    document.getElementById('kpis').innerHTML =
      kpi('Pacientes ativos', d.ativos) +
      kpi('Admissões', d.admissoes.mes, trio(d.admissoes)) +
      kpi('Altas', d.altas.mes, trio(d.altas)) +
      kpi('Óbitos', d.obitos.mes, trio(d.obitos), 'red') +
      kpi('Mortalidade (mês)', d.mortalidade.mes.taxa.toLocaleString('pt-BR') + '%',
        `<div><span><b>${d.mortalidade.ano.taxa.toLocaleString('pt-BR')}%</b>ano</span><span><b>${d.mortalidade.mes.obitos}/${d.mortalidade.mes.base}</b>óbitos/base</span></div>`, 'red');

    grafico('c-pend', 'bar', d.pendencias);
    grafico('c-mot', 'bar', d.motivos.dados, {horizontal: true});
    grafico('c-cx', 'doughnut', d.complexidade.map(c => ({label: `${c.label} (${c.pct}%)`, total: c.total})));
    grafico('c-idade', 'bar', d.idade.faixas);
    document.getElementById('idade-media').textContent = `média: ${d.idade.media.toLocaleString('pt-BR')} anos`;
    grafico('c-bairro', 'bar', d.bairros, {horizontal: true});
    grafico('c-cidade', 'bar', d.cidades, {horizontal: true});
    grafico('c-diag', 'bar', d.diagnosticos, {horizontal: true});
    grafico('c-serv', 'doughnut', d.servicos);
    grafico('c-oper', 'doughnut', d.operadoras);
    document.querySelector('#t-so tbody').innerHTML =
      d.servico_operadora.map(r => `<tr><td>${esc(r.servico)}</td><td>${esc(r.operadora)}</td><td class="r">${r.total}</td></tr>`).join('') ||
      '<tr><td colspan="3" class="muted">Sem dados.</td></tr>';
  }

  refEl.onchange = perEl.onchange = () => carregar().catch(e => toast(e.message, true));
  carregar().catch(e => toast(e.message, true));
})();

/* Configuração única dos gráficos (Chart.js): cores por variável CSS, marcas finas, eixos discretos,
   tooltip em todo gráfico e clique abrindo o detalhamento. */
const Graficos = (() => {
  const css = getComputedStyle(document.documentElement);
  const v = n => css.getPropertyValue(n).trim();
  const COR = {
    acc: v('--acc'), tx: v('--tx'), tx2: v('--tx2'), mut: v('--mut'), linha: v('--line-2'), crit: v('--crit'),
    s: [1, 2, 3, 4, 5, 6, 7, 8].map(i => v('--s' + i)),
    terapia: {FISIO: v('--t-fisio'), FONO: v('--t-fono'), TO: v('--t-to'), NUTRI: v('--t-nutri'), PSICO: v('--t-psico')},
    nivel: [v('--n1'), v('--n2'), v('--n3')],
  };
  const fonte = getComputedStyle(document.body).fontFamily;
  Chart.defaults.font.family = fonte;
  Chart.defaults.font.size = 12;
  Chart.defaults.color = COR.mut;
  Chart.defaults.maintainAspectRatio = false;
  Object.assign(Chart.defaults.plugins.tooltip, {backgroundColor: v('--menu'), padding: 10, cornerRadius: 6, boxPadding: 4,
    titleFont: {weight: 700}, callbacks: {label: c => ` ${c.dataset.label ? c.dataset.label + ': ' : ''}${c.formattedValue}${c.dataset.sufixo || ''}`}});
  Chart.defaults.plugins.legend.labels.boxWidth = 10;
  Chart.defaults.plugins.legend.labels.boxHeight = 10;

  // rótulos seletivos: valor no topo das barras (conjuntos pequenos) e no último ponto das linhas
  Chart.register({
    id: 'rotulosTST',
    afterDatasetsDraw(ch, _a, o) {
      if (!o || !o.ativo) return;
      const {ctx} = ch;
      ctx.save(); ctx.font = `600 11.5px ${fonte}`; ctx.fillStyle = COR.tx2; ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
      ch.data.datasets.forEach((ds, di) => {
        const meta = ch.getDatasetMeta(di);
        if (meta.hidden) return;
        meta.data.forEach((el, i) => {
          const val = ds.data[i];
          if (!val || (meta.type === 'line' && i !== ds.data.length - 1)) return;
          ctx.fillText(Number(val).toLocaleString('pt-BR') + (ds.sufixo || ''), el.x, el.y - 6);
        });
      });
      ctx.restore();
    },
  });

  const charts = {};
  const eixos = (sufixo = '') => ({
    x: {grid: {display: false}, border: {color: COR.linha}, ticks: {maxRotation: 0, autoSkip: true}},
    y: {beginAtZero: true, grid: {color: COR.linha}, border: {display: false}, ticks: {precision: 0, callback: x => x.toLocaleString('pt-BR') + sufixo}},
  });
  function criar(id, config, aoClicar) {
    charts[id]?.destroy();
    const o = config.options = config.options || {};
    o.interaction = {mode: config.type === 'line' ? 'index' : 'nearest', intersect: config.type !== 'line'};
    o.onHover = (e, els) => { e.native.target.style.cursor = els.length && aoClicar ? 'pointer' : 'default'; };
    if (aoClicar) o.onClick = (_e, els) => { if (els.length) aoClicar(els[0].index, els[0].datasetIndex); };
    charts[id] = new Chart($(id), config);
    return charts[id];
  }

  return {
    COR,
    /* série mensal única (linha 2px, pontos 4px) */
    linha(id, rotulos, dados, {rotulo = '', cor = COR.acc, sufixo = '', aoClicar} = {}) {
      return criar(id, {type: 'line',
        data: {labels: rotulos, datasets: [{label: rotulo, data: dados, sufixo, borderColor: cor, backgroundColor: cor, borderWidth: 2,
          pointRadius: 4, pointHoverRadius: 6, pointBackgroundColor: '#fff', pointBorderWidth: 2, tension: 0}]},
        options: {layout: {padding: {top: 22, right: 12}}, scales: eixos(sufixo), plugins: {legend: {display: false}, rotulosTST: {ativo: true}}},
      }, aoClicar);
    },
    /* colunas (uma ou mais séries lado a lado, mesma escala) */
    colunas(id, rotulos, series, {aoClicar, rotulosValor = false, sufixo = ''} = {}) {
      return criar(id, {type: 'bar',
        data: {labels: rotulos, datasets: series.map(s => ({label: s.rotulo, data: s.dados, backgroundColor: s.cor, sufixo,
          borderRadius: {topLeft: 4, topRight: 4}, borderSkipped: 'bottom', maxBarThickness: 34, barPercentage: .75, categoryPercentage: .8,
          borderColor: '#fff', borderWidth: series.length > 1 ? {left: 1, right: 1} : 0}))},
        options: {layout: {padding: {top: rotulosValor ? 20 : 4}}, scales: eixos(sufixo),
          plugins: {legend: {display: series.length > 1, position: 'top', align: 'start'}, rotulosTST: {ativo: rotulosValor}}},
      }, aoClicar);
    },
  };
})();

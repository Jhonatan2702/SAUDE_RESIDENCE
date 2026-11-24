/* Painel BI (gestor/admin). Um único carregamento por período; cada aba só desenha o que já chegou. */
(() => {
  const G = Graficos, C = G.COR;
  const NOMES = {FISIO: 'Fisioterapia', FONO: 'Fonoaudiologia', TO: 'Terapia ocupacional', NUTRI: 'Nutrição', PSICO: 'Psicologia'};
  let d = null, escMotivo = 'mes';
  const desenhadas = new Set();

  const det = Detalhe((tipo, valor) => {
    if (tipo === 'ficha') { FichaBairro.abrir(valor); return null; }
    if (tipo === 'paciente') { Ficha.abrir('paciente', valor); return null; }  // resumo completo do paciente
    const P = periodo.valor();
    return api('/api/painel/detalhe?' + new URLSearchParams({tipo, valor, ini: P.ini, fim: P.fim}));
  });
  const abas = window.ABAS = Abas(nome => desenhar(nome));
  const periodo = Periodo(() => carregar());
  FichaBairro.configurar(() => periodo.valor());

  const tObitos = Tabela('t-obitos', {aoClicar: l => det.abrir('paciente', l[0]), numericas: [7], vazio: 'Nenhum óbito no período.'});
  const tProf = Tabela('t-prof', {aoClicar: l => Ficha.abrir('profissional', l[6]), numericas: [2, 3, 4, 5], vazio: 'Nenhuma visita no período.'});
  const tAbr = Tabela('t-abr', {busca: 'abr-busca', contador: 'abr-n', numericas: [5, 6], vazio: 'Nenhuma visita no período.',
    aoClicar: l => FichaBairro.abrir(l[3])});

  async function carregar() {
    const P = periodo.valor();
    $('sub-periodo').textContent = 'Período: ' + rotuloPeriodo(P) + ' · dados da URL Saúde Residence';
    try {
      d = await api(`/api/painel?ini=${P.ini}&fim=${P.fim}`);
      desenhadas.clear();
      desenhar(abas.atual());
      api(`/api/operacional/abrangencia?ini=${P.ini}&fim=${P.fim}`).then(a => tAbr.dados(a.colunas, a.linhas)).catch(e => toast(e.message, true));
    } catch (e) { toast(e.message, true); }
  }

  function desenhar(aba) {
    if (!d || desenhadas.has(aba)) return;
    desenhadas.add(aba);
    ({geral, mapa: mapaAba, terapias, complexidade, movimentacao, perfil, profissionais})[aba]?.();
  }

  // ------------------------------------------------------------ Visão geral
  function geral() {
    const k = d.kpis, meses = d.meses.map(nomeMes);
    kpis('k-geral', [
      {tom: 'acc', icone: 'ativos', rotulo: 'Pacientes ativos', valor: fmt(k.pacientes_ativos), det: 'ativos',
        sub: `<b>${fmt(k.atendimentos_ativos)}</b> atendimentos ativos`, info: 'Pessoas distintas com ao menos um atendimento sem alta na data final do período. Um paciente pode ter mais de um atendimento (serviços diferentes).'},
      {tom: 'acc', icone: 'terapias', rotulo: 'Pacientes com terapias', valor: fmt(k.com_terapias), det: 'com_terapias',
        sub: `de <b>${fmt(k.pacientes_ativos)}</b> pacientes ativos`, info: 'Pacientes ativos com ao menos um atendimento ativo indicado com terapias pela URL (possui terapias = SIM) ou com visita de Fisio, Fono, TO, Nutri ou Psico.'},
      {tom: 'acc', icone: 'terapias', rotulo: 'Monitoramento com terapias', valor: fmt(k.monit_terapias), det: 'monit_terapias',
        sub: `de <b>${fmt(k.monitoramento)}</b> pacientes em monitoramento`, info: 'Pacientes ativos no serviço Monitoramento que a URL indica com terapias (possui terapias = SIM).'},
      {tom: 'crit', icone: 'mortalidade', rotulo: 'Mortalidade', valor: fmtPct(k.mortalidade), det: 'obitos',
        sub: `<b>${fmt(k.obitos)}</b> óbito(s) de ${fmt(k.atendidos)} atendidos`, info: 'Pacientes que foram a óbito no período ÷ pacientes atendidos no período (admitidos até o fim e sem alta antes do início). Clique para ver quem foi a óbito.'},
      {tom: 'warn', icone: 'pendencia', rotulo: 'Pacientes com terapia pendente', valor: fmt(k.pendentes), det: 'pendentes',
        sub: `de <b>${fmt(k.em_terapia)}</b> pacientes em terapia`, info: `Pacientes ativos sem visita há mais de ${d.janelas.atraso} dias numa terapia em andamento, ou indicados com terapias e sem nenhuma visita de terapia em ${d.janelas.terapia} dias.`},
      {tom: 'ok', icone: 'admissao', rotulo: 'Admissões com terapias', valor: fmt(k.admissoes_terapias), det: 'admissoes', valorDet: 'terapias',
        sub: `<b>${fmt(k.admissoes)}</b> admissões no período (todos os serviços)`,
        info: 'Atendimentos admitidos no período que são indicados com terapias pela URL (possui terapias = SIM) ou que já tiveram visita de terapia. A observação mostra todas as admissões do período.'},
      {tom: 'acc', icone: 'alta', rotulo: 'Altas com terapias', valor: fmt(k.altas_terapias), det: 'altas', valorDet: 'terapias',
        sub: `<b>${fmt(k.altas)}</b> altas no período · <b>${fmt(k.obitos)}</b> óbito(s) à parte`,
        info: 'Atendimentos com terapias (indicados pela URL ou com visita de terapia) que receberam alta no período, por qualquer motivo exceto óbito. Clique para ver os pacientes, a data e o motivo da alta.'},
      {tom: 'neutro', icone: 'evolucao', rotulo: 'Visitas no período', valor: fmt(k.visitas), det: 'visitas',
        sub: `<b>${fmt(k.pacientes_visitados)}</b> pacientes ativos visitados`, info: 'Visitas registradas pelos profissionais dentro do período.'},
      {tom: 'warn', icone: 'aviso', rotulo: 'Ativos sem visita no período', valor: fmt(k.sem_visita), det: 'sem_visita',
        sub: 'Monitoramento, ID, Plantão e Serv. Prof. Não Méd.', info: 'Pacientes ativos na data final, em Monitoramento, Internação domiciliar, Plantão ou Serv. Prof. Não Méd., que não tiveram nenhuma visita dentro do período.'},
      {tom: 'warn', icone: 'relatorios', rotulo: 'Relatórios pendentes', valor: fmt(k.relatorios_recentes), det: 'relatorios',
        sub: `2 últimos meses · <b>${fmt(k.relatorios_pendentes)}</b> no total`, info: 'Relatórios pendentes enviados pela URL com competência do ano atual e dos 2 últimos meses (mês atual e anterior). No detalhe, desmarque os filtros para ver todos. Não depende do período.'},
    ]);
    G.linha('c-visitas', meses, d.visitas_mes, {rotulo: 'Visitas', aoClicar: i => det.abrir('mes_visitas', d.meses[i])});
    G.colunas('c-fluxo', meses, [
      {rotulo: 'Admissões', dados: d.admissoes_mes, cor: C.s[0]}, {rotulo: 'Altas', dados: d.altas_mes, cor: C.s[2]},
      {rotulo: 'Óbitos', dados: d.obitos_mes, cor: C.s[1]},
    ], {aoClicar: (i, s) => det.abrir(['mes_admissoes', 'mes_altas', 'mes_obitos'][s], d.meses[i])});
  }

  // ------------------------------------------------------------ Terapias
  function terapias() {
    const k = d.kpis, J = d.janelas;
    kpis('k-terapias', [
      {tom: 'acc', icone: 'terapias', rotulo: 'Pacientes em terapia', valor: fmt(k.em_terapia), det: 'em_terapia',
        sub: `com visita de terapia nos últimos ${J.terapia} dias`, info: `Pacientes ativos com ao menos uma visita de Fisio, Fono, TO, Nutri ou Psico nos ${J.terapia} dias até a data final.`},
      {tom: 'acc', icone: 'ativos', rotulo: 'Monitoramento com terapias', valor: fmt(k.monit_terapias), det: 'monit_terapias',
        sub: `de <b>${fmt(k.monitoramento)}</b> em monitoramento`, info: 'Pacientes ativos no serviço Monitoramento indicados com terapias pela URL.'},
      {tom: 'warn', icone: 'pendencia', rotulo: 'Pacientes com terapia pendente', valor: fmt(k.pendentes), det: 'pendentes',
        sub: 'em ao menos uma terapia', info: 'Pacientes distintos (sem duplicar quem está pendente em mais de uma terapia).'},
      {tom: 'crit', icone: 'aviso', rotulo: 'Indicados sem nenhuma terapia', valor: fmt(k.sem_atendimento_terapia), det: 'pendentes', valorDet: 'SEM',
        sub: `sem visita de terapia em ${J.terapia} dias`, info: 'Pacientes ativos que a URL marca com terapias (possui terapias = SIM), mas sem nenhuma visita de terapia na janela.'},
    ]);
    $('ter-blocos').innerHTML = d.terapias.map(t => `<button type="button" class="ter" style="--c:${corTerapia(t.sigla)}" data-det="em_terapia" data-valor="${esc(t.sigla)}">` +
      `<span class="t-sig"><i></i>${esc(t.sigla)}</span><div class="t-val">${fmt(t.pacientes)}</div><div class="t-nome">pacientes em ${esc(t.nome.toLowerCase())}</div>` +
      `<div class="t-sub"><span><b>${fmt(t.pacientes_periodo)}</b> no período</span><span><b>${fmt(t.visitas_periodo)}</b> visitas</span>` +
      `<span class="pend"><b>${fmt(t.pendentes)}</b> pendentes</span></div></button>`).join('');
    const pend = d.terapias.filter(t => t.pendentes).map(t => ({rotulo: t.sigla, nome: t.nome, valor: t.pendentes}))
      .sort((a, b) => b.valor - a.valor);
    pend.push({rotulo: 'SEM', nome: `Indicados com terapias, sem nenhuma visita (${J.terapia} d)`, valor: k.sem_atendimento_terapia});
    $('pend-nota').textContent = `${fmt(k.pendentes)} paciente(s) distinto(s)`;
    listaBarras('l-pend', pend, {det: 'pendentes', rotulo: i => i.nome, cor: i => i.rotulo === 'SEM' ? 'var(--crit)' : corTerapia(i.rotulo), max: 10});
    const vis = d.terapias.filter(t => t.visitas_periodo);
    G.colunas('c-ter-visitas', vis.map(t => t.sigla), [{rotulo: 'Visitas', dados: vis.map(t => t.visitas_periodo), cor: vis.map(t => C.terapia[t.sigla] || C.s[6])}],
      {rotulosValor: true, aoClicar: i => det.abrir('terapia_visitas', vis[i].sigla)});
  }

  // ------------------------------------------------------------ Complexidade
  function complexidade() {
    const total = d.complexidade.reduce((s, n) => s + n.valor, 0);
    $('cx-desc').textContent = `Classificação dos ${fmt(total)} pacientes ativos em terapia pela quantidade de terapias diferentes ` +
      `(Fisio, Fono, TO, Nutri, Psico) que receberam nos últimos ${d.janelas.terapia} dias até a data final. Clique num nível para ver os pacientes.`;
    $('niveis').innerHTML = d.complexidade.map((n, i) => `<button type="button" class="nv" style="--c:${C.nivel[i]}" data-det="complexidade" data-valor="${esc(n.rotulo)}">` +
      `<div class="n-cab"><h3><i></i>${esc(n.rotulo)}</h3><span class="n-faixa">${esc(n.faixa)}</span></div>` +
      `<div class="n-val">${fmt(n.valor)}<small>${fmtPct(n.pct)}</small></div><div class="trilho"><i style="width:${n.pct}%"></i></div></button>`).join('');
    const siglas = d.terapias.map(t => t.sigla);
    const linhas = d.complexidade.map(n => {
      const cel = siglas.map(s => { const v = d.complexidade_terapia[n.rotulo]?.[s] || 0;
        return `<td class="num">${v ? `<a href="#" data-det="complexidade_terapia" data-valor="${esc(n.rotulo + '|' + s)}">${fmt(v)}</a>` : '<span class="muted">0</span>'}</td>`; }).join('');
      return `<tr><td class="forte">${esc(n.rotulo)}</td>${cel}<td class="num"><a href="#" data-det="complexidade" data-valor="${esc(n.rotulo)}"><b>${fmt(n.valor)}</b></a></td></tr>`;
    }).join('');
    $('t-cx').innerHTML = `<thead><tr><th>Nível</th>${siglas.map(s => `<th class="num">${esc(s)}</th>`).join('')}<th class="num">Pacientes</th></tr></thead><tbody>${linhas}</tbody>`;
    $('t-cx').onclick = e => { if (e.target.closest('a')) e.preventDefault(); };
    listaBarras('l-cx-url', d.complexidade_informada, {det: 'complexidade_informada'});
  }

  // ------------------------------------------------------------ Movimentação e mortalidade
  function movimentacao() {
    const k = d.kpis;
    kpis('k-mov', [
      {tom: 'crit', icone: 'mortalidade', rotulo: 'Mortalidade no período', valor: fmtPct(k.mortalidade), det: 'obitos', destaque: true,
        sub: `<b>${fmt(k.obitos)}</b> óbito(s) ÷ ${fmt(k.atendidos)} pacientes atendidos`, info: 'Pacientes que foram a óbito no período ÷ pacientes atendidos no período × 100. Clique para ver quem foi a óbito.'},
      {tom: 'crit', icone: 'obito', rotulo: 'Óbitos', valor: fmt(k.obitos), det: 'obitos', sub: 'pacientes no período'},
      {tom: 'ok', icone: 'admissao', rotulo: 'Admissões', valor: fmt(k.admissoes), det: 'admissoes', sub: 'atendimentos no período'},
      {tom: 'acc', icone: 'alta', rotulo: 'Altas', valor: fmt(k.altas), det: 'altas', sub: 'atendimentos, sem contar óbitos'},
    ]);
    const dm = d.dma;
    const linhas = [['Admissões', 'admissoes', 'dma_admissoes', fmt], ['Altas (sem óbitos)', 'altas', 'dma_altas', fmt],
      ['Óbitos', 'obitos', 'dma_obitos', fmt], ['Mortalidade', 'mortalidade', 'dma_obitos', fmtPct]];
    $('t-dma').innerHTML = linhas.map(([nome, campo, tipo, f]) => `<tr><td>${nome}</td>` +
      ['dia', 'mes', 'ano'].map(e => `<td class="num"><a href="#" data-det="${tipo}" data-valor="${e}"><b>${f(dm[e][campo])}</b></a></td>`).join('') + '</tr>').join('');
    $('t-dma').onclick = e => { if (e.target.closest('a')) e.preventDefault(); };
    $('dma-nota').textContent = `Dia ${dm.dia.rotulo} · Mês ${dm.mes.rotulo} · Ano ${dm.ano.rotulo}`;
    motivos();
    G.linha('c-mort', d.meses.map(nomeMes), d.mortalidade_mes, {rotulo: 'Mortalidade', sufixo: '%', cor: C.crit,
      aoClicar: i => det.abrir('mes_obitos', d.meses[i])});
    $('obitos-nota').textContent = `${fmt(d.obitos_lista.linhas.length)} no período`;
    tObitos.dados(d.obitos_lista.colunas, d.obitos_lista.linhas);
  }
  function motivos() {
    document.querySelectorAll('#mot-esc button').forEach(b => b.classList.toggle('on', b.dataset.esc === escMotivo));
    listaBarras('l-motivos', d.motivos[escMotivo], {det: 'motivo', valorDet: i => `${escMotivo}|${i.rotulo}`,
      cor: i => /bito/i.test(i.rotulo) ? 'var(--crit)' : 'var(--acc)', vazio: 'Nenhuma alta neste intervalo.'});
  }
  $('mot-esc').onclick = e => { const b = e.target.closest('button'); if (b && d) { escMotivo = b.dataset.esc; motivos(); } };

  // ------------------------------------------------------------ Perfil
  function perfil() {
    const total = d.kpis.pacientes_ativos;
    listaBarras('l-oper', d.operadoras, {det: 'operadora', total});
    listaBarras('l-serv', d.servicos, {det: 'servico', total});
    listaBarras('l-diag', d.diagnosticos, {det: 'diagnostico', total});
    listaBarras('l-cid', d.cidades, {det: 'cidade', total});
    $('idade-nota').textContent = `idade média ${d.kpis.idade_media.toLocaleString('pt-BR')} anos`;
    G.colunas('c-idade', d.faixas_etarias.map(f => f.rotulo), [{rotulo: 'Pacientes', dados: d.faixas_etarias.map(f => f.valor), cor: C.acc}],
      {rotulosValor: true, aoClicar: i => det.abrir('idade', d.faixas_etarias[i].rotulo)});
  }

  // ------------------------------------------------------------ Mapa por bairro
  const METRICAS = {
    ativos: {nome: 'Pacientes ativos', un: 'paciente(s) ativo(s)', rampa: 'azul', porTerapia: false,
      desc: 'Pacientes ativos na data final, pelo bairro do atendimento mais recente.'},
    em_terapia: {nome: 'Pacientes em terapia', un: 'paciente(s) em terapia', rampa: 'azul', porTerapia: true,
      desc: 'Pacientes ativos com visita da terapia nos últimos 90 dias.'},
    pendentes: {nome: 'Pacientes com terapia pendente', un: 'paciente(s) com pendência', rampa: 'laranja', porTerapia: true,
      desc: 'Pacientes ativos sem visita há mais de 5 dias numa terapia em andamento (ou indicados com terapias e sem nenhuma visita em 90 dias).'},
    visitas: {nome: 'Visitas no período', un: 'visita(s) no período', rampa: 'azul', porTerapia: true,
      desc: 'Visitas registradas no período em atendimentos do bairro.'},
    profissionais: {nome: 'Profissionais que atenderam', un: 'profissional(is) no período', rampa: 'azul', porTerapia: true,
      desc: 'Profissionais diferentes com ao menos uma visita no bairro durante o período: a cobertura observada.'},
    cobertura: {nome: 'Profissionais que cobrem', un: 'profissional(is) que cobrem o bairro', rampa: 'azul', porTerapia: true,
      desc: 'Profissionais que atenderam alguém no bairro nos últimos 180 dias, mesmo sem visita no período: quem cobre a região. Contorno laranja = bairro com pacientes e sem visita no período, mas com alguém que cobre; vermelho = ninguém em 180 dias.'},
    altas: {nome: 'Altas no período', un: 'alta(s) no período', rampa: 'azul', porTerapia: false,
      desc: 'Atendimentos que receberam alta no período (sem contar óbitos), pelo bairro do atendimento.'},
    relatorios: {nome: 'Relatórios pendentes', un: 'relatório(s) pendente(s)', rampa: 'laranja', porTerapia: true,
      desc: 'Relatórios pendentes da lista atual da URL, pelo bairro do atendimento.'},
  };
  let metrica = 'ativos', terapiaMapa = '*', bairroFixo = null;
  const valorMapa = (b, m = metrica) => (d.mapa[b]?.[m]?.[METRICAS[m].porTerapia ? terapiaMapa : '*']) || 0;
  const nomeTer = t => t === '*' ? '' : t === 'SEM' ? ' · indicados sem nenhuma terapia' : ' · ' + (NOMES[t] || t);
  const mapaFor = MapaFortaleza.criar('mapa-svg', {
    legendaId: 'mapa-leg',
    rotuloValor: v => `${fmt(v)} ${METRICAS[metrica].un}`,
    aoPassar: chave => infoBairro(chave || bairroFixo),
    aoClicar: (chave, nome) => { bairroFixo = chave; infoBairro(chave); if (chave) FichaBairro.abrir(nome); },
  });

  function infoBairro(chave) {
    const el = $('mapa-info');
    if (!chave) {
      const soma = m => Object.keys(d.mapa).reduce((s, b) => s + valorMapa(b, m), 0);
      el.innerHTML = `<h3>Fortaleza</h3><span class="muted">${fmt(Object.keys(d.mapa).length)} bairros com pacientes${esc(nomeTer(terapiaMapa))}. ` +
        'Passe o mouse sobre um bairro ou clique para fixá-lo.</span><dl>' +
        ['ativos', 'em_terapia', 'pendentes', 'visitas', 'altas', 'relatorios'].map(m =>
          `<dt class="${m === metrica ? 'on' : ''}">${METRICAS[m].nome}</dt><dd>${fmt(soma(m))}</dd>`).join('') + '</dl>';
      return;
    }
    const nome = Object.keys(d.mapa).find(b => MapaFortaleza.norm(b) === chave) || chave;
    el.innerHTML = `<h3>${esc(nome)}</h3><span class="muted">${bairroFixo ? 'Bairro fixado · clique de novo no mapa para soltar' : 'Clique no bairro para abrir a ficha completa'}${esc(nomeTer(terapiaMapa))}</span><dl>` +
      Object.keys(METRICAS).map(m => {
        const v = valorMapa(nome, m), sig = METRICAS[m].porTerapia ? terapiaMapa : '*';
        return `<dt class="${m === metrica ? 'on' : ''}">${METRICAS[m].nome}</dt><dd>${v ? `<a href="#" data-det="mapa" data-valor="${esc(`${m}|${sig}|${nome}`)}">${fmt(v)}</a>` : '0'}</dd>`;
      }).join('') + `</dl><button type="button" class="btn primario sm" data-det="ficha" data-valor="${esc(nome)}">Abrir ficha do bairro →</button>`;
  }
  $('mapa-info').onclick = e => { if (e.target.closest('a')) e.preventDefault(); };

  async function mapaAba() {
    const opcoes = [...new Set(d.terapias.map(t => t.sigla))];
    const sel = $('mapa-terapia');
    if (sel.options.length === 1) sel.innerHTML += opcoes.map(t => `<option value="${t}">${esc(NOMES[t] || t)}</option>`).join('') +
      '<option value="SEM">Indicados sem nenhuma terapia (pendência)</option>';
    document.querySelectorAll('#mapa-metrica button').forEach(b => b.classList.toggle('on', b.dataset.m === metrica));
    const M = METRICAS[metrica];
    sel.disabled = !M.porTerapia;
    const dados = Object.fromEntries(Object.keys(d.mapa).map(b => [b, valorMapa(b)]));
    const total = Object.values(dados).reduce((s, v) => s + v, 0);
    $('mapa-desc').textContent = M.desc + (M.porTerapia && terapiaMapa !== '*' ? ` Filtro: ${nomeTer(terapiaMapa).slice(3)}.` : '');
    $('mapa-nota').textContent = metrica === 'profissionais' ? '' : `${fmt(total)} no total`;
    const zona = d.zonas_info[$('mapa-zona').value];
    // ao olhar profissionais: destaca bairros com pacientes e sem visita no período (laranja se alguém cobre, vermelho se ninguém)
    const alerta = new Set(), atencao = new Set();
    if (metrica === 'profissionais' || metrica === 'cobertura') {
      Object.entries(d.mapa).forEach(([b, m]) => {
        if (!m.ativos?.['*'] || m.profissionais?.['*']) return;
        (m.cobertura?.['*'] ? atencao : alerta).add(MapaFortaleza.norm(b));
      });
    }
    const fora = await mapaFor.desenhar(dados, {rampa: M.rampa, alerta, atencao, destaque: new Set(zona ? zona.bairros : [])});
    const f = d.mapa_fora;
    $('mapa-fora').textContent = [
      fora.length ? `Não encontrados entre os bairros oficiais de Fortaleza: ${fora.join(', ')}.` : '',
      f.outra_cidade ? `${fmt(f.outra_cidade)} paciente(s) ativo(s) de outras cidades.` : '',
      f.sem_bairro ? `${fmt(f.sem_bairro)} sem bairro informado pela URL.` : '',
    ].filter(Boolean).join(' ');
    $('mapa-rank-nota').textContent = M.nome.toLowerCase();
    const ranking = Object.entries(dados).filter(([, v]) => v).sort((a, b) => b[1] - a[1]).map(([rotulo, valor]) => ({rotulo, valor}));
    listaBarras('mapa-rank', ranking, {det: 'ficha',
      max: 15, cor: M.rampa === 'laranja' ? 'var(--s2)' : 'var(--acc)', vazio: 'Nenhum bairro com dados para este filtro.'});
    // zonas de atendimento: ranking pelo indicador atual e destaque dos bairros da zona escolhida
    const zsel = $('mapa-zona');
    if (zsel.options.length === 1) zsel.innerHTML += Object.entries(d.zonas_info).sort((a, b) => a[1].nome.localeCompare(b[1].nome, 'pt-BR', {numeric: true}))
      .map(([id, z]) => `<option value="${esc(id)}">${esc(z.nome)}</option>`).join('');
    const sig = M.porTerapia ? terapiaMapa : '*';
    const zonas = Object.entries(d.zonas).map(([id, m]) => ({id, rotulo: d.zonas_info[id]?.nome || id, valor: m[metrica]?.[sig] || 0}))
      .filter(z => z.valor).sort((a, b) => b.valor - a.valor);
    $('mapa-zonas-nota').textContent = `${fmt(Object.keys(d.zonas_info).length)} zonas · ${M.nome.toLowerCase()}`;
    listaBarras('mapa-zonas', zonas, {det: 'zona', valorDet: z => `${metrica}|${sig}|${z.id}`, max: 12,
      cor: M.rampa === 'laranja' ? 'var(--s2)' : 'var(--acc)', vazio: 'Nenhuma zona com dados para este filtro.'});
    infoBairro(bairroFixo);
  }
  $('mapa-metrica').onclick = e => { const b = e.target.closest('button'); if (b && d) { metrica = b.dataset.m; mapaAba(); } };
  $('mapa-terapia').onchange = e => { terapiaMapa = e.target.value; if (d) mapaAba(); };
  $('mapa-zona').onchange = () => { if (d) mapaAba(); };

  // ------------------------------------------------------------ Profissionais
  function profissionais() {
    tProf.dados(['Profissional', 'Terapia', 'Visitas', 'Pacientes', 'Dias com visita', 'Bairros'],
      d.profissionais.map(p => Object.assign([p.nome, p.terapia, p.visitas, p.pacientes, p.dias, p.bairros], {6: p.chave})));
    $('rel-nota').textContent = `${fmt(d.kpis.relatorios_pendentes)} no total`;
    listaBarras('l-rel', d.relatorios_terapia, {det: 'relatorios', rotulo: i => NOMES[i.rotulo] || i.rotulo, cor: i => corTerapia(i.rotulo)});
  }

  abas.inicial();
  carregar();
})();

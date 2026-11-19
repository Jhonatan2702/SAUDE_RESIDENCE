/* Painel operacional: cada aba busca só os seus dados, e de novo quando o período muda. */
(() => {
  const NOMES = {FISIO: 'Fisioterapia', FONO: 'Fonoaudiologia', TO: 'Terapia ocupacional', NUTRI: 'Nutrição', PSICO: 'Psicologia'};
  const carregadas = new Set();
  // listas abertas a partir dos números desta página (filtradas no navegador, com os dados já carregados)
  const local = {};
  const lista = (titulo, colunas, linhas, drill = {tipo: 'hist', col: 0}) => ({titulo, colunas, linhas, total: linhas.length, truncado: false, drill});
  const det = Detalhe((tipo, valor) => {
    const P = periodo.valor();
    if (tipo === 'ficha') { FichaBairro.abrir(valor); return null; }
    if (tipo === 'profissional') { Ficha.abrir('profissional', valor); return null; }  // resumo completo do profissional
    if (tipo === 'hist') { Ficha.abrir('paciente', valor); return null; }  // resumo completo do paciente
    const R = local.rel, F = local.fic;
    const col = {rel_ter: 3, rel_prof: 2, rel_comp: 5, fic_ter: 4, fic_prof: 3}[tipo];
    if (tipo.startsWith('rel_') && R) {
      const linhas = tipo === 'rel_todos' ? R.linhas : R.linhas.filter(l => l[col] === valor);
      return lista(`Relatórios pendentes${valor ? ' — ' + valor : ''}`, R.colunas, linhas);
    }
    if (tipo === 'rel_pacientes' && R) {
      const g = {};
      R.linhas.forEach(l => { (g[l[0]] ||= {n: 0, ters: new Set(), comp: l[5]}); g[l[0]].n++; g[l[0]].ters.add(l[3]); });
      return lista('Pacientes com relatórios pendentes', ['Paciente', 'Relatórios', 'Terapias', 'Competência mais antiga'],
        Object.entries(g).sort((a, b) => b[1].n - a[1].n).map(([p, x]) => [p, x.n, [...x.ters].join(' · '), x.comp]));
    }
    if (tipo.startsWith('fic_') && F) {
      if (tipo === 'fic_resumo') {
        const g = {};
        F.linhas.forEach(l => { (g[l[3]] ||= {n: 0, pac: new Set(), ters: new Set()}); g[l[3]].n++; g[l[3]].pac.add(l[1]); g[l[3]].ters.add(l[4]); });
        return lista('Fichas por profissional', ['Profissional', 'Fichas', 'Pacientes', 'Terapias'],
          Object.entries(g).sort((a, b) => b[1].n - a[1].n).map(([p, x]) => [p, x.n, x.pac.size, [...x.ters].join(' · ')]), {tipo: 'profissional', col: 0});
      }
      if (tipo === 'fic_pacientes') {
        const g = {};
        F.linhas.forEach(l => { (g[l[1]] ||= {n: 0, profs: new Set(), ult: l[0]}); g[l[1]].n++; g[l[1]].profs.add(l[3]); });
        return lista('Pacientes atendidos no período', ['Paciente', 'Fichas', 'Profissionais', 'Última ficha'],
          Object.entries(g).sort((a, b) => b[1].n - a[1].n).map(([p, x]) => [p, x.n, [...x.profs].join('; '), x.ult]));
      }
      const linhas = tipo === 'fic_todos' ? F.linhas : F.linhas.filter(l => l[col] === valor);
      return lista(`Fichas realizadas${valor ? ' — ' + valor : ''}`, F.colunas, linhas, {tipo: 'hist', col: 1});
    }
    return Promise.reject(new Error('Detalhamento indisponível.'));
  });
  const abas = window.ABAS = Abas(nome => carregar(nome));
  const periodo = Periodo(() => { carregadas.clear(); carregar(abas.atual()); });
  FichaBairro.configurar(() => periodo.valor());
  const qs = () => { const P = periodo.valor(); return `ini=${P.ini}&fim=${P.fim}`; };
  const contador = (aba, n) => { const el = $('cont-' + aba); el.hidden = false; el.textContent = fmt(n); };
  const filtroSelect = (sel, col) => l => !$(sel).value || l[col] === $(sel).value;
  const opcoesTerapia = (sel, itens) => {
    const atual = $(sel).value;
    $(sel).innerHTML = '<option value="">Todas as terapias</option>' + itens.map(i => `<option value="${esc(i.rotulo)}">${esc(i.nome)} (${fmt(i.valor)})</option>`).join('');
    $(sel).value = itens.some(i => i.rotulo === atual) ? atual : '';
  };

  // ------------------------------------------------------------ tabelas
  const tRel = Tabela('t-rel', {busca: 'rel-busca', contador: 'rel-n', filtro: filtroSelect('rel-ter', 3), aoClicar: l => det.abrir('hist', l[0])});
  const tProf = Tabela('t-prof', {busca: 'prof-busca', contador: 'prof-n', numericas: [2, 3, 4, 5], aoClicar: l => det.abrir('profissional', l[6])});
  const tAbrSem = Tabela('t-abr-sem', {numericas: [1], aoClicar: l => FichaBairro.abrir(l[0]),
    vazio: 'Todos os bairros com pacientes indicados tiveram visita no período.'});
  const tAbr = Tabela('t-abr', {busca: 'abr-busca', contador: 'abr-n', numericas: [5, 6], aoClicar: l => FichaBairro.abrir(l[3])});
  let zonaSel = null;
  const tZonas = Tabela('t-zonas', {numericas: [1, 2, 3, 4, 5], vazio: 'A URL ainda não enviou zonas.',
    aoClicar: l => { zonaSel = zonaSel === l[6] ? null : l[6]; $('abr-busca').value = zonaSel ? l[0] : ''; desenharMapaAbr(false); }});
  const tFic = Tabela('t-fic', {busca: 'fic-busca', contador: 'fic-n', filtro: filtroSelect('fic-ter', 4), aoClicar: l => det.abrir('hist', l[1])});
  $('rel-ter').onchange = () => tRel.redesenhar();
  $('fic-ter').onchange = () => tFic.redesenhar();

  async function carregar(aba) {
    if (!aba || carregadas.has(aba)) return;
    carregadas.add(aba);
    $('sub-periodo').textContent = aba === 'relatorios' || aba === 'precos'
      ? 'Lista atual enviada pela URL Saúde Residence'
      : 'Período: ' + periodo.rotulo() + ' · dados da URL Saúde Residence';
    try {
      if (aba === 'relatorios') relatorios(await api('/api/operacional/relatorios'));
      else if (aba === 'profissional') profissionais(await api('/api/operacional/profissionais?' + qs()));
      else if (aba === 'abrangencia') abrangencia(await api('/api/operacional/abrangencia?' + qs()));
      else if (aba === 'fichas') fichas(await api('/api/operacional/fichas?' + qs()));
    } catch (e) { carregadas.delete(aba); toast(e.message, true); }
  }

  function relatorios(r) {
    local.rel = r;
    contador('relatorios', r.total);
    kpis('k-rel', [
      {tom: 'warn', icone: 'relatorios', rotulo: 'Relatórios pendentes', valor: fmt(r.total), sub: 'na lista atual da URL', det: 'rel_todos'},
      {tom: 'neutro', icone: 'pacientes', rotulo: 'Pacientes', valor: fmt(r.pacientes), sub: 'com ao menos um relatório pendente', det: 'rel_pacientes'},
      {tom: 'neutro', icone: 'profissional', rotulo: 'Profissionais', valor: fmt(r.profissionais), sub: 'com relatórios a entregar', det: 'rel_todos'},
      {tom: 'crit', icone: 'calendario', rotulo: 'Competência mais antiga', valor: r.mais_antiga, sub: 'relatório pendente há mais tempo',
        det: 'rel_comp', valorDet: r.mais_antiga},
    ]);
    listaBarras('l-rel-ter', r.por_terapia, {rotulo: i => i.nome, cor: i => corTerapia(i.rotulo), total: r.total, det: 'rel_ter'});
    listaBarras('l-rel-prof', r.por_profissional, {total: r.total, det: 'rel_prof'});
    listaBarras('l-rel-comp', r.por_competencia, {max: 12, det: 'rel_comp'});  // mais antigas primeiro: são as mais atrasadas
    opcoesTerapia('rel-ter', r.por_terapia);
    tRel.dados(r.colunas, r.linhas);
  }

  function profissionais(r) {
    contador('profissional', r.profissionais.length);
    $('prof-nota').textContent = `${fmt(r.profissionais.length)} profissionais · ${fmt(r.visitas)} visitas`;
    // a 7ª coluna (oculta no cabeçalho) guarda a chave do profissional para o clique
    tProf.dados(['Profissional', 'Terapia', 'Visitas', 'Pacientes', 'Dias com visita', 'Bairros'],
      r.profissionais.map(p => Object.assign([p.nome, p.terapia, p.visitas, p.pacientes, p.dias, p.bairros], {6: p.chave})));
  }

  // mapa de cobertura: todos os profissionais (quantos atendem cada bairro) ou a região de um profissional
  let abr = null;
  const mapaAbr = MapaFortaleza.criar('abr-mapa', {
    legendaId: 'abr-leg',
    rotuloValor: v => $('abr-prof').value ? `${fmt(v)} paciente(s) deste profissional` : `${fmt(v)} profissional(is) no período`,
    aoClicar: (chave, nome) => {
      $('abr-busca').value = chave ? (nome || '') : $('abr-prof').value; tAbr.redesenhar();
      if (chave) FichaBairro.abrir(nome);
    },
  });
  function desenharMapaAbr(sincronizarBusca = true) {
    const prof = $('abr-prof').value, dados = {};
    abr.linhas.filter(l => !prof || l[0] === prof).forEach(l => { dados[l[3]] = (dados[l[3]] || 0) + (prof ? l[5] : 1); });
    const zona = abr.zonas.find(z => z.id === zonaSel);
    // sem profissional: vermelho; descoberto no período mas com alguém que cobre: laranja
    const alerta = prof ? new Set() : new Set(abr.sem_cobertura.filter(b => !b.cobrem.length).map(b => MapaFortaleza.norm(b.bairro)));
    const atencao = prof ? new Set() : new Set(abr.sem_cobertura.filter(b => b.cobrem.length).map(b => MapaFortaleza.norm(b.bairro)));
    // profissional escolhido: contorna a região que ele cobre (últimos 180 dias), além de pintar onde atendeu no período
    const regiao = prof ? new Set((abr.regiao_prof[prof] || []).map(MapaFortaleza.norm)) : null;
    const semNinguem = abr.sem_cobertura.filter(b => !b.cobrem.length).length;
    $('abr-mapa-nota').textContent = prof
      ? `${fmt(Object.keys(dados).length)} bairro(s) no período · cobre ${fmt(regiao.size)} em ${abr.janela_cobertura} dias`
      : `${fmt(abr.sem_cobertura.length)} descoberto(s) no período · ${fmt(semNinguem)} sem ninguém`;
    mapaAbr.selecionar(null);
    mapaAbr.desenhar(dados, {alerta, atencao, destaque: regiao || new Set(zona ? zona.bairros : []),
      rotuloDestaque: regiao ? `região que cobre (${abr.janela_cobertura} dias)` : 'bairros da zona'});
    if (sincronizarBusca) $('abr-busca').value = prof;
    tAbr.redesenhar();
  }
  $('abr-prof').onchange = () => abr && desenharMapaAbr();
  ['l-abr-bairros'].forEach(id => $(id).addEventListener('click', e => {
    const lb = e.target.closest('.lb');
    if (lb) FichaBairro.abrir(lb.title);
  }));

  function abrangencia(r) {
    abr = r;
    contador('abrangencia', r.bairros.length);
    kpis('k-abr', [
      {tom: 'acc', icone: 'profissional', rotulo: 'Profissionais', valor: fmt(r.profissionais), sub: 'com visitas no período'},
      {tom: 'acc', icone: 'bairro', rotulo: 'Bairros atendidos', valor: fmt(r.bairros.length), sub: 'com ao menos uma visita'},
      {tom: 'warn', icone: 'aviso', rotulo: 'Bairros com 1 profissional', valor: fmt(r.bairros.filter(b => b.profissionais === 1).length),
        sub: 'cobertura dependente de uma pessoa', info: 'Bairros onde só um profissional atendeu no período: se ele faltar, o bairro fica descoberto.'},
      {tom: 'crit', icone: 'aviso', rotulo: 'Bairros descobertos no período', valor: fmt(r.sem_cobertura.length),
        sub: `<b>${fmt(r.sem_cobertura.filter(b => !b.cobrem.length).length)}</b> sem nenhum profissional em ${r.janela_cobertura} dias`,
        info: `Bairros de Fortaleza com pacientes ativos indicados com terapias e nenhuma visita no período. Os demais têm profissional que cobre a região (atendeu lá nos últimos ${r.janela_cobertura} dias).`},
      {tom: 'crit', icone: 'aviso', rotulo: 'Zonas descobertas no período', valor: fmt(r.zonas.filter(z => z.indicados && !z.profissionais).length),
        sub: `<b>${fmt(r.zonas.filter(z => z.indicados && !z.cobrem).length)}</b> sem nenhum profissional em ${r.janela_cobertura} dias`,
        info: `Zonas com pacientes ativos indicados com terapias e nenhuma visita no período. As demais têm profissional que atendeu na zona nos últimos ${r.janela_cobertura} dias.`},
    ]);
    zonaSel = null;
    $('zonas-nota').textContent = `${fmt(r.zonas.length)} zonas`;
    // 6ª coluna (oculta) guarda o id da zona para o clique; zonas sem cobertura primeiro
    tZonas.dados(['Zona', 'Bairros', 'Indicados', 'Profissionais', `Cobrem (${r.janela_cobertura} d)`, 'Visitas'],
      [...r.zonas].sort((a, b) => (!!a.profissionais - !!b.profissionais) || b.indicados - a.indicados)
        .map(z => Object.assign([z.nome, z.bairros.length, z.indicados, z.profissionais, z.cobrem, z.visitas], {6: z.id})));
    const atual = $('abr-prof').value;
    const nomes = [...new Set(r.linhas.map(l => l[0]))].sort((a, b) => a.localeCompare(b, 'pt-BR'));
    $('abr-prof').innerHTML = '<option value="">Todos os profissionais (cobertura)</option>' + nomes.map(n => `<option>${esc(n)}</option>`).join('');
    $('abr-prof').value = nomes.includes(atual) ? atual : '';
    $('abr-sem-nota').textContent = `${fmt(r.sem_cobertura.length)} bairro(s)`;
    tAbrSem.dados(['Bairro', 'Pacientes', 'Coberto por'], r.sem_cobertura.map(b => [b.bairro, b.pacientes,
      b.cobrem.length ? b.cobrem.slice(0, 3).map(x => `${x.nome} (${x.ultima})`).join('; ') + (b.cobrem.length > 3 ? ` +${b.cobrem.length - 3}` : '')
        : `Ninguém nos últimos ${r.janela_cobertura} dias`]));
    listaBarras('l-abr-bairros', r.bairros.map(b => ({rotulo: b.bairro, valor: b.profissionais})), {max: 15});
    tAbr.dados(r.colunas, r.linhas);
    desenharMapaAbr();
  }

  function fichas(r) {
    local.fic = r;
    contador('fichas', r.total);
    kpis('k-fichas', [
      {tom: 'ok', icone: 'prontuario', rotulo: 'Fichas realizadas', valor: fmt(r.total), sub: 'visitas registradas no App', det: 'fic_todos'},
      {tom: 'neutro', icone: 'pacientes', rotulo: 'Pacientes atendidos', valor: fmt(r.pacientes), sub: 'no período', det: 'fic_pacientes'},
      {tom: 'neutro', icone: 'profissional', rotulo: 'Profissionais', valor: fmt(r.profissionais), sub: 'que registraram fichas', det: 'fic_resumo'},
      ...r.por_terapia.slice(0, 5).map(t => ({tom: 'acc', icone: 'terapias', rotulo: t.nome, valor: fmt(t.valor), sub: 'fichas no período',
        det: 'fic_ter', valorDet: t.rotulo})),
    ]);
    opcoesTerapia('fic-ter', r.por_terapia);
    tFic.dados(r.colunas, r.linhas);
    if (r.truncado) toast('Período muito longo: exibindo as 10.000 fichas mais recentes.');
  }

  abas.inicial();
})();

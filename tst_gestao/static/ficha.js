/* Ficha do bairro: abre ao clicar num bairro (mapa, rankings, tabelas de abrangência).
   Mostra resumo, profissionais, pacientes, terapias, relatórios e operadoras do bairro, e permite descer
   bairro → profissional → paciente → histórico de visitas, com "Voltar". */
const FichaBairro = (() => {
  let periodo = () => ({ini: '', fim: ''}), dados = null, pilha = [], pronto = false;
  let tProf, tPac, tRel, tSub, abaAtual = 'profissionais';
  const qs = extra => new URLSearchParams({...periodo(), ...extra});

  function preparar() {
    if (pronto) return;
    pronto = true;
    tProf = Tabela('fb-t-prof', {busca: 'fb-prof-busca', contador: 'fb-prof-n', numericas: [2, 3],
      aoClicar: l => profissional(l[5], l[0]), vazio: 'Nenhum profissional com visita neste bairro no período.'});
    tPac = Tabela('fb-t-pac', {busca: 'fb-pac-busca', contador: 'fb-pac-n', aoClicar: l => historico(l[0]),
      filtro: l => ({todos: true, terapia: l[3] !== '—', pendente: l[4] !== '—'})[$('fb-pac-filtro').value],
      vazio: 'Nenhum paciente ativo neste bairro.'});
    tRel = Tabela('fb-t-rel', {busca: 'fb-rel-busca', contador: 'fb-rel-n', aoClicar: l => historico(l[0]),
      vazio: 'Nenhum relatório pendente neste bairro.'});
    tSub = Tabela('fb-t-sub', {busca: 'fb-sub-busca', contador: 'fb-sub-n', aoClicar: l => tSub.aoClicar?.(l)});
    $('fb-pac-filtro').onchange = () => tPac.redesenhar();
    $('fb-abas').onclick = e => { const b = e.target.closest('[data-fa]'); if (b) aba(b.dataset.fa); };
    $('fb-kpis').onclick = e => {
      const k = e.target.closest('[data-fk]');
      if (!k) return;
      const [destino, filtro] = k.dataset.fk.split('|');
      if (filtro) { $('fb-pac-filtro').value = filtro; tPac.redesenhar(); }
      aba(destino);
    };
    $('fb-ter').onclick = e => {
      const tr = e.target.closest('[data-sig]');
      if (!tr) return;
      $('fb-pac-filtro').value = 'todos'; $('fb-pac-busca').value = tr.dataset.sig; tPac.redesenhar(); aba('pacientes');
    };
    $('fb-fechar').onclick = () => $('dlg-ficha').close();
    $('fb-voltar').onclick = voltar;
  }

  function aba(nome) {
    abaAtual = nome;
    document.querySelectorAll('#fb-abas [data-fa]').forEach(b => b.classList.toggle('on', b.dataset.fa === nome));
    document.querySelectorAll('#fb-principal [data-fp]').forEach(s => { s.hidden = s.dataset.fp !== nome; });
  }

  function mostrarPrincipal() {
    $('fb-principal').hidden = false; $('fb-sub').hidden = true;
    $('fb-trilha').textContent = 'Bairro';
    $('fb-t').textContent = dados.bairro;
  }

  async function abrir(bairro) {
    preparar();
    try {
      dados = await api('/api/bairro?' + qs({nome: bairro}));
    } catch (e) { return toast(e.message, true); }
    pilha = [];
    const r = dados.resumo, P = dados.periodo;
    mostrarPrincipal();
    $('fb-zonas').innerHTML = (dados.zonas.length ? '<span class="muted">Zonas:</span> ' + dados.zonas.map(z => `<span class="tag acc">${esc(z.nome)}</span>`).join(' ') : '') +
      ` <span class="muted">· período ${esc(fmtData(P.ini))} a ${esc(fmtData(P.fim))}</span>` +
      (dados.oficial ? '' : ' <span class="tag warn">fora dos bairros oficiais de Fortaleza</span>');
    const k = (rot, val, fk, tom, sub = '') => `<button type="button" class="fb-k tom-${tom}" data-fk="${fk}"><span>${rot}</span><b>${fmt(val)}</b>${sub ? `<small>${sub}</small>` : ''}</button>`;
    $('fb-kpis').innerHTML = k('Pacientes ativos', r.ativos, 'pacientes|todos', 'acc') +
      k('Em terapia', r.em_terapia, 'pacientes|terapia', 'acc', 'últimos 90 dias') +
      k('Com pendência', r.pendentes, 'pacientes|pendente', 'warn', r.sem_terapia ? `${fmt(r.sem_terapia)} sem nenhuma terapia` : '') +
      k('Profissionais', r.profissionais, 'profissionais', 'acc', 'com visita no período') +
      k('Visitas', r.visitas, 'profissionais', 'neutro', 'no período') +
      k('Relatórios pendentes', r.relatorios, 'relatorios', 'warn');
    $('fb-pac-filtro').value = 'todos';
    ['fb-prof-busca', 'fb-pac-busca', 'fb-rel-busca'].forEach(id => { $(id).value = ''; });
    tProf.dados(dados.profissionais.colunas, dados.profissionais.linhas);
    tPac.dados(dados.pacientes.colunas, dados.pacientes.linhas);
    tRel.dados(dados.relatorios.colunas, dados.relatorios.linhas);
    $('fb-ter').innerHTML = '<thead><tr><th>Terapia</th><th class="num">Pacientes</th><th class="num">Pendentes</th><th class="num">Visitas no período</th><th class="num">Profissionais</th></tr></thead><tbody>' +
      (dados.terapias.map(t => `<tr class="clicavel" data-sig="${esc(t.sigla)}" title="Ver os pacientes de ${esc(t.nome)}"><td><span class="fb-sig" style="--c:${corTerapia(t.sigla)}"></span>${esc(t.nome)}</td>` +
        `<td class="num">${fmt(t.pacientes)}</td><td class="num">${fmt(t.pendentes)}</td><td class="num">${fmt(t.visitas)}</td><td class="num">${fmt(t.profissionais)}</td></tr>`).join('') ||
       '<tr><td colspan="5" class="muted">Nenhuma terapia neste bairro.</td></tr>') + '</tbody>';
    listaBarras('fb-l-oper', dados.operadoras, {total: r.ativos, vazio: 'Nenhum paciente ativo.'});
    // abre na aba que tem conteúdo
    aba(r.profissionais ? 'profissionais' : r.ativos ? 'pacientes' : 'relatorios');
    const dlg = $('dlg-ficha');
    if (!dlg.open) dlg.showModal();
  }

  async function sub(titulo, trilha, carregar, aoClicar) {
    try {
      const r = await carregar();
      pilha.push({titulo, trilha, carregar, aoClicar});
      $('fb-principal').hidden = true; $('fb-sub').hidden = false;
      $('fb-trilha').textContent = trilha; $('fb-t').textContent = titulo;
      $('fb-sub-busca').value = '';
      tSub.aoClicar = aoClicar;
      tSub.dados(r.colunas, r.linhas);
    } catch (e) { toast(e.message, true); }
  }
  const profissional = (chave, nome) => sub(nome, `Bairro ${dados.bairro} › Profissional`,
    () => api('/api/operacional/profissional?' + qs({chave})), l => historico(l[0]));
  const historico = nome => sub(nome, `Bairro ${dados.bairro} › Paciente › Histórico de visitas`,
    () => api('/api/historico?' + new URLSearchParams({paciente: nome})), null);

  function voltar() {
    pilha.pop();
    const ant = pilha.pop();
    if (ant) sub(ant.titulo, ant.trilha, ant.carregar, ant.aoClicar);
    else { mostrarPrincipal(); aba(abaAtual); }
  }

  // link direto: /painel?bairro=Meireles#mapa abre a ficha do bairro ao carregar a página
  addEventListener('load', () => {
    const b = new URLSearchParams(location.search).get('bairro');
    if (b) setTimeout(() => abrir(b), 600);
  });

  return {configurar: fn => { periodo = fn; }, abrir};
})();

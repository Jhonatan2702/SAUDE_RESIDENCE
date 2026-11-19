(() => {
  const dataHora = s => s ? fmtData(s) + ' ' + s.slice(11, 16) : '—';

  async function status() {
    const s = await api('/api/integracao/status');
    if (!s) { kpis('k-sync', [{tom: 'neutro', icone: 'integracoes', rotulo: 'Sincronização', valor: 'Pendente', sub: 'ainda não executada'}]); return; }
    const ok = s.status !== 'erro';
    kpis('k-sync', [
      {tom: ok ? 'ok' : 'crit', icone: ok ? 'integracoes' : 'aviso', rotulo: 'Última execução', valor: ok ? (s.status === 'parcial' ? 'Parcial' : 'Sucesso') : 'Falhou',
        sub: `${dataHora(s.ultima_execucao)}${s.erro ? ' · ' + esc(s.erro) : ''}`},
      {tom: 'acc', icone: 'calendario', rotulo: 'Última atualização com sucesso', valor: s.ultima_sucesso ? s.ultima_sucesso.slice(11, 16) : '—',
        sub: s.ultima_sucesso ? fmtData(s.ultima_sucesso) + ` · repete a cada ${s.intervalo_min} min` : 'nenhuma'},
      {tom: 'neutro', icone: 'pacientes', rotulo: 'Atendimentos no espelho', valor: fmt(s.atendimentos),
        sub: `<b>${fmt(s.atendimentos_criados)}</b> novos · ${fmt(s.atendimentos_atualizados)} atualizados na última vez`},
      {tom: 'neutro', icone: 'evolucao', rotulo: 'Visitas no espelho', valor: fmt(s.visitas),
        sub: `<b>${fmt(s.visitas_criadas)}</b> novas · ${fmt(s.visitas_atualizadas)} atualizadas na última vez`},
    ]);
  }

  let conhecidos = null;
  async function monitor(avisar = false) {
    const d = await api('/api/integracao/monitor');
    $('mon-resumo').textContent = d.ultima_verificacao
      ? `${d.campos_monitorados} campos · ${d.alertas_pendentes} alerta(s) pendente(s)` : 'Aguardando a primeira sincronização';
    const ids = new Set(d.alertas.map(a => a.id));
    if (avisar && conhecidos) {
      const novos = d.alertas.filter(a => !conhecidos.has(a.id) && !a.reconhecido_em);
      if (novos.length) toast(`A URL apresentou ${novos.length} alteração(ões) nova(s).`, true);
    }
    conhecidos = ids;
    $('t-alertas').innerHTML = '<thead><tr><th>Detectado</th><th>Campo</th><th>Alteração</th><th></th></tr></thead><tbody>' +
      (d.alertas.map(a => `<tr><td>${esc(dataHora(a.criado_em))}</td><td><code>${esc(a.campo)}</code></td><td>${esc(a.detalhe)}</td>` +
        `<td>${a.reconhecido_em ? '<span class="tag">Visto</span>' : `<button class="btn sm" data-alerta="${a.id}">Marcar como visto</button>`}</td></tr>`).join('') ||
       '<tr><td colspan="4" class="muted">Nenhuma alteração detectada.</td></tr>') + '</tbody>';
  }
  $('t-alertas').onclick = async e => {
    const b = e.target.closest('[data-alerta]');
    if (!b) return;
    try { await api(`/api/integracao/alertas/${b.dataset.alerta}/reconhecer`, 'POST'); monitor(); } catch (err) { toast(err.message, true); }
  };

  $('sync').onclick = async () => {
    const b = $('sync'); b.disabled = true; b.lastChild.textContent = 'Sincronizando…';
    try {
      const r = await api('/api/integracao/sincronizar', 'POST');
      toast(r.erro || (r.alertas_esquema ? `${r.alertas_esquema} alteração(ões) na URL detectada(s).` : 'Sincronização concluída.'), Boolean(r.erro || r.alertas_esquema));
    } catch (err) { toast(err.message, true); }
    finally { b.disabled = false; b.lastChild.textContent = 'Sincronizar agora'; status(); monitor(); }
  };

  status().catch(err => toast(err.message, true));
  monitor().catch(err => { $('mon-resumo').textContent = err.message; });
  setInterval(() => { status().catch(() => {}); monitor(true).catch(() => {}); }, 60000);
})();

/* Atualizações do sistema: buscar, ver novidades e atualizar (sempre com confirmação). */
(() => {
  const dataHora = s => s ? fmtData(s) + ' às ' + s.slice(11, 16) : 'nunca';
  function desenhar(e) {
    const linhas = [`Versão instalada: <b>${esc(e.versao_atual)}</b> · última consulta: ${esc(dataHora(e.verificado_em))}`];
    if (e.erro) linhas.push(`<span class="tag warn">${esc(e.erro)}</span>`);
    else if (e.verificado_em && !e.disponivel) linhas.push('<span class="tag ok">Você está na versão mais recente.</span>');
    if (!e.executavel) linhas.push('<span class="tag">Rodando pelo código-fonte: a instalação automática só funciona no executável (TST-GESTAO.exe).</span>');
    $('atu-estado').innerHTML = linhas.join('<br>');
    const box = $('atu-nova'), n = e.disponivel;
    box.hidden = !n;
    if (!n) return;
    box.innerHTML = `<div class="versao-nova"><h3>Nova versão ${esc(n.versao)} disponível</h3>` +
      `<span class="muted">Publicada em ${esc(dataHora(n.publicado_em || ''))} · ${fmt(Math.round(n.tamanho / 1048576))} MB · assinatura digital conferida ✓</span>` +
      `<pre>${esc(n.notas || 'Sem notas de versão.')}</pre>` +
      `<button type="button" class="btn primario" id="atu-aplicar"${e.executavel ? '' : ' disabled'}>Atualizar agora</button>` +
      `<div class="confirmar" id="atu-confirmar" hidden><span>O sistema vai <b>reiniciar por alguns segundos</b>: quem estiver usando verá a página recarregar. Os dados são mantidos e a versão atual fica guardada. Confirmar?</span>` +
      `<button type="button" class="btn primario sm" id="atu-sim">Sim, atualizar</button><button type="button" class="btn sm" id="atu-nao">Cancelar</button></div></div>`;
    $('atu-aplicar').onclick = () => { $('atu-confirmar').hidden = false; $('atu-aplicar').hidden = true; };
    $('atu-nao').onclick = () => { $('atu-confirmar').hidden = true; $('atu-aplicar').hidden = false; };
    $('atu-sim').onclick = aplicar;
  }
  async function aplicar() {
    $('atu-confirmar').innerHTML = '<span>Baixando e conferindo a atualização… não feche esta janela.</span>';
    try {
      const r = await api('/api/atualizacao/aplicar', 'POST');
      $('atu-confirmar').innerHTML = `<span>Versão ${esc(r.versao)} instalada. Reiniciando o sistema…</span>`;
      aguardarRetorno();
    } catch (err) { toast(err.message, true); $('atu-confirmar').innerHTML = `<span>${esc(err.message)}</span>`; }
  }
  // espera a versão nova responder e recarrega a página
  function aguardarRetorno(tentativas = 0) {
    setTimeout(async () => {
      try { const r = await fetch('/login', {cache: 'no-store'}); if (r.ok && tentativas > 1) return location.reload(); } catch (e) { /* reiniciando */ }
      if (tentativas < 60) aguardarRetorno(tentativas + 1);
    }, 1500);
  }
  $('atu-verificar').onclick = async () => {
    const b = $('atu-verificar'); b.disabled = true; b.textContent = 'Consultando…';
    try { desenhar(await api('/api/atualizacao/verificar', 'POST')); } catch (err) { toast(err.message, true); }
    finally { b.disabled = false; b.textContent = 'Buscar atualizações'; }
  };
  // endereço fixo: só fica editável depois de "Alterar endereço"; "Cancelar" volta ao valor salvo
  const campoUrl = $('url-dados'), urlSalva = campoUrl.value;
  const editarUrl = sim => {
    campoUrl.readOnly = !sim;
    $('url-salvar').hidden = !sim;
    if ($('url-alterar')) $('url-alterar').hidden = sim;
    if ($('url-cancelar')) $('url-cancelar').hidden = !sim;
    if (sim) { campoUrl.focus(); campoUrl.select(); } else campoUrl.value = urlSalva;
  };
  if ($('url-alterar')) $('url-alterar').onclick = () => editarUrl(true);
  if ($('url-cancelar')) $('url-cancelar').onclick = () => editarUrl(false);
  $('f-url').onsubmit = async e => {
    e.preventDefault();
    try {
      await api('/api/integracao/url', 'POST', {url: campoUrl.value});
      toast('URL salva. Sincronizando…');
      $('sync').click();
      setTimeout(() => location.reload(), 1500);  // volta a mostrar o campo fixo com o novo endereço
    } catch (err) { toast(err.message, true); }
  };
  api('/api/atualizacao').then(desenhar).catch(err => { $('atu-estado').textContent = err.message; });
})();

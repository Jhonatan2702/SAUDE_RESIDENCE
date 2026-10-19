const $ = id => document.getElementById(id);
let estado = null;

function formCfg() {
  return {
    motor: $('b-motor').value, arquivo: $('b-arquivo').value, servidor: $('b-servidor').value, porta: $('b-porta').value,
    banco: $('b-banco').value, autenticacao: $('b-auth').value, driver: $('b-driver').value, servico: $('b-servico').value,
    dsn: $('b-dsn').value, usuario: $('b-usuario').value, senha: $('b-senha').value,
    criptografar: $('b-cript').checked, confiar_certificado: $('b-confiar').checked,
  };
}

function alternar() {
  const m = $('b-motor').value, win = m === 'sqlserver' && $('b-auth').value === 'windows';
  const mostra = (cls, on) => document.querySelectorAll('.' + cls).forEach(e => e.classList.toggle('hidden', !on));
  mostra('g-sqlite', m === 'sqlite');
  mostra('g-rede', m !== 'sqlite');
  mostra('g-ss', m === 'sqlserver');
  mostra('g-or', m === 'oracle');
  mostra('g-cred', m !== 'sqlite' && !win);
  const av = $('aviso-lib');
  const ok = m === 'sqlite' || (estado && estado.bibliotecas[m]);
  av.classList.toggle('hidden', ok);
  av.textContent = ok ? '' : 'Biblioteca do motor não instalada (pip install ' + (m === 'oracle' ? 'oracledb' : 'pyodbc') + ').';
  $('b-porta').placeholder = m === 'oracle' ? '1521' : '1433 (opcional)';
}

function resultado(msg, erro) {
  const r = $('resultado');
  r.classList.remove('hidden');
  r.style.background = erro ? '' : '#e8f7ee';
  r.style.color = erro ? '' : '#14532d';
  r.style.borderColor = erro ? '' : '#b7e4c7';
  r.innerHTML = msg;
}

function desenharAtual() {
  const a = estado.atual, c = estado.cfg;
  if (a.erro) { $('atual').innerHTML = '<b>' + esc(c.motor) + '</b> — erro: ' + esc(a.erro); return; }
  const linhas = Object.entries(a.tabelas).map(([t, n]) => '<tr><td>' + esc(t) + '</td><td style="text-align:right">' + n + '</td></tr>').join('');
  $('atual').innerHTML = '<p><b>' + esc(a.versao) + '</b>' + (c.servidor ? ' · ' + esc(c.servidor) : '') + (c.banco ? ' · ' + esc(c.banco) : '') + '</p>' +
    '<div class="table-wrap"><table><thead><tr><th>Tabela</th><th style="text-align:right">Registros</th></tr></thead><tbody>' + linhas + '</tbody></table></div>';
}

function preencher(c) {
  $('b-motor').value = c.motor || 'sqlite';
  for (const [id, k] of [['b-arquivo', 'arquivo'], ['b-servidor', 'servidor'], ['b-porta', 'porta'], ['b-banco', 'banco'], ['b-servico', 'servico'], ['b-dsn', 'dsn'], ['b-usuario', 'usuario']])
    $(id).value = c[k] || '';
  $('b-auth').value = c.autenticacao || 'windows';
  $('b-cript').checked = !!c.criptografar;
}

async function carregar() {
  estado = await api('/api/banco');
  $('b-driver').innerHTML = '<option value="">Automático</option>' + estado.drivers.map(d => '<option>' + esc(d) + '</option>').join('');
  preencher(estado.cfg);
  desenharAtual();
  alternar();
}

async function executar(botao, fn) {
  botao.disabled = true;
  try { await fn(); } catch (e) { resultado(esc(e.message), true); } finally { botao.disabled = false; }
}

function posAtivar(r) {
  if (r.relogin) { setTimeout(() => location.href = '/login', 2500); return ' Usuário não existe no novo banco: faça login novamente.'; }
  return '';
}

$('b-motor').onchange = $('b-auth').onchange = alternar;

$('bt-testar').onclick = () => executar($('bt-testar'), async () => {
  const r = await api('/api/banco/testar', 'POST', {cfg: formCfg(), criar_banco: $('b-criar').checked});
  resultado('✅ Conexão OK — ' + esc(r.versao || '') + (r.estrutura_ok ? ' · estrutura existente (' + r.registros + ' registros)' : ' · sem estrutura ainda'));
});

$('bt-ativar').onclick = () => executar($('bt-ativar'), async () => {
  if (!confirm('Passar a usar este banco agora? Os dados atuais não serão copiados.')) return;
  const r = await api('/api/banco/ativar', 'POST', {cfg: formCfg(), criar_banco: $('b-criar').checked});
  resultado('✅ Banco ativado.' + posAtivar(r));
  if (!r.relogin) carregar();
});

$('bt-migrar').onclick = () => executar($('bt-migrar'), async () => {
  if (!confirm('Criar a estrutura no destino e copiar todos os dados?' + ($('b-apagar').checked ? '\n\nATENÇÃO: os dados existentes no destino serão APAGADOS.' : ''))) return;
  const r = await api('/api/banco/migrar', 'POST', {cfg: formCfg(), criar_banco: $('b-criar').checked, apagar_destino: $('b-apagar').checked, ativar: $('b-ativar-fim').checked});
  resultado('✅ Migração concluída — ' + r.total + ' registros copiados' + (r.ativado ? ' e banco ativado.' : '.') + posAtivar(r));
  if (!r.relogin) carregar();
});

carregar().catch(e => toast(e.message, true));

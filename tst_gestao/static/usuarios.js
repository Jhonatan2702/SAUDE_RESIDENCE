(() => {
  const dlg = $('dlg'), frm = $('frm');
  let editId = null, usuarios = [];
  const rotulo = n => window.PERFIS[n]?.rotulo || n;

  async function carregar() {
    usuarios = await api('/api/usuarios');
    $('t-usuarios').innerHTML = '<thead><tr><th>Usuário</th><th>Nome</th><th>Perfil</th><th>Situação</th><th></th></tr></thead><tbody>' +
      usuarios.map(u => `<tr><td class="forte">${esc(u.usuario)}</td><td>${esc(u.nome)}</td>` +
        `<td><span class="tag ${u.nivel === 'admin' ? 'acc' : ''}">${esc(rotulo(u.nivel))}</span></td>` +
        `<td>${u.ativo ? '<span class="tag ok">Ativo</span>' : '<span class="tag">Inativo</span>'}</td>` +
        `<td class="num"><button class="btn sm" data-editar="${u.id}">Editar</button> <button class="btn sm perigo" data-excluir="${u.id}">Excluir</button></td></tr>`).join('') +
      '</tbody>';
  }
  $('t-usuarios').onclick = async e => {
    const ed = e.target.closest('[data-editar]'), ex = e.target.closest('[data-excluir]');
    if (ed) abrir(usuarios.find(u => u.id === +ed.dataset.editar));
    if (ex) {
      const u = usuarios.find(x => x.id === +ex.dataset.excluir);
      if (ex.dataset.confirmar !== '1') { ex.dataset.confirmar = '1'; ex.textContent = 'Confirmar exclusão'; return; }
      try { await api('/api/usuarios/' + u.id, 'DELETE'); toast(`Usuário ${u.usuario} excluído.`); carregar(); } catch (err) { toast(err.message, true); }
    }
  };
  function abrir(u) {
    editId = u ? u.id : null; frm.reset();
    $('dlg-t').textContent = u ? 'Editar usuário' : 'Novo usuário';
    $('dica').textContent = u ? '(deixe em branco para manter)' : '(mín. 6 caracteres; a troca é exigida no 1º acesso)';
    frm.elements.nivel.value = 'operacional';
    if (u) for (const k of ['usuario', 'nome', 'nivel', 'ativo']) frm.elements[k].value = u[k];
    $('dlg-erro').classList.add('hidden'); dlg.showModal();
  }
  $('novo').onclick = () => abrir(null);
  $('cancelar').onclick = () => dlg.close();
  frm.onsubmit = async e => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(frm)); d.ativo = +d.ativo;
    try { await api(editId ? '/api/usuarios/' + editId : '/api/usuarios', editId ? 'PUT' : 'POST', d); dlg.close(); toast('Usuário salvo.'); carregar(); }
    catch (err) { const a = $('dlg-erro'); a.textContent = err.message; a.classList.remove('hidden'); }
  };
  carregar().catch(err => toast(err.message, true));
})();

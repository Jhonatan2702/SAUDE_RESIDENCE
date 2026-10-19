(async () => {
  const ent = window.ENT, podeEditar = NIVEL >= 2, podeExcluir = NIVEL >= 3;
  const meta = await api('/api/meta/' + ent), opcoes = await api('/api/opcoes');
  const thead = document.querySelector('#tbl thead'), tbody = document.querySelector('#tbl tbody');
  const dlg = document.getElementById('dlg'), frm = document.getElementById('frm'), campos = document.getElementById('campos');
  const rotulo = Object.fromEntries(meta.campos.map(c => [c.nome, c]));
  let editId = null;

  const mesEl = document.getElementById('mes');
  if (meta.filtro_mes) { mesEl.classList.remove('hidden'); mesEl.value = new Date().toISOString().slice(0, 7); }

  function valoresDe(c) {
    const src = c.valores || opcoes[c.lista] || [];
    return src.map(v => typeof v === 'string' ? {valor: v, rotulo: v} : v);
  }

  // etiquetas coloridas por coluna (valor em minúsculas -> cor)
  const ETIQUETA = {
    situacao: {ativa: 'verde', realizada: 'verde', pendente: 'ambar', 'a confirmar': 'cinza', hospitalizado: 'roxo', 'não prorrogada': 'cinza',
      cancelada: 'red', 'óbito': 'red', suspensa: 'cinza', encerrada: 'navy'},
    complexidade: {'básico': '', 'intermediário': 'ambar', intensivo: 'red'},
    evento: {'admissão': 'verde', alta: '', 'óbito': 'navy', 'internação': 'ambar', retorno: 'agua'},
    agendado: {sim: 'verde', 'não': 'cinza'}, relatorio: {sim: 'verde', 'não': 'cinza'},
    terapia: {fisio: '', fono: 'roxo', nutri: 'verde', to: 'ambar', psico: 'agua'},
  };
  const nomePac = Object.fromEntries((opcoes['@pacientes'] || []).map(o => typeof o === 'string' ? [o, o] : [o.valor, o.rotulo]));
  const NUM = new Set(['int', 'money']);

  function celula(c, v) {
    if (v == null || v === '') return '<span class="muted">—</span>';
    if (c.tipo === 'date') return fmtData(v);
    if (c.tipo === 'month') return /^\d{4}-\d{2}$/.test(v) ? v.slice(5) + '/' + v.slice(0, 4) : esc(v);
    if (c.tipo === 'money') return 'R$ ' + Number(v).toLocaleString('pt-BR', {minimumFractionDigits: 2});
    const cores = ETIQUETA[c.nome];
    if (cores) { const k = String(v).toLowerCase(); return `<span class="tag ${k in cores ? cores[k] : 'cinza'}">${esc(v)}</span>`; }
    if (c.nome === 'codigo_paciente' && nomePac[v] && nomePac[v] !== v) return `<b>${esc(nomePac[v])}</b>`;
    return esc(v);
  }
  const classe = n => (n === 'codigo' ? 'cod' : n === 'nome' ? 'forte' : NUM.has(rotulo[n].tipo) ? 'r' : '');

  thead.innerHTML = '<tr>' + meta.colunas.map(n => `<th class="${NUM.has(rotulo[n].tipo) ? 'r' : ''}">${esc(rotulo[n].rotulo)}</th>`).join('') + '<th></th></tr>';

  async function carregar() {
    const p = new URLSearchParams({q: document.getElementById('q').value});
    if (mesEl.value) p.set('mes', mesEl.value);
    const rows = await api(`/api/${ent}?${p}`);
    tbody.innerHTML = '';
    document.getElementById('vazio').classList.toggle('hidden', rows.length > 0);
    document.getElementById('contador').textContent = rows.length.toLocaleString('pt-BR') + (rows.length === 1 ? ' registro' : ' registros');
    for (const r of rows) {
      const tr = document.createElement('tr');
      tr.innerHTML = meta.colunas.map(n => `<td class="${classe(n)}">${celula(rotulo[n], r[n])}</td>`).join('') + '<td class="r"></td>';
      const td = tr.lastChild;
      if (ent === 'pacientes') {
        const a = document.createElement('a'); a.className = 'btn ghost sm'; a.title = 'Abrir prontuário';
        a.innerHTML = '<svg class="ic"><use href="#i-prontuario"/></svg>Prontuário'; a.href = '/paciente/' + encodeURIComponent(r.codigo); td.append(a);
      }
      if (podeEditar) td.append(botao('editar', 'Editar', () => abrir(r)));
      if (podeExcluir) td.append(botao('excluir', 'Excluir', () => excluir(r), 'danger'));
      tbody.append(tr);
    }
  }

  function botao(icone, titulo, fn, cls = '') {
    const b = document.createElement('button'); b.type = 'button'; b.className = 'btn ghost sm so-ic ' + cls; b.title = titulo; b.onclick = fn;
    b.innerHTML = `<svg class="ic"><use href="#i-${icone}"/></svg>`; return b;
  }

  function abrir(r) {
    editId = r ? r.id : null; campos.innerHTML = '';
    document.getElementById('dlg-t').textContent = (r ? 'Editar ' : 'Novo registro · ') + meta.titulo;
    document.getElementById('dlg-erro').classList.add('hidden');
    for (const c of meta.campos) {
      const lab = document.createElement('label'); lab.textContent = c.rotulo;
      let el;
      if (c.tipo === 'select') {
        el = document.createElement('select');
        el.add(new Option('— selecione —', ''));
        valoresDe(c).forEach(o => el.add(new Option(o.rotulo, o.valor)));
      } else {
        el = document.createElement('input');
        el.type = {date: 'date', month: 'month', int: 'number', money: 'number'}[c.tipo] || 'text';
        if (c.tipo === 'money') el.step = '0.01';
        if (c.tipo === 'int') el.min = 0;
      }
      el.name = c.nome;
      const v = r ? r[c.nome] : (c.nome === 'mes' ? (mesEl.value || new Date().toISOString().slice(0, 7)) : c.nome === 'data' ? new Date().toISOString().slice(0, 10) : '');
      if (c.tipo === 'select' && v && ![...el.options].some(o => o.value === String(v))) el.add(new Option(v, v));
      el.value = v ?? '';
      lab.append(el); campos.append(lab);
    }
    dlg.showModal();
  }

  async function excluir(r) {
    const aviso = ent === 'pacientes' ? '\nTerapias e movimentações deste paciente também serão excluídas.' : '';
    if (!confirm('Excluir este registro?' + aviso)) return;
    try { await api(`/api/${ent}/${r.id}`, 'DELETE'); toast('Registro excluído.'); carregar(); } catch (e) { toast(e.message, true); }
  }

  frm.onsubmit = async e => {
    e.preventDefault();
    try {
      await api(editId ? `/api/${ent}/${editId}` : `/api/${ent}`, editId ? 'PUT' : 'POST', Object.fromEntries(new FormData(frm)));
      dlg.close(); toast('Registro salvo.'); Object.assign(opcoes, await api('/api/opcoes')); carregar();
    } catch (err) {
      const a = document.getElementById('dlg-erro'); a.textContent = err.message; a.classList.remove('hidden');
    }
  };

  document.getElementById('cancelar').onclick = () => dlg.close();
  document.getElementById('novo')?.addEventListener('click', () => abrir(null));
  let t; document.getElementById('q').addEventListener('input', () => { clearTimeout(t); t = setTimeout(carregar, 250); });
  mesEl.addEventListener('change', carregar);
  carregar();
})();

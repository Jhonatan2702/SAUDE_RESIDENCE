/* Fichas de resumo (bairro, profissional, paciente): uma janela que mostra tudo o que está ligado a quem foi clicado.
   O servidor devolve sempre o mesmo formato (fichas.py); aqui só desenhamos. Dá para navegar entre fichas
   (bairro → profissional → paciente → …) e voltar. Também cuida da busca rápida no topo dos painéis. */
const Ficha = (() => {
  let periodo = () => ({ini: '', fim: ''}), pilha = [], atual = null, abaAtual = null, tabelas = {};
  const ROTULO = {bairro: 'bairro', profissional: 'profissional', paciente: 'paciente'};

  async function abrir(tipo, valor, empilhar = true) {
    if (!valor) return;
    let r;
    try {
      r = await api(`/api/ficha/${tipo}?` + new URLSearchParams({valor, ...periodo()}));
    } catch (e) { return toast(e.message, true); }
    if (empilhar) pilha.push({tipo, valor});
    atual = r;
    desenhar();
    const dlg = $('dlg-ficha');
    if (!dlg.open) dlg.showModal();
  }

  function desenhar() {
    const r = atual, P = r.periodo;
    $('fx-trilha').textContent = pilha.length > 1
      ? pilha.slice(0, -1).map(p => ROTULO[p.tipo]).join(' › ') + ' › ' + r.trilha : r.trilha;
    $('fx-t').textContent = r.titulo;
    $('fx-voltar').hidden = pilha.length < 2;
    $('fx-chips').innerHTML = r.chips.map(c => `<span class="tag ${esc(c.tom || '')}">${esc(c.texto)}</span>`).join(' ') +
      ` <span class="muted">· período ${esc(fmtData(P.ini))} a ${esc(fmtData(P.fim))}</span>`;
    $('fx-kpis').innerHTML = r.kpis.map(k => `<button type="button" class="fb-k tom-${esc(k.tom || 'neutro')}" data-fa="${esc(k.aba || '')}">` +
      `<span>${esc(k.rotulo)}</span><b>${typeof k.valor === 'number' ? fmt(k.valor) : esc(k.valor)}</b>${k.sub ? `<small>${esc(k.sub)}</small>` : ''}</button>`).join('');
    $('fx-abas').innerHTML = r.abas.map(a => `<button type="button" data-fa="${esc(a.id)}">${esc(a.nome)}` +
      (a.tipo === 'tabela' ? `<span class="cont">${fmt(a.linhas.length)}</span>` : '') + '</button>').join('');
    // cada aba ganha seu próprio bloco; tabelas usam o componente comum (busca, ordenação, CSV)
    tabelas = {};
    $('fx-corpo').innerHTML = r.abas.map(a => `<section data-fp="${esc(a.id)}" hidden><p class="card-desc">${esc(a.desc || '')}</p>` + (
      a.tipo === 'tabela'
        ? `<div class="barra-tab"><input type="search" class="busca" id="fx-b-${esc(a.id)}" placeholder="Filtrar nesta lista…">` +
          (a.filtros ? `<select id="fx-f-${esc(a.id)}" style="width:auto">${a.filtros.map((f, i) => `<option value="${i}">${esc(f.rotulo)}</option>`).join('')}</select>` : '') +
          `<button type="button" class="btn sm" data-csv="fx-t-${esc(a.id)}">Exportar CSV</button><span class="contador" id="fx-n-${esc(a.id)}"></span></div>` +
          `<div class="tabela-wrap" style="max-height:46vh"><table id="fx-t-${esc(a.id)}"></table></div>`
        : a.tipo === 'barras' ? `<div class="lbar" id="fx-l-${esc(a.id)}"></div>`
          : `<dl class="fx-dados">${a.pares.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>`) + '</section>').join('');
    r.abas.forEach(a => {
      if (a.tipo === 'tabela') {
        const filtroSel = a.filtros && $(`fx-f-${a.id}`);
        tabelas[a.id] = Tabela(`fx-t-${a.id}`, {
          busca: `fx-b-${a.id}`, contador: `fx-n-${a.id}`, numericas: a.numericas || [],
          filtro: filtroSel ? l => { const f = a.filtros[+filtroSel.value]; return f.col === undefined || (l[f.col] && l[f.col] !== '—'); } : null,
          aoClicar: a.abrir ? l => abrir(a.abrir.tipo, String(l[a.abrir.col])) : null,
          vazio: 'Nada a mostrar.',
        });
        if (filtroSel) filtroSel.onchange = () => tabelas[a.id].redesenhar();
        tabelas[a.id].dados(a.colunas, a.linhas);
      } else if (a.tipo === 'barras') {
        listaBarras(`fx-l-${a.id}`, a.itens, {max: a.ordem ? 24 : 30, total: a.ordem ? 0 : a.itens.reduce((s, i) => s + i.valor, 0)});
        if (a.abrir) $(`fx-l-${a.id}`).onclick = e => { const lb = e.target.closest('.lb'); if (lb) abrir(a.abrir.tipo, lb.title); };
      }
    });
    const primeira = r.abas.find(a => a.id === abaAtual && pilha.length && atual.tipo === pilha[pilha.length - 1].tipo)
      || r.abas.find(a => a.tipo !== 'tabela' || a.linhas.length) || r.abas[0];
    aba(primeira.id);
  }

  function aba(id) {
    if (!id) return;
    abaAtual = id;
    document.querySelectorAll('#fx-abas [data-fa]').forEach(b => b.classList.toggle('on', b.dataset.fa === id));
    document.querySelectorAll('#fx-corpo [data-fp]').forEach(s => { s.hidden = s.dataset.fp !== id; });
  }

  function iniciar() {
    if (!$('dlg-ficha')) return;
    $('fx-abas').onclick = e => { const b = e.target.closest('[data-fa]'); if (b) aba(b.dataset.fa); };
    $('fx-kpis').onclick = e => { const b = e.target.closest('[data-fa]'); if (b) aba(b.dataset.fa); };
    $('fx-fechar').onclick = () => $('dlg-ficha').close();
    $('dlg-ficha').addEventListener('close', () => { pilha = []; });
    $('fx-voltar').onclick = () => { pilha.pop(); const ant = pilha[pilha.length - 1]; if (ant) abrir(ant.tipo, ant.valor, false); };
    iniciarBusca();
    // links diretos: /painel?bairro=Meireles, ?paciente=Nome, ?profissional=Nome
    addEventListener('load', () => {
      const q = new URLSearchParams(location.search);
      for (const tipo of ['bairro', 'profissional', 'paciente']) if (q.get(tipo)) return setTimeout(() => abrir(tipo, q.get(tipo)), 600);
    });
  }

  // ---------------------------------------------------------------- busca rápida
  function iniciarBusca() {
    const campo = $('busca-global'), lista = $('busca-resultados');
    if (!campo) return;
    let espera, itens = [], marcado = -1;
    const fechar = () => { lista.hidden = true; marcado = -1; };
    const escolher = i => { const it = itens[i]; if (!it) return; fechar(); campo.value = ''; abrir(it.tipo, it.valor); };
    const marcar = i => {
      marcado = Math.max(0, Math.min(itens.length - 1, i));
      lista.querySelectorAll('[data-i]').forEach(el => el.classList.toggle('on', +el.dataset.i === marcado));
    };
    campo.addEventListener('input', () => {
      clearTimeout(espera);
      const q = campo.value.trim();
      if (q.length < 2) return fechar();
      espera = setTimeout(async () => {
        try {
          const r = await api('/api/busca?' + new URLSearchParams({q}));
          itens = [...r.pacientes.map(p => ({tipo: 'paciente', valor: p.nome, nome: p.nome, detalhe: p.detalhe})),
            ...r.profissionais.map(p => ({tipo: 'profissional', valor: p.chave, nome: p.nome, detalhe: p.detalhe}))];
          let i = -1;
          const grupo = (titulo, tipo) => {
            const g = itens.map((it, k) => [it, k]).filter(([it]) => it.tipo === tipo);
            return g.length ? `<b>${titulo}</b>` + g.map(([it, k]) => `<button type="button" data-i="${k}"><span>${esc(it.nome)}</span><small>${esc(it.detalhe)}</small></button>`).join('') : '';
          };
          lista.innerHTML = (grupo('Pacientes', 'paciente') + grupo('Profissionais', 'profissional')) || '<p class="muted">Ninguém encontrado com esse nome.</p>';
          lista.hidden = false; marcado = i;
        } catch (e) { toast(e.message, true); }
      }, 250);
    });
    campo.addEventListener('keydown', e => {
      if (lista.hidden) return;
      if (e.key === 'ArrowDown') { e.preventDefault(); marcar(marcado + 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); marcar(marcado - 1); }
      else if (e.key === 'Enter') { e.preventDefault(); escolher(marcado < 0 ? 0 : marcado); }
      else if (e.key === 'Escape') fechar();
    });
    lista.addEventListener('click', e => { const b = e.target.closest('[data-i]'); if (b) escolher(+b.dataset.i); });
    document.addEventListener('click', e => { if (!e.target.closest('.busca-global')) fechar(); });
  }

  document.addEventListener('DOMContentLoaded', iniciar);
  return {configurar: fn => { periodo = fn; }, abrir};
})();

// compatibilidade: o mapa e as tabelas chamam FichaBairro.abrir(nome do bairro)
const FichaBairro = {abrir: b => Ficha.abrir('bairro', b), configurar: fn => Ficha.configurar(fn)};

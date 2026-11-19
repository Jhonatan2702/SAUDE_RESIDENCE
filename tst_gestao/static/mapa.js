/* Mapa de bairros de Fortaleza (SVG, sem biblioteca externa).
   Contornos: static/fortaleza-bairros.geojson. Os bairros são casados pelo nome sem acento e em maiúsculas,
   o mesmo padrão que o servidor aplica aos dados da URL. */
const MapaFortaleza = (() => {
  let geo = null;
  const norm = s => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase().replace(/\s+/g, ' ').trim();
  // escalas sequenciais de um só tom (claro = pouco, escuro = muito)
  const RAMPAS = {
    azul: ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b'],
    laranja: ['#fde3d3', '#fbc4a4', '#f6a074', '#eb6834', '#c9531f', '#a04015', '#702b0c'],
  };
  const VAZIO = '#e9edf2';
  const carregarGeo = async () => (geo ||= await fetch('/static/fortaleza-bairros.geojson').then(r => r.json()));

  function criar(svgId, {aoPassar, aoClicar, legendaId, rotuloValor = v => fmt(v)} = {}) {
    const svg = $(svgId);
    const dica = document.createElement('div'); dica.className = 'mapa-dica'; document.body.append(dica);
    let caminhos = null, valores = new Map(), selecionado = null;

    async function preparar() {
      if (caminhos) return;
      const g = await carregarGeo();
      const pts = g.features.flatMap(f => f.geometry.coordinates.flat());
      const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
      const x0 = Math.min(...xs), y1 = Math.max(...ys), kx = Math.cos(-3.76 * Math.PI / 180);
      const w = (Math.max(...xs) - x0) * kx, h = y1 - Math.min(...ys), ea = 100 / Math.max(w, h);
      svg.setAttribute('viewBox', `0 0 ${(w * ea).toFixed(2)} ${(h * ea).toFixed(2)}`);
      svg.innerHTML = g.features.map(f => {
        const d = f.geometry.coordinates.map(a => 'M' + a.map(p => `${((p[0] - x0) * kx * ea).toFixed(2)},${((y1 - p[1]) * ea).toFixed(2)}`).join('L') + 'Z').join('');
        return `<path d="${d}" data-bairro="${esc(norm(f.properties.bairro))}" data-nome="${esc(f.properties.bairro)}" fill-rule="evenodd"/>`;
      }).join('');
      caminhos = [...svg.querySelectorAll('path')];
      svg.addEventListener('mousemove', e => {
        const p = e.target.closest('path');
        if (!p) { dica.classList.remove('on'); return; }
        const v = valores.get(p.dataset.bairro) || 0;
        dica.innerHTML = `<b>${esc(p.dataset.nome)}</b>${rotuloValor(v)}`;
        dica.style.left = Math.min(e.clientX + 14, innerWidth - dica.offsetWidth - 8) + 'px';
        dica.style.top = (e.clientY + 14) + 'px';
        dica.classList.add('on');
        aoPassar?.(p.dataset.bairro, p.dataset.nome);
      });
      svg.addEventListener('mouseleave', () => { dica.classList.remove('on'); aoPassar?.(null); });
      svg.addEventListener('click', e => {
        const p = e.target.closest('path');
        selecionar(p && p.dataset.bairro !== selecionado ? p.dataset.bairro : null);
        aoClicar?.(selecionado, p?.dataset.nome);
      });
    }

    function selecionar(chave) {
      selecionado = chave;
      caminhos?.forEach(p => p.classList.toggle('sel', p.dataset.bairro === chave));
    }

    /* dados: {bairro: número}; opções: rampa, alerta (bairros com contorno de atenção) */
    async function desenhar(dados, {rampa = 'azul', alerta = new Set(), atencao = new Set(), destaque = new Set(), rotuloDestaque = 'bairros da zona'} = {}) {
      await preparar();
      valores = new Map(Object.entries(dados).map(([b, v]) => [norm(b), v]));
      const cores = RAMPAS[rampa];
      const max = Math.max(0, ...valores.values());
      // faixas inteiras de mesmo tamanho (no máximo 7)
      const tam = Math.max(1, Math.ceil(max / cores.length));
      const passos = Math.max(1, Math.ceil(max / tam));
      const faixa = v => Math.min(passos - 1, Math.floor((v - 1) / tam));
      const paleta = Array.from({length: passos}, (_, i) => cores[Math.round(i * (cores.length - 1) / Math.max(1, passos - 1))]);
      const noMapa = new Set();
      if (destaque.size) svg.append(...caminhos.filter(p => destaque.has(p.dataset.bairro)));  // contorno por cima
      caminhos.forEach(p => {
        const v = valores.get(p.dataset.bairro) || 0;
        noMapa.add(p.dataset.bairro);
        p.setAttribute('fill', v > 0 ? paleta[faixa(v)] : VAZIO);
        p.classList.toggle('alerta', alerta.has(p.dataset.bairro));
        p.classList.toggle('atencao', atencao.has(p.dataset.bairro));
        p.classList.toggle('destaque', destaque.has(p.dataset.bairro));
        p.classList.toggle('com-dado', v > 0);
      });
      if (legendaId) {
        $(legendaId).innerHTML = max ? paleta.map((c, i) => {
          const a = i * tam + 1, b = Math.min(max, (i + 1) * tam);
          return `<span><i style="background:${c}"></i>${a === b ? fmt(a) : `${fmt(a)}–${fmt(b)}`}</span>`;
        }).join('') + `<span><i style="background:${VAZIO}"></i>nenhum</span>` +
          (atencao.size ? '<span><i class="leg-atencao"></i>descoberto no período, mas coberto</span>' : '') +
          (alerta.size ? `<span><i class="leg-alerta"></i>${atencao.size ? 'sem nenhum profissional' : 'atenção'}</span>` : '') +
          (destaque.size ? `<span><i class="leg-destaque"></i>${esc(rotuloDestaque)}</span>` : '') : '<span class="muted">Sem dados para este filtro.</span>';
      }
      // bairros dos dados que não existem no mapa (grafia diferente da base cartográfica)
      return [...valores.entries()].filter(([b, v]) => v > 0 && !noMapa.has(b)).map(([b]) => b);
    }

    return {desenhar, selecionar, selecionado: () => selecionado, norm};
  }
  return {criar, norm};
})();

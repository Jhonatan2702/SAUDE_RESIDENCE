const CSRF = document.querySelector('meta[name=csrf]')?.content || '';

async function api(url, method = 'GET', body) {
  const opt = {method, headers: {'X-CSRF-Token': CSRF}};
  if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  const r = await fetch(url, opt);
  if (r.status === 401) { location.href = '/login'; throw new Error('Sessão expirada.'); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.erro || 'Erro inesperado.');
  return data;
}

function esc(v) {
  return String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}

function toast(msg, erro = false) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.className = 'show' + (erro ? ' err' : '');
  clearTimeout(t._h); t._h = setTimeout(() => t.className = '', 3200);
}

function fmtData(v) { return /^\d{4}-\d{2}-\d{2}$/.test(v || '') ? v.split('-').reverse().join('/') : (v || ''); }

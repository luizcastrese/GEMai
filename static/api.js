const BASE = '/api/v1';
const K = 'erp.token';
let token = null;
try { token = sessionStorage.getItem(K); } catch { /* armazenamento indisponível */ }

export const temToken = () => !!token;
export function setToken(t) {
  token = t;
  try { t ? sessionStorage.setItem(K, t) : sessionStorage.removeItem(K); } catch { /* ignore */ }
}

let aoExpirar = () => {};
export const quandoExpirar = (fn) => { aoExpirar = fn; };

function mensagem(det) {
  if (typeof det === 'string') return det;
  if (Array.isArray(det)) return det.map((e) => `${(e.loc || []).slice(1).join('.')}: ${e.msg}`).join('; ');
  return 'Erro inesperado.';
}

export async function api(metodo, caminho, corpo) {
  const opts = { method: metodo, headers: {} };
  if (token) opts.headers.Authorization = `Bearer ${token}`;
  if (corpo !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(corpo); }
  let r;
  try { r = await fetch(BASE + caminho, opts); } catch { throw new Error('Sem conexão com o servidor.'); }
  if (r.status === 204) return null;
  let dados = null;
  try { dados = await r.json(); } catch { /* corpo vazio */ }
  if (r.status === 401 && token) { setToken(null); aoExpirar(); }
  if (!r.ok) throw new Error(mensagem(dados && dados.detail));
  return dados;
}
export const get = (c) => api('GET', c);
export const post = (c, b = {}) => api('POST', c, b);
export const patch = (c, b = {}) => api('PATCH', c, b);
export const qs = (o) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') p.set(k, v); });
  const s = p.toString();
  return s ? `?${s}` : '';
};

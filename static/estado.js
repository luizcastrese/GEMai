import { get } from './api.js';

export const estado = { usuario: null, empresa: null, unidades: [], unidadeId: null };
const KU = 'erp.unidade';

export async function carregarBase() {
  const [u, e, un] = await Promise.all([get('/auth/eu'), get('/empresa'), get('/unidades')]);
  estado.usuario = u; estado.empresa = e; estado.unidades = un.filter((x) => x.ativa);
  let salva = null;
  try { salva = Number(sessionStorage.getItem(KU)); } catch { /* ignore */ }
  estado.unidadeId = estado.unidades.find((x) => x.id === salva)?.id ?? estado.unidades[0]?.id ?? null;
}
export function escolherUnidade(id) {
  estado.unidadeId = Number(id);
  try { sessionStorage.setItem(KU, String(id)); } catch { /* ignore */ }
}
export const unidadeAtual = () => estado.unidades.find((u) => u.id === estado.unidadeId);
export const ehGestor = () => ['admin', 'gestor'].includes(estado.usuario?.perfil);
export const ehAdmin = () => estado.usuario?.perfil === 'admin';

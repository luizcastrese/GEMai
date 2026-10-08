// Helpers de DOM. Nunca usa innerHTML: todo texto entra como nó de texto (anti-XSS).
export function h(tag, attrs, ...filhos) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'class') el.className = v;
    else if (k === 'value') el.value = v;
    else if (k === 'checked' || k === 'disabled' || k === 'selected') el[k] = !!v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  add(el, filhos);
  return el;
}
function add(el, filhos) {
  for (const f of filhos.flat(Infinity)) {
    if (f === null || f === undefined || f === false) continue;
    el.append(f instanceof Node ? f : document.createTextNode(String(f)));
  }
}
export const limpar = (el) => { while (el.firstChild) el.removeChild(el.firstChild); return el; };
export const montar = (el, ...filhos) => { limpar(el); add(el, filhos); return el; };

export function toast(msg, erro = false) {
  const t = h('div', { class: `toast${erro ? ' err' : ''}` }, msg);
  document.getElementById('toasts').append(t);
  setTimeout(() => t.remove(), erro ? 7000 : 3500);
}
export async function tentar(fn, ok) {
  try { const r = await fn(); if (ok) toast(ok); return r; } catch (e) { toast(e.message, true); return undefined; }
}

export function modal(titulo, corpo, { larga = false, acoes } = {}) {
  const fundo = h('div', { class: 'modal-bg', onmousedown: (e) => { if (e.target === fundo) fechar(); } });
  const fechar = () => fundo.remove();
  const caixa = h('div', { class: `modal${larga ? ' wide' : ''}`, role: 'dialog', 'aria-modal': 'true', 'aria-label': titulo },
    h('h2', { style: undefined }, titulo), corpo, acoes ? h('div', { class: 'acts' }, acoes(fechar)) : null);
  fundo.append(caixa);
  document.body.append(fundo);
  const primeiro = caixa.querySelector('input,select,textarea');
  if (primeiro) primeiro.focus();
  return fechar;
}
export function confirmar(texto, aoConfirmar, rotulo = 'Confirmar') {
  modal('Confirmação', h('p', null, texto), { acoes: (fechar) => [
    h('button', { onclick: fechar }, 'Cancelar'),
    h('button', { class: 'pri', onclick: () => { fechar(); aoConfirmar(); } }, rotulo)] });
}

// Formulário a partir de definição de campos. Retorna {el, valores()}.
export function formulario(campos, inicial = {}) {
  const refs = {};
  const el = h('div', null, campos.map((c) => {
    let inp;
    const v = inicial[c.k] ?? c.padrao ?? '';
    if (c.tipo === 'textarea') inp = h('textarea', { value: v });
    else if (c.tipo === 'select') inp = h('select', null, (c.opcoes || []).map((o) => {
      const [val, rot] = Array.isArray(o) ? o : [o, o];
      return h('option', { value: val, selected: String(val) === String(v) }, rot);
    }));
    else if (c.tipo === 'bool') inp = h('input', { type: 'checkbox', checked: !!inicial[c.k] });
    else if (c.tipo === 'lista') inp = h('input', { type: 'text', value: Array.isArray(v) ? v.join(', ') : v, placeholder: 'separe por vírgulas' });
    else inp = h('input', { type: c.tipo || 'text', value: v, step: c.tipo === 'number' ? 'any' : undefined, min: c.min, maxlength: c.max, placeholder: c.dica });
    refs[c.k] = { inp, c };
    return h('div', null, h('label', null, c.rotulo), inp, c.ajuda ? h('div', { class: 'muted small' }, c.ajuda) : null);
  }));
  const valores = () => {
    const o = {};
    for (const [k, { inp, c }] of Object.entries(refs)) {
      if (c.tipo === 'bool') o[k] = inp.checked;
      else if (c.tipo === 'number') o[k] = inp.value === '' ? null : Number(inp.value);
      else if (c.tipo === 'lista') o[k] = inp.value.split(',').map((s) => s.trim()).filter(Boolean);
      else if (c.tipo === 'select' && c.num) o[k] = inp.value === '' ? null : Number(inp.value);
      else o[k] = inp.value.trim() === '' && c.nulo ? null : inp.value.trim();
    }
    return o;
  };
  return { el, valores, refs };
}

export const badge = (txt, tipo = '') => h('span', { class: `badge ${tipo}` }, txt);
const STATUS = {
  planejada: ['', 'Planejada'], liberada: ['b-pri', 'Liberada'], em_producao: ['b-pri', 'Em produção'],
  parada: ['b-warn', 'Parada'], concluida: ['b-ok', 'Concluída'], cancelada: ['b-err', 'Cancelada'],
  rascunho: ['b-warn', 'Rascunho'], ativo: ['b-ok', 'Ativo'], substituido: ['', 'Substituído'], arquivado: ['', 'Arquivado'],
  pendente: ['b-warn', 'Pendente'], em_andamento: ['b-pri', 'Em andamento'], pulada: ['', 'Pulada'],
  registrado: ['b-warn', 'A aprovar'], aprovado: ['b-ok', 'Aprovado'], rejeitado: ['b-err', 'Rejeitado'],
  aplicada: ['b-ok', 'Aplicada'], aprovada: ['b-ok', 'Aprovada'], rejeitada: ['b-err', 'Rejeitada'],
  validado: ['b-ok', 'Validado'],
};
export const statusBadge = (s) => badge((STATUS[s] || ['', s])[1], (STATUS[s] || [''])[0]);
const FONTE = { historico: ['b-ok', 'Histórico'], parametro: ['b-pri', 'Parâmetro'], modelo_ia: ['b-ia', 'Modelo IA'], sem_base: ['b-warn', 'Sem base'] };
export const fonteBadge = (f) => badge((FONTE[f] || ['', f])[1], (FONTE[f] || [''])[0]);
const ORIGEM = { informado: ['', 'Informado'], medido: ['b-ok', 'Medido'], calculado: ['b-pri', 'Calculado'], ia_sugerido: ['b-ia', 'Sugestão IA'] };
export const origemBadge = (o) => badge((ORIGEM[o] || ['', o])[1], (ORIGEM[o] || [''])[0]);

export function fmtMin(m) {
  if (m === null || m === undefined) return '—';
  const t = Math.round(m);
  if (t < 60) return `${t} min`;
  return `${Math.floor(t / 60)}h ${String(t % 60).padStart(2, '0')}min`;
}
export const fmtNum = (n, c = 1) => (n === null || n === undefined ? '—' : Number(n).toLocaleString('pt-BR', { maximumFractionDigits: c }));
export const fmtPct = (n) => (n === null || n === undefined ? '—' : `${fmtNum(n)}%`);
export const fmtData = (iso) => (iso ? new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : '—');
export const fmtDia = (d) => (d ? new Date(`${d}T12:00:00`).toLocaleDateString('pt-BR') : '—');

export function tabela(colunas, linhas, vazio = 'Nenhum registro.') {
  if (!linhas.length) return h('p', { class: 'muted' }, vazio);
  return h('div', { class: 'tw' }, h('table', null,
    h('thead', null, h('tr', null, colunas.map((c) => h('th', null, c.t)))),
    h('tbody', null, linhas.map((l) => h('tr', null, colunas.map((c) => h('td', null, c.f(l))))))));
}
export const kpi = (rotulo, valor, tom = '') => h('div', { class: `card kpi ${tom}` }, h('div', { class: 'v' }, valor), h('div', { class: 'l' }, rotulo));

export function barras(rotulos, valores, { sufixo = '', cor = '#1f5fbf' } = {}) {
  const ns = 'http://www.w3.org/2000/svg';
  const W = 520, H = 130, pad = 22;
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('class', 'chart'); svg.setAttribute('role', 'img');
  const max = Math.max(1, ...valores.map((v) => v || 0));
  const bw = (W - 2 * pad) / Math.max(valores.length, 1);
  valores.forEach((v, i) => {
    const alt = ((v || 0) / max) * (H - 2 * pad);
    const r = document.createElementNS(ns, 'rect');
    r.setAttribute('x', pad + i * bw + 4); r.setAttribute('y', H - pad - alt);
    r.setAttribute('width', Math.max(bw - 8, 2)); r.setAttribute('height', alt); r.setAttribute('fill', cor); r.setAttribute('rx', 3);
    svg.append(r);
    const t = document.createElementNS(ns, 'text');
    t.setAttribute('x', pad + i * bw + bw / 2); t.setAttribute('y', H - 8); t.setAttribute('text-anchor', 'middle');
    t.textContent = rotulos[i];
    svg.append(t);
    const val = document.createElementNS(ns, 'text');
    val.setAttribute('x', pad + i * bw + bw / 2); val.setAttribute('y', H - pad - alt - 3); val.setAttribute('text-anchor', 'middle');
    val.textContent = v === null || v === undefined ? '' : `${fmtNum(v, 0)}${sufixo}`;
    svg.append(val);
  });
  return svg;
}

export function avisoIA(texto) {
  return h('div', { class: 'aviso-ia' }, h('strong', null, 'Sugestão gerada por IA. '),
    texto || 'Não é um fato: precisa ser revisada e validada por um responsável antes de ser usada.');
}

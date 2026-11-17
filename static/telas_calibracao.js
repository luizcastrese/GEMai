// Calibração: o sistema compara o previsto com o realizado nas ordens concluídas e PROPÕE correções; nada vale até uma pessoa validar.
import { get, post, qs } from './api.js';
import { estado } from './estado.js';
import { confirmar, detalhes, fmtNum, h, kpi, montar, tentar, toast } from './ui.js';

const LIM_MIN = 0.5, LIM_MAX = 2.0;
const vezes = (f) => `× ${fmtNum(f, 2)}`;
const pct = (v) => (v === null || v === undefined ? '—' : `${fmtNum(v, 1)}%`);

// Fator para um pedido de porte `x` (tempo normal previsto por unidade): fator_ref × (x ÷ porte_ref)^expoente, limitado a 0,5–2,0.
export const fatorEm = (c, x) => {
  if (!c.expoente || !c.porte_ref) return c.fator;
  return Math.min(Math.max(c.fator * ((x / c.porte_ref) ** c.expoente), LIM_MIN), LIM_MAX);
};
export function frase(f) {
  const d = Math.round((f - 1) * 100);
  if (d === 0) return 'Fica igual ao previsto';
  return d > 0 ? `Leva ${d}% a mais que o previsto` : `Leva ${-d}% a menos que o previsto`;
}

function barraErro(rotulo, v, max, destaque) {
  const b = h('div', { class: 'bar' }, h('i'));
  b.firstChild.style.width = `${v === null || v === undefined ? 0 : Math.max(2, (v / max) * 100)}%`;
  return h('div', { class: `prova${destaque ? ' on' : ''}` }, h('div', { class: 'prova-l' }, h('span', null, rotulo), h('strong', null, pct(v))), b);
}

function prova(c) {
  const vals = [c.erro_sem_pct, c.erro_constante_pct, c.erro_com_pct].filter((v) => v !== null && v !== undefined);
  if (!vals.length) return null;
  const max = Math.max(...vals, 1);
  const escala = !!c.expoente;
  return h('div', { class: 'provas' },
    h('div', { class: 'small muted' }, 'Erro típico ao prever pedidos que ficaram de fora do cálculo (quanto menor, melhor)'),
    barraErro('Sem calibração', c.erro_sem_pct, max),
    escala ? barraErro('Com um fator único', c.erro_constante_pct, max) : null,
    barraErro(escala ? 'Com esta proposta (escala com o tamanho)' : 'Com esta proposta', c.erro_com_pct, max, true));
}

function decidir(c, acao, depois) {
  const aplicar = acao === 'validar';
  confirmar(aplicar ? 'Aplicar esta correção aos novos planos? Planos já gerados não mudam.' : 'Ignorar esta proposta? Nada muda nos cálculos.', async () => {
    if (await tentar(() => post(`/calibracao/modulos/${c.id}/${acao}`, {}), aplicar ? 'Correção aplicada.' : 'Proposta ignorada.')) depois();
  }, aplicar ? 'Aplicar' : 'Ignorar');
}

const titulo = (c) => `${c.titulo || c.modulo} · ${c.produto_nome || 'todos os produtos'}`;

function cartaoProposta(c, depois) {
  const escala = !!c.expoente;
  const aviso = /NÃO melhora|descartada/.test(c.justificativa || '') ? c.justificativa.split(/(?<=\.)\s+/).filter((t) => /NÃO melhora|descartada/.test(t)).join(' ') : '';
  return h('div', { class: 'card calib' },
    h('h3', null, titulo(c)),
    h('p', { class: 'big-txt' }, frase(c.fator), escala ? ' (muda com o tamanho do pedido)' : '', '.'),
    aviso ? h('div', { class: 'aviso' }, aviso) : null,
    h('div', { class: 'inline' },
      h('button', { class: 'pri', onclick: () => decidir(c, 'validar', depois) }, 'Aplicar'),
      h('button', { onclick: () => decidir(c, 'rejeitar', depois) }, 'Ignorar')),
    detalhes('Ver como chegamos nisso',
      h('p', { class: 'muted small' }, `Baseado em ${c.amostras} ordens concluídas e aprovadas. Fator ${vezes(c.fator)}${escala ? ' para o pedido típico' : ''}.`),
      escala ? h('div', { class: 'grid g4' },
        kpi('Menor pedido já feito', vezes(fatorEm(c, c.porte_min)), 'peq'),
        kpi('Pedido típico', vezes(fatorEm(c, c.porte_ref)), 'peq'),
        kpi('Maior pedido já feito', vezes(fatorEm(c, c.porte_max)), 'peq')) : null,
      prova(c)));
}

export async function calibracao(el) {
  const u = estado.unidadeId;
  const carregar = async () => {
    const [lista, previa] = await Promise.all([get(`/calibracao/modulos${qs({ unidade_id: u })}`), post('/calibracao/modulos', { unidade_id: u, aplicar: false })]);
    const pendentes = lista.filter((c) => c.status === 'pendente').sort((a, b) => (b.produto_id ? 1 : 0) - (a.produto_id ? 1 : 0));
    const vigentes = lista.filter((c) => c.vigente);
    const faltam = previa.modulos.filter((m) => m.status === 'insuficiente');
    montar(el,
      h('h1', null, 'Calibração'),
      h('p', { class: 'muted' }, 'Compara o previsto com o que levou de verdade e propõe correções. Nada muda até você aplicar.'),
      h('div', { class: 'inline noprint' }, h('button', { class: 'pri', onclick: async () => {
        const r = await tentar(() => post('/calibracao/modulos', { unidade_id: u, aplicar: true }));
        if (r) { toast(r.propostas ? `${r.propostas} proposta(s) nova(s).` : 'Ainda não há dados suficientes.'); carregar(); }
      } }, 'Buscar propostas')),
      pendentes.length ? [h('h2', null, `Para você decidir (${pendentes.length})`), pendentes.map((c) => cartaoProposta(c, carregar))] : null,
      vigentes.length ? [h('h2', null, 'Já aplicadas'), h('div', { class: 'card' }, vigentes.map((c) => h('div', { class: 'lig' },
        h('strong', null, titulo(c)), h('span', { class: 'muted' }, `${vezes(c.fator)}${c.expoente ? ', muda com o tamanho' : ''}`))))] : null,
      !pendentes.length && !vigentes.length ? h('div', { class: 'card' }, h('p', { class: 'muted' }, 'Nenhuma correção ainda. Os planos usam os tempos de referência do catálogo.')) : null,
      faltam.length ? detalhes(`Ainda sem dados suficientes (${faltam.length})`,
        h('ul', null, faltam.map((m) => h('li', { class: 'small' }, `${m.titulo} · ${m.produto_nome || 'todos os produtos'}: ${m.amostras} de ${m.minimo} ordens`))),
        h('p', { class: 'muted small' }, 'Por produto, também é preciso ter pedidos de pelo menos 3 tamanhos diferentes.')) : null);
  };
  await carregar();
}

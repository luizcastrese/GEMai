// Calibração: o sistema compara o previsto com o realizado nas ordens concluídas e PROPÕE correções; nada vale até uma pessoa validar.
import { get, post, qs } from './api.js';
import { estado } from './estado.js';
import { badge, fmtData, fmtNum, formulario, h, kpi, modal, montar, tabela, tentar, toast } from './ui.js';

const LIM_MIN = 0.5, LIM_MAX = 2.0;
const vezes = (f) => `× ${fmtNum(f, 2)}`;
const pct = (v) => (v === null || v === undefined ? '—' : `${fmtNum(v, 1)}%`);
const quem = (c) => (c.produto_nome ? badge(`Produto: ${c.produto_nome}`, 'b-pri') : badge('Todos os produtos'));

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
  const rotulo = acao === 'validar' ? 'Validar' : 'Rejeitar';
  const f = formulario([{ k: 'observacao', rotulo: 'Observação (opcional)', tipo: 'textarea', dica: 'Por que validou ou rejeitou?' }]);
  modal(`${rotulo} calibração`, h('div', null,
    h('p', { class: 'muted' }, acao === 'validar'
      ? 'A partir de agora, os novos planos usam este fator e aparecem rotulados como calibrados. Planos já gerados não mudam; recalcule-os se quiser.'
      : 'A proposta é descartada e nada muda nos cálculos.'), f.el), {
    acoes: (fechar) => [h('button', { onclick: fechar }, 'Cancelar'),
      h('button', { class: acao === 'validar' ? 'pri' : 'dng', onclick: async () => {
        const r = await tentar(() => post(`/calibracao/modulos/${c.id}/${acao}`, { observacao: f.valores().observacao || '' }), acao === 'validar' ? 'Calibração validada.' : 'Proposta rejeitada.');
        if (r) { fechar(); depois(); }
      } }, rotulo)] });
}

function cartaoProposta(c, depois) {
  const escala = !!c.expoente;
  return h('div', { class: 'card calib' },
    h('div', { class: 'calib-t' }, h('h3', null, c.titulo || c.modulo), quem(c), badge(`v${c.versao}`)),
    h('p', { class: 'big-txt' }, h('strong', null, `${vezes(c.fator)}`), ` — ${frase(c.fator).toLowerCase()}`, escala ? ' num pedido típico.' : '.'),
    escala ? h('div', null,
      h('p', { class: 'muted small' }, 'O desvio muda com o tamanho do pedido. Pelo que as ordens anteriores mostraram, o fator para cada tamanho é:'),
      h('div', { class: 'grid g4' },
        kpi('Menor pedido já feito', vezes(fatorEm(c, c.porte_min)), 'peq'),
        kpi('Pedido típico', vezes(fatorEm(c, c.porte_ref)), 'peq'),
        kpi('Maior pedido já feito', vezes(fatorEm(c, c.porte_max)), 'peq')),
      h('p', { class: 'muted small' }, `Fora dessa faixa o fator é travado na borda e o passo aparece como "extrapolado". Tamanho medido pelo tempo normal previsto por unidade (${fmtNum(c.porte_min, 1)} a ${fmtNum(c.porte_max, 1)} min).`)) : null,
    prova(c),
    /NÃO melhora|descartada/.test(c.justificativa || '') ? h('div', { class: 'aviso' }, c.justificativa.split(/(?<=\.)\s+/).filter((t) => /NÃO melhora|descartada/.test(t)).join(' ')) : null,
    h('p', { class: 'muted small' }, `Baseado em ${c.amostras} operações concluídas e aprovadas.`),
    h('div', { class: 'inline' },
      h('button', { class: 'pri', onclick: () => decidir(c, 'validar', depois) }, 'Validar'),
      h('button', { class: 'dng', onclick: () => decidir(c, 'rejeitar', depois) }, 'Rejeitar')));
}

export async function calibracao(el) {
  const u = estado.unidadeId;
  const carregar = async () => {
    const [lista, previa] = await Promise.all([get(`/calibracao/modulos${qs({ unidade_id: u })}`), post('/calibracao/modulos', { unidade_id: u, aplicar: false })]);
    const pendentes = lista.filter((c) => c.status === 'pendente').sort((a, b) => (b.produto_id ? 1 : 0) - (a.produto_id ? 1 : 0));
    const vigentes = lista.filter((c) => c.vigente);
    const faltam = previa.modulos.filter((m) => m.status === 'insuficiente');
    const sugeridas = previa.modulos.filter((m) => m.status === 'sugerido').length;
    montar(el,
      h('h1', null, 'Calibração'),
      h('p', { class: 'muted' }, 'O sistema compara o tempo previsto com o que realmente levou nas ordens concluídas e propõe correções. Nada muda nos planos até você validar.'),
      h('div', { class: 'card inline noprint' },
        h('button', { class: 'pri', onclick: async () => {
          const r = await tentar(() => post('/calibracao/modulos', { unidade_id: u, aplicar: true }));
          if (r) { toast(r.propostas ? `${r.propostas} proposta(s) criada(s). Confira abaixo.` : 'Ainda não há dados suficientes para propor.'); carregar(); }
        } }, 'Calcular propostas com os apontamentos atuais'),
        h('span', { class: 'muted small' }, sugeridas ? `${sugeridas} sugestão(ões) possível(is) agora. Uma proposta nova substitui a pendente anterior do mesmo item.`
          : 'Ainda sem sugestões: faltam ordens concluídas com apontamentos aprovados.')),
      h('h2', null, `Aguardando a sua validação${pendentes.length ? ` (${pendentes.length})` : ''}`),
      pendentes.length ? pendentes.map((c) => cartaoProposta(c, carregar)) : h('div', { class: 'card' }, h('p', { class: 'muted' }, 'Nenhuma proposta pendente.')),
      h('h2', null, 'Em uso nos planos'),
      h('div', { class: 'card' }, tabela([
        { t: 'Módulo', f: (c) => c.titulo || c.modulo },
        { t: 'Vale para', f: (c) => quem(c) },
        { t: 'Fator', f: (c) => (c.expoente ? `${vezes(c.fator)} (típico), escala com o tamanho` : vezes(c.fator)) },
        { t: 'Amostras', f: (c) => c.amostras },
        { t: 'Versão', f: (c) => `v${c.versao}` },
        { t: 'Validada em', f: (c) => fmtData(c.validado_em) }], vigentes, 'Nenhuma calibração em uso: os planos usam os coeficientes genéricos do catálogo.')),
      faltam.length ? h('div', null, h('h2', null, 'Ainda sem dados suficientes'),
        h('div', { class: 'card' }, tabela([
          { t: 'Módulo', f: (m) => m.titulo },
          { t: 'Vale para', f: (m) => (m.produto_id ? badge(`Produto: ${m.produto_nome || m.produto_id}`, 'b-pri') : badge('Todos os produtos')) },
          { t: 'Ordens concluídas', f: (m) => `${m.amostras} de ${m.minimo}` }], faltam),
        h('p', { class: 'muted small' }, 'Para calibrar um produto também é preciso ter pedidos de pelo menos 3 tamanhos diferentes.'))) : null);
  };
  await carregar();
}

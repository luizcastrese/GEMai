import { get, post } from './api.js';
import { h, avisoIA, badge, fmtData, modal, statusBadge, tentar } from './ui.js';

const ROT = {
  estrutura_processo: 'Estrutura de processo', analise_desvio: 'Análise de desvios', analise_gargalo: 'Possíveis gargalos',
  relatorio_gestor: 'Relatório do gestor', indicadores_sugeridos: 'Indicadores sugeridos', processos_semelhantes: 'Operações semelhantes',
};
export const rotuloTipo = (t) => ROT[t] || t;

// Corpo legível de uma análise textual (não-estrutura).
export function corpoAnalise(rec) {
  const c = rec.conteudo || {};
  return h('div', null, avisoIA(),
    h('p', null, c.resumo),
    (c.pontos_investigacao || []).length ? h('div', null, h('h3', null, 'Pontos para investigação'),
      h('ul', null, c.pontos_investigacao.map((p) => h('li', null, h('strong', null, p.titulo), ' — ', p.evidencia,
        p.hipotese ? h('div', { class: 'muted small' }, `Hipótese (não confirmada): ${p.hipotese}`) : null)))) : null,
    (c.indicadores_sugeridos || []).length ? h('div', null, h('h3', null, 'Indicadores sugeridos'),
      h('ul', null, c.indicadores_sugeridos.map((i) => h('li', null, i)))) : null,
    h('details', null, h('summary', { class: 'small muted' }, 'Evidências calculadas pelo sistema'),
      h('pre', { class: 'small tw' }, JSON.stringify(rec.evidencias, null, 2).slice(0, 6000))),
    h('p', { class: 'small muted' }, `Fonte: ${rec.provedor} · ${fmtData(rec.criada_em)} · `, statusBadge(rec.status)));
}

export function verRecomendacao(rec, aoMudar) {
  const corpo = rec.tipo === 'estrutura_processo'
    ? h('div', null, avisoIA(), h('p', null, 'Revise e aprove esta estrutura na tela de Implantação.'),
        h('a', { href: '#/implantacao' }, 'Abrir Implantação'))
    : corpoAnalise(rec);
  modal(`${rotuloTipo(rec.tipo)} — ${rec.titulo}`, corpo, { larga: true, acoes: (fechar) => [
    rec.status === 'pendente' && rec.tipo !== 'estrutura_processo' ? [
      h('button', { onclick: async () => { if (await tentar(() => post(`/recomendacoes/${rec.id}/rejeitar`), 'Sugestão rejeitada.')) { fechar(); aoMudar?.(); } } }, 'Rejeitar'),
      h('button', { class: 'pri', onclick: async () => { if (await tentar(() => post(`/recomendacoes/${rec.id}/aprovar`), 'Sugestão marcada como validada.')) { fechar(); aoMudar?.(); } } }, 'Validar (li e concordo)'),
    ] : null,
    h('button', { onclick: fechar }, 'Fechar')] });
}

export async function gerarAnalise(tipo, extra, aoMudar) {
  const rec = await tentar(() => post('/ia/analises', { tipo, ...extra }));
  if (rec) verRecomendacao(rec, aoMudar);
  return rec;
}
export { get, badge };

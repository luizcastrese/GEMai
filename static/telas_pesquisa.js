// Indicadores do piloto (para o TCC): calculados dos dados que o sistema já guarda, sem rastrear cliques nem dado pessoal.
import { baixar, get } from './api.js';
import { detalhes, fmtMin, fmtNum, h, kpi, montar, tabela } from './ui.js';

const pct = (v) => (v === null || v === undefined ? '—' : `${fmtNum(v, 1)}%`);

export async function pesquisa(el) {
  const d = await get('/pesquisa/indicadores');
  const u = d.uso, m = d.medicao, px = d.previsto_x_realizado, a = d.atividades;
  montar(el, h('h1', null, 'Indicadores do piloto'),
    h('p', { class: 'muted' }, 'Agregados desta empresa, calculados dos registros do próprio sistema (sem rastrear uso e sem dado pessoal).'),
    h('h2', null, 'Uso (QP3)'),
    h('div', { class: 'grid g4' }, kpi('Do cadastro ao primeiro plano', u.minutos_do_cadastro_ao_primeiro_plano === null ? '—' : fmtMin(u.minutos_do_cadastro_ao_primeiro_plano)),
      kpi('Planos', u.planos), kpi('Planos completos', u.planos_completos), kpi('Planos que viraram pedido', u.planos_com_pedido)),
    h('h2', null, 'Medição'),
    h('div', { class: 'grid g4' }, kpi('Pedidos abertos', m.pedidos_abertos), kpi('Pedidos medidos', m.pedidos_medidos),
      kpi('Fração medida', m.fracao_medida === null ? '—' : pct(m.fracao_medida * 100)),
      kpi('Medidos no total / passo a passo', `${m.formas.total || 0} / ${m.formas.passo_a_passo || 0}`)),
    h('h2', null, 'Previsto × realizado (QP2)'),
    h('div', { class: 'grid g4' }, kpi('Erro típico sem calibração', pct(px.erro_tipico_sem_calibracao_pct)), kpi('Pedidos', px.pedidos_sem_calibracao),
      kpi('Erro típico com calibração', pct(px.erro_tipico_com_calibracao_pct)), kpi('Pedidos', px.pedidos_com_calibracao)),
    px.pedidos.length ? h('div', { class: 'card' }, tabela([{ t: 'Pedido', f: (x) => x.ordem_id }, { t: 'Previsto', f: (x) => fmtMin(x.previsto_min) },
      { t: 'Realizado', f: (x) => fmtMin(x.realizado_min) }, { t: 'Desvio', f: (x) => pct(x.desvio_pct) }, { t: 'Calibrado', f: (x) => (x.calibrado ? 'sim' : 'não') },
      { t: 'Medido', f: (x) => (x.forma === 'total' ? 'no total' : 'passo a passo') }], px.pedidos),
      h('button', { onclick: () => baixar('/pesquisa/pedidos.csv', 'pedidos-previsto-realizado.csv') }, 'Baixar planilha (CSV)')) : null,
    h('h2', null, 'Atividades delimitadas pela IA (QP4)'),
    h('div', { class: 'grid g4' }, kpi('Validadas sem edição', a.ia_validadas_sem_edicao || 0), kpi('Validadas com edição', a.ia_validadas_com_edicao || 0),
      kpi('Rejeitadas', a.ia_rejeitadas || 0), kpi('Criadas por pessoa', a.criadas_por_pessoa || 0)),
    detalhes('Método', h('p', { class: 'small muted' }, d.metodo)));
}

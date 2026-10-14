import { get, qs } from './api.js';
import { estado } from './estado.js';
import { fonteBadge, barras, fmtDia, fmtMin, fmtNum, fmtPct, h, kpi, montar, statusBadge, tabela, tentar } from './ui.js';
import { gerarAnalise } from './ia_view.js';

const iso = (d) => d.toISOString().slice(0, 10);

// ---------------------------------------------------------------- Painel (seção 13)
export async function painel(el) {
  const ate = new Date(); const de = new Date(Date.now() - 29 * 864e5);
  const f = { de: iso(de), ate: iso(ate), todas: false };
  const area = h('div');
  const ctl = h('div', { class: 'card row' },
    h('div', null, h('label', null, 'De'), h('input', { type: 'date', value: f.de, onchange: (e) => { f.de = e.target.value; carregar(); } })),
    h('div', null, h('label', null, 'Até'), h('input', { type: 'date', value: f.ate, onchange: (e) => { f.ate = e.target.value; carregar(); } })),
    h('div', null, h('label', null, 'Abrangência'), h('select', { onchange: (e) => { f.todas = e.target.value === 'todas'; carregar(); } },
      h('option', { value: 'atual' }, 'Unidade selecionada'), h('option', { value: 'todas' }, 'Todas as minhas unidades'))),
    h('button', { class: 'ia', onclick: () => gerarAnalise('relatorio_gestor', { unidade_id: estado.unidadeId, de: f.de, ate: f.ate }) }, 'Relatório em linguagem simples (IA)'),
    h('button', { class: 'ia', onclick: () => gerarAnalise('analise_gargalo', { unidade_id: estado.unidadeId, de: f.de, ate: f.ate }) }, 'Possíveis gargalos (IA)'));
  montar(el, h('h1', null, 'Análises completas'), ctl, area);

  async function carregar() {
    const d = await tentar(() => get(`/dashboard${qs({ unidade_id: f.todas ? '' : estado.unidadeId, de: f.de, ate: f.ate })}`));
    if (!d) return;
    if (d.vazio) return montar(area, h('p', { class: 'muted' }, 'Sem unidades.'));
    const eff = d.planejado_x_realizado.eficiencia_pct;
    montar(area,
      h('div', { class: 'grid g4' },
        kpi('Ordens em aberto', d.ordens.em_producao),
        kpi('Ordens atrasadas', d.ordens_atrasadas.length, d.ordens_atrasadas.length ? 'bad' : 'good'),
        kpi('Eficiência (previsto ÷ realizado)', fmtPct(eff), eff !== null && eff < 90 ? 'bad' : ''),
        kpi('Paradas no período', fmtMin(d.paradas.total_min)),
        kpi('Retrabalho (% do tempo)', fmtPct(d.retrabalho.pct_do_tempo_de_trabalho)),
        kpi('Refugo', fmtPct(d.qualidade.refugo_pct)),
        kpi('Produtividade (un/h)', fmtNum(d.produtividade.un_por_hora)),
        kpi('Concluídas no período', `${d.ordens.concluidas_no_periodo}${d.ordens.concluidas_com_atraso_no_periodo ? ` (${d.ordens.concluidas_com_atraso_no_periodo} com atraso)` : ''}`)),
      h('div', { class: 'grid g2' },
        h('div', { class: 'card' }, h('h3', null, 'Ordens atrasadas'), tabela([
          { t: 'Ordem', f: (o) => h('a', { href: `#/ordens/${o.id}` }, o.numero) }, { t: 'Cliente', f: (o) => o.cliente },
          { t: 'Prazo', f: (o) => fmtDia(o.prazo) }, { t: 'Atraso', f: (o) => `${o.dias_atraso} dia(s)` }, { t: 'Status', f: (o) => statusBadge(o.status) }],
          d.ordens_atrasadas, 'Nenhuma ordem atrasada.')),
        h('div', { class: 'card' }, h('h3', null, 'Planejado × realizado: maiores desvios'), tabela([
          { t: 'Etapa › operação', f: (x) => `${x.etapa} › ${x.operacao}` }, { t: 'Previsto', f: (x) => fmtMin(x.estimado_min) },
          { t: 'Realizado', f: (x) => fmtMin(x.realizado_min) }, { t: 'Desvio', f: (x) => h('span', { class: x.desvio_min > 0 ? 'badge b-err' : 'badge b-ok' }, fmtPct(x.desvio_pct)) }],
          d.planejado_x_realizado.maiores_desvios, 'Sem operações concluídas com estimativa no período.')),
        h('div', { class: 'card' }, h('h3', null, 'Quão bem o tempo planejado acerta?'), tabela([
          { t: 'Fonte do planejado', f: (x) => fonteBadge(x.fonte) }, { t: 'Operações', f: (x) => x.operacoes },
          { t: 'Desvio médio', f: (x) => fmtPct(x.desvio_medio_pct) }, { t: 'Erro absoluto médio', f: (x) => fmtPct(x.erro_absoluto_medio_pct) }], d.acuracia_por_fonte, 'Conclua operações com estimativa para medir a acurácia.'),
          h('p', { class: 'muted small' }, 'Desvio médio positivo = o real demorou mais que o planejado. Com mais ordens aprovadas, o histórico passa a substituir o modelo da IA.')),
        h('div', { class: 'card' }, h('h3', null, 'Gargalos (espera e ocupação por etapa)'), tabela([
          { t: 'Etapa', f: (x) => x.etapa }, { t: 'Fila', f: (x) => fmtMin(x.espera_fila_min) },
          { t: 'Espera reg.', f: (x) => fmtMin(x.espera_registrada_min) }, { t: 'Ocupação', f: (x) => fmtMin(x.ocupacao_min) }], d.gargalos),
          h('p', { class: 'muted small' }, 'Fila = tempo entre o fim da operação anterior e o início desta. Indica onde investigar; não é prova de gargalo.')),
        h('div', { class: 'card' }, h('h3', null, 'Paradas por motivo'), tabela([
          { t: 'Motivo', f: (x) => x.causa }, { t: 'Ocorrências', f: (x) => x.ocorrencias }, { t: 'Duração', f: (x) => fmtMin(x.duracao_min) }], d.paradas.por_causa, 'Nenhuma parada registrada.')),
        h('div', { class: 'card' }, h('h3', null, 'Utilização das máquinas'), tabela([
          { t: 'Recurso', f: (x) => x.recurso }, { t: 'Usado', f: (x) => fmtMin(x.usado_min) }, { t: 'Disponível', f: (x) => fmtMin(x.disponivel_min) },
          { t: '%', f: (x) => h('div', { style: undefined }, fmtPct(x.utilizacao_pct), (() => { const b = h('div', { class: 'bar' }, h('i')); b.firstChild.style.width = `${Math.min(x.utilizacao_pct || 0, 100)}%`; return b; })()) }],
          d.utilizacao_maquinas, 'Cadastre recursos e registre apontamentos com recurso.')),
        h('div', { class: 'card' }, h('h3', null, 'Tendência semanal'),
          d.tendencia_semanal.length ? h('div', null,
            h('div', { class: 'small muted' }, 'Eficiência (%)'), barras(d.tendencia_semanal.map((s) => fmtDia(s.semana).slice(0, 5)), d.tendencia_semanal.map((s) => s.eficiencia_pct), { sufixo: '' }),
            h('div', { class: 'small muted' }, 'Paradas (min)'), barras(d.tendencia_semanal.map((s) => fmtDia(s.semana).slice(0, 5)), d.tendencia_semanal.map((s) => s.paradas_min), { cor: '#b26a00' }))
            : h('p', { class: 'muted' }, 'Sem dados no período.'))),
    );
  }
  await carregar();
}

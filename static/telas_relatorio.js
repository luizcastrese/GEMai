import { baixar, get, qs } from './api.js';
import { badge, fmtMin, fmtNum, h, montar, tabela, tentar } from './ui.js';

const sinal = (v) => (v === null || v === undefined ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${fmtNum(Math.abs(v))}%`);
const tomDesvio = (v) => (v === null || v === undefined ? '' : v > 10 ? 'b-warn' : v < -10 ? 'b-ok' : '');
const min = (v) => (v === null || v === undefined ? '—' : fmtMin(v));
const LIMITE_TELA = 100;
// Em tela estreita a tabela rola por dentro do cartão em vez de espremer as colunas.
const larga = (t) => { const tb = t.querySelector('table'); if (tb) tb.style.minWidth = '720px'; return t; };

export async function relatorio(el) {
  const produtos = (await get('/produtos?ativo=true')).filter((p) => p.tipo === 'produto');
  const f = {
    produto: h('select', null, h('option', { value: '' }, 'Todos os produtos'), produtos.map((p) => h('option', { value: p.id }, p.nome))),
    desde: h('input', { type: 'date' }), ate: h('input', { type: 'date' }),
  };
  const saida = h('div');
  const filtros = () => ({ produto_id: f.produto.value, desde: f.desde.value, ate: f.ate.value });

  const mostrar = (r) => {
    const q = filtros();
    if (!r.linhas.length) {
      return montar(saida, h('div', { class: 'card' }, h('p', { class: 'muted' }, 'Nenhum plano neste filtro. Gere planos de trabalho (e, depois de executar, apontamentos) para ver o desempenho aqui.')));
    }
    const concluidas = r.resumo.reduce((n, s) => n + s.ordens_concluidas, 0);
    montar(saida,
      h('div', { class: 'card' },
        h('div', { class: 'inline noprint' },
          h('button', { class: 'pri', onclick: () => tentar(() => baixar(`/relatorios/desempenho.csv${qs({ ...q, tipo: 'resumo' })}`, 'desempenho-resumo.csv')) }, 'Baixar resumo por variante (Excel)'),
          h('button', { onclick: () => tentar(() => baixar(`/relatorios/desempenho.csv${qs({ ...q, tipo: 'detalhe' })}`, 'desempenho-por-pedido.csv')) }, 'Baixar detalhe por pedido (Excel)')),
        h('p', { class: 'muted small' }, `${r.linhas.length} pedido(s) · ${concluidas} concluído(s) com tempo real. Desvio positivo = demorou mais que o previsto. `
          + 'Previsto e realizado só são comparados em pedidos concluídos e com todos os passos previstos.')),
      h('h2', null, 'Resumo por variante'),
      h('div', { class: 'card' }, larga(tabela([
        { t: 'Produto', f: (s) => s.produto },
        { t: 'Variante', f: (s) => s.variante || h('span', { class: 'muted' }, 'sem especificação') },
        { t: 'Pedidos', f: (s) => s.planos },
        { t: 'Concluídos', f: (s) => s.ordens_concluidas },
        { t: 'Previsto / un. (planos)', f: (s) => min(s.previsto_por_unidade_planos_min) },
        { t: 'Previsto / un. (concluídos)', f: (s) => min(s.previsto_por_unidade_concluidas_min) },
        { t: 'Realizado / un.', f: (s) => min(s.realizado_por_unidade_min) },
        { t: 'Desvio', f: (s) => (s.desvio_pct === null ? '—' : badge(sinal(s.desvio_pct), tomDesvio(s.desvio_pct))) }], r.resumo))),
      h('h2', null, 'Pedidos'),
      h('div', { class: 'card' }, larga(tabela([
        { t: 'Plano', f: (l) => h('a', { href: `#/planos/${l.plano_id}`, title: l.plano }, `Plano ${l.plano_id}`) },
        { t: 'Variante', f: (l) => l.variante || '—' },
        { t: 'Qtd.', f: (l) => fmtNum(l.quantidade, 2) },
        { t: 'Previsto / un.', f: (l) => min(l.previsto_por_unidade_min) },
        { t: 'Realizado / un.', f: (l) => min(l.realizado_por_unidade_min) },
        { t: 'Desvio', f: (l) => (l.desvio_pct === null ? '—' : badge(sinal(l.desvio_pct), tomDesvio(l.desvio_pct))) },
        { t: 'Ordem', f: (l) => l.ordem_numero || '—' }], r.linhas.slice(0, LIMITE_TELA))),
      r.linhas.length > LIMITE_TELA ? h('p', { class: 'muted small' }, `Mostrando os ${LIMITE_TELA} mais recentes. A planilha traz todos.`) : null));
  };

  const carregar = async () => {
    const r = await tentar(() => get(`/relatorios/desempenho${qs(filtros())}`));
    if (r) mostrar(r);
  };
  montar(el, h('h1', null, 'Relatório de desempenho'),
    h('p', { class: 'muted' }, 'Veja, para cada produto e variante (tamanho, tipo…), quanto tempo o sistema previu e quanto levou de verdade. Baixe a planilha para analisar ou guardar.'),
    h('div', { class: 'card' }, h('div', { class: 'row' },
      h('div', null, h('label', null, 'Produto'), f.produto), h('div', null, h('label', null, 'De'), f.desde), h('div', null, h('label', null, 'Até'), f.ate),
      h('button', { class: 'pri', onclick: carregar }, 'Ver relatório'))), saida);
  await carregar();
}

import { get, patch, post, qs } from './api.js';
import { estado, unidadeAtual } from './estado.js';
import { fonteBadge, barras, fmtDia, fmtMin, fmtNum, fmtPct, formulario, h, kpi, limpar, montar, statusBadge, tabela, tentar, toast, avisoIA, badge, confirmar } from './ui.js';
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
  montar(el, h('h1', null, 'Painel do gestor'), ctl, area);

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
      d.alertas_ergonomia.length ? h('div', { class: 'card' }, h('h3', null, 'Operações que merecem avaliação ergonômica'),
        h('div', { class: 'aviso' }, 'Sinalização automática a partir dos dados informados. Não é avaliação ergonômica: use método apropriado e profissional competente.'),
        tabela([{ t: 'Processo › etapa › operação', f: (x) => `${x.processo} › ${x.etapa} › ${x.operacao}` },
          { t: 'Fatores', f: (x) => Object.entries(x.ergonomia).map(([k, v]) => `${k.replace('_', ' ')}: ${v}`).join(' · ') }], d.alertas_ergonomia)) : null);
  }
  await carregar();
}

// ---------------------------------------------------------------- Implantação (telas 1–3)
export async function implantacao(el) {
  const u = unidadeAtual();
  if (!u) return montar(el, h('p', null, 'Nenhuma unidade disponível.'));
  let aba = 'descricao';
  const area = h('div');
  const abas = h('div', { class: 'tabs' });
  const desenhar = async () => {
    montar(abas, [['descricao', '1. Descrição da empresa'], ['diagnostico', '2. Diagnóstico inteligente'], ['estrutura', '3. Estrutura do processo']].map(([k, r]) =>
      h('button', { class: aba === k ? 'on' : '', onclick: () => { aba = k; desenhar(); } }, r)));
    montar(area, h('p', { class: 'muted' }, 'Carregando…'));
    await ({ descricao: telaDescricao, diagnostico: telaDiagnostico, estrutura: telaEstrutura }[aba])(area, u, (a) => { aba = a; desenhar(); });
  };
  montar(el, h('h1', null, `Implantação — ${u.nome}`),
    h('p', { class: 'muted' }, 'Descreva a operação com suas palavras; a IA sugere perguntas e uma estrutura, e você valida antes de qualquer coisa ser criada.'), abas, area);
  await desenhar();
}

async function telaDescricao(area, u, ir) {
  const fresh = await get(`/unidades/${u.id}`);
  const f = formulario([
    { k: 'descricao_operacao', rotulo: 'Descrição da operação', tipo: 'textarea', ajuda: 'Ex.: Recebemos insumos, preparamos, produzimos e entregamos.' },
    { k: 'objetivo', rotulo: 'Objetivo do sistema', tipo: 'textarea', ajuda: 'Ex.: Reduzir tempo e padronizar produção.' },
    { k: 'principais_problemas', rotulo: 'Principais problemas', tipo: 'textarea', ajuda: 'Ex.: Atrasos, retrabalho e falta de histórico.' },
    { k: 'informacoes_disponiveis', rotulo: 'Informações já disponíveis', tipo: 'textarea', ajuda: 'Ex.: Planilhas, sistema atual, registros.' }], fresh);
  montar(area, h('div', { class: 'card' }, f.el, h('p', null,
    h('button', { class: 'pri', onclick: async () => { const r = await tentar(() => patch(`/unidades/${u.id}`, f.valores()), 'Descrição salva.'); if (r) { Object.assign(u, r); ir('diagnostico'); } } }, 'Salvar e continuar'))));
}

async function telaDiagnostico(area, u) {
  const render = async () => {
    const qs_ = await get(`/unidades/${u.id}/diagnostico`);
    const grupos = {};
    qs_.forEach((q) => (grupos[q.grupo] ||= []).push(q));
    montar(area,
      h('div', { class: 'card inline' },
        h('button', { class: 'ia', onclick: async () => {
          const r = await tentar(() => post(`/unidades/${u.id}/diagnostico/perguntas/gerar`));
          if (r) { toast(`${r.perguntas.length} nova(s) pergunta(s) (${r.provedor}).`); if (r.aviso) toast(r.aviso, true); render(); }
        } }, qs_.length ? 'Gerar perguntas de aprofundamento' : 'Gerar perguntas com IA'),
        h('span', { class: 'muted small' }, 'As perguntas se adaptam às respostas já dadas. Responda o que souber; o restante pode ficar em branco.')),
      qs_.length ? null : h('p', { class: 'muted' }, 'Ainda não há perguntas. Preencha a descrição (passo 1) e gere as perguntas.'),
      Object.entries(grupos).map(([g, itens]) => h('div', { class: 'card' }, h('h3', null, g), itens.map((q) => {
        const ta = h('textarea', { value: q.resposta || '' });
        return h('div', null, h('label', null, q.texto), ta, h('div', { class: 'inline' },
          h('button', { class: 'sm', onclick: async () => { if (await tentar(() => patch(`/diagnostico/perguntas/${q.id}`, { resposta: ta.value }), 'Resposta salva.')) q.resposta = ta.value; } }, 'Salvar resposta'),
          q.origem !== 'heuristica' ? badge('IA', 'b-ia') : null));
      }))));
  };
  await render();
}

async function telaEstrutura(area, u, ir) {
  const pend = await get(`/recomendacoes${qs({ unidade_id: u.id, tipo: 'estrutura_processo', status: 'pendente' })}`);
  const geradora = h('div', { class: 'card inline' },
    h('button', { class: 'ia', onclick: async () => { const r = await tentar(() => post(`/unidades/${u.id}/diagnostico/estruturar`)); if (r) ir('estrutura'); } },
      pend.length ? 'Gerar nova proposta' : 'Gerar estrutura com IA'),
    h('span', { class: 'muted small' }, 'Nada é criado até você revisar e aprovar.'));
  if (!pend.length) return montar(area, geradora, h('p', { class: 'muted' }, 'Sem proposta pendente. Gere uma a partir do diagnóstico.'));
  const rec = pend[0];
  const c = structuredClone(rec.conteudo);
  const editor = h('div');
  const redesenhar = () => montar(editor,
    c.processos.map((p, pi) => h('div', { class: 'card' },
      h('div', { class: 'row' }, h('div', null, h('label', null, 'Processo'), h('input', { value: p.nome, onchange: (e) => { p.nome = e.target.value; } })),
        h('div', null, h('label', null, 'Macroprocesso'), h('input', { value: p.macroprocesso, onchange: (e) => { p.macroprocesso = e.target.value; } }))),
      h('h3', null, 'Etapas e operações'),
      p.etapas.map((e, ei) => h('div', { class: 'etapa' },
        h('div', { class: 'row' },
          h('div', null, h('label', null, `Etapa ${ei + 1}`), h('input', { value: e.nome, onchange: (ev) => { e.nome = ev.target.value; } })),
          h('button', { class: 'sm', disabled: ei === 0, onclick: () => { [p.etapas[ei - 1], p.etapas[ei]] = [p.etapas[ei], p.etapas[ei - 1]]; redesenhar(); } }, '↑'),
          h('button', { class: 'sm', disabled: ei === p.etapas.length - 1, onclick: () => { [p.etapas[ei + 1], p.etapas[ei]] = [p.etapas[ei], p.etapas[ei + 1]]; redesenhar(); } }, '↓'),
          h('button', { class: 'sm dng', onclick: () => { p.etapas.splice(ei, 1); redesenhar(); } }, 'Remover')),
        e.operacoes.map((o, oi) => h('div', { class: 'op row' },
          h('div', null, h('label', null, 'Operação'), h('input', { value: o.nome, onchange: (ev) => { o.nome = ev.target.value; } })),
          h('div', null, h('label', null, 'Recurso padrão (opcional)'), h('input', { value: o.recurso || '', onchange: (ev) => { o.recurso = ev.target.value || null; } })),
          h('div', { class: 'small muted' }, `Parâmetros a medir: ${(o.parametros || []).map((x) => x.nome).join(', ') || '—'}`),
          h('button', { class: 'sm dng', onclick: () => { e.operacoes.splice(oi, 1); redesenhar(); } }, 'Remover'))),
        h('button', { class: 'sm', onclick: () => { e.operacoes.push({ nome: 'Nova operação', descricao: '', recurso: null, formula_tipo: 'linear', unidade_medida: 'un', dados_medidos: ['tempo', 'quantidade'], parametros: [{ nome: 'tempo_preparacao_min', unidade: 'min', valor: null, justificativa: '' }, { nome: 'tempo_unitario_min', unidade: 'min/un', valor: null, justificativa: '' }] }); redesenhar(); } }, '+ Operação'))),
      h('button', { onclick: () => { p.etapas.push({ nome: 'Nova etapa', descricao: '', entradas: [], saidas: [], opcional: false, condicao: '', operacoes: [{ nome: 'Nova etapa', descricao: '', recurso: null, formula_tipo: 'linear', unidade_medida: 'un', dados_medidos: ['tempo', 'quantidade'], parametros: [{ nome: 'tempo_preparacao_min', unidade: 'min', valor: null, justificativa: '' }, { nome: 'tempo_unitario_min', unidade: 'min/un', valor: null, justificativa: '' }] }] }); redesenhar(); } }, '+ Etapa'))),
    h('div', { class: 'grid g2' },
      h('div', { class: 'card' }, h('h3', null, 'Recursos identificados'),
        c.recursos.length ? c.recursos.map((r, i) => h('div', { class: 'inline' }, `${r.nome} (${r.tipo})`, h('button', { class: 'sm dng', onclick: () => { c.recursos.splice(i, 1); redesenhar(); } }, '✕'))) : h('p', { class: 'muted' }, 'Nenhum.')),
      h('div', { class: 'card' }, h('h3', null, 'Materiais identificados'),
        c.materiais.length ? c.materiais.map((m, i) => h('div', { class: 'inline' }, m.nome, h('button', { class: 'sm dng', onclick: () => { c.materiais.splice(i, 1); redesenhar(); } }, '✕'))) : h('p', { class: 'muted' }, 'Nenhum.'))),
    c.etapas_possivelmente_omitidas.length ? h('div', { class: 'card' }, h('h3', null, 'Etapas que talvez não tenham sido informadas'),
      c.etapas_possivelmente_omitidas.map((n) => h('div', { class: 'inline' }, n, h('button', { class: 'sm', onclick: () => {
        c.processos[0]?.etapas.push({ nome: n, descricao: '', entradas: [], saidas: [], opcional: false, condicao: '', operacoes: [{ nome: n, descricao: '', recurso: null, formula_tipo: 'linear', unidade_medida: 'un', dados_medidos: ['tempo', 'quantidade'], parametros: [] }] });
        c.etapas_possivelmente_omitidas = c.etapas_possivelmente_omitidas.filter((x) => x !== n); redesenhar(); } }, 'Adicionar ao processo')))) : null,
    c.perguntas_pendentes.length ? h('div', { class: 'card' }, h('h3', null, 'Ainda por responder'), h('ul', null, c.perguntas_pendentes.map((x) => h('li', null, x)))) : null,
    c.indicadores_sugeridos.length ? h('div', { class: 'card' }, h('h3', null, 'Indicadores sugeridos'), h('ul', null, c.indicadores_sugeridos.map((x) => h('li', null, x)))) : null);
  redesenhar();
  const aprovar = async () => {
    if (!c.processos.length || !c.processos.some((p) => p.etapas.length)) return toast('Inclua ao menos um processo com etapas.', true);
    if (!await tentar(() => patch(`/recomendacoes/${rec.id}`, { conteudo: c }))) return;
    const r = await tentar(() => post(`/recomendacoes/${rec.id}/aprovar`, { observacao: 'Revisada no assistente de implantação.' }));
    if (r) { toast('Processo criado como RASCUNHO. Defina os parâmetros e publique.'); location.hash = '#/processos'; }
  };
  montar(area, geradora, avisoIA(rec.justificativa), h('p', { class: 'muted small' }, `Fonte: ${rec.provedor}. ${c.observacoes || ''}`), editor,
    h('div', { class: 'card inline' },
      h('button', { class: 'pri', onclick: aprovar }, 'Aprovar e criar processo (rascunho)'),
      h('button', { class: 'dng', onclick: () => confirmar('Rejeitar esta proposta?', async () => { if (await tentar(() => post(`/recomendacoes/${rec.id}/rejeitar`), 'Proposta rejeitada.')) ir('estrutura'); }) }, 'Rejeitar')));
}

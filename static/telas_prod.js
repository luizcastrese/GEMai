import { get, patch, post, qs } from './api.js';
import { estado, ehGestor } from './estado.js';
import { badge, confirmar, fmtData, fmtDia, fmtMin, fmtNum, fonteBadge, formulario, h, kpi, modal, montar, statusBadge, tabela, tentar, toast } from './ui.js';
import { gerarAnalise } from './ia_view.js';

const TIPO_APT = { preparacao: 'Preparação', execucao: 'Execução', espera: 'Espera', retrabalho: 'Retrabalho' };
const hojeISO = () => new Date().toISOString().slice(0, 10);

// ---------------------------------------------------------------- lista / nova ordem
export async function ordens(el) {
  const filtro = { status: '', q: '' };
  const area = h('div');
  const carregar = async () => {
    const os = await get(`/ordens${qs({ unidade_id: estado.unidadeId, status: filtro.status, q: filtro.q })}`);
    montar(area, h('div', { class: 'card' }, tabela([
      { t: 'Ordem', f: (o) => h('a', { href: `#/ordens/${o.id}` }, o.numero) }, { t: 'Cliente / demanda', f: (o) => o.cliente || o.descricao },
      { t: 'Qtd', f: (o) => fmtNum(o.quantidade, 2) }, { t: 'Prazo', f: (o) => h('span', null, fmtDia(o.prazo), o.atrasada ? [' ', badge('Atrasada', 'b-err')] : '') },
      { t: 'Estimado', f: (o) => (o.tempo_estimado_min === null ? badge('Sem base', 'b-warn') : fmtMin(o.tempo_estimado_min) + (o.estimativa_parcial ? ' *' : '')) },
      { t: 'Status', f: (o) => statusBadge(o.status) }], os, 'Nenhuma ordem.'),
    h('p', { class: 'muted small' }, '* estimativa parcial: há operações sem base de tempo.')));
  };
  montar(el, h('div', { class: 'top' }, h('h1', null, 'Ordens de produção'), h('button', { class: 'pri', onclick: () => novaOrdem(el) }, '+ Nova ordem')),
    h('div', { class: 'card row' },
      h('div', null, h('label', null, 'Status'), h('select', { onchange: (e) => { filtro.status = e.target.value; carregar(); } },
        [['', 'Todos'], ['planejada', 'Planejada'], ['liberada,em_producao,parada', 'Abertas'], ['concluida', 'Concluída'], ['cancelada', 'Cancelada']].map(([v, r]) => h('option', { value: v }, r)))),
      h('div', null, h('label', null, 'Buscar'), h('input', { placeholder: 'número, cliente ou descrição', onchange: (e) => { filtro.q = e.target.value; carregar(); } }))), area);
  await carregar();
}

async function novaOrdem(el) {
  const [procs, produtos] = await Promise.all([get(`/processos${qs({ unidade_id: estado.unidadeId, status: 'ativo' })}`), get('/produtos?ativo=true')]);
  if (!procs.length) return toast('Não há processo ativo. Publique um processo antes de criar ordens.', true);
  const f = formulario([
    { k: 'processo_id', rotulo: 'Processo (roteiro)', tipo: 'select', num: true, opcoes: procs.map((p) => [p.id, `${p.nome} (v${p.versao})`]) },
    { k: 'produto_id', rotulo: 'Produto / serviço (opcional)', tipo: 'select', num: true, opcoes: [['', '—'], ...produtos.map((p) => [p.id, p.nome])] },
    { k: 'descricao', rotulo: 'O que será realizado' }, { k: 'cliente', rotulo: 'Cliente ou demanda' },
    { k: 'quantidade', rotulo: 'Quantidade', tipo: 'number', padrao: 1, min: 0 }, { k: 'prazo', rotulo: 'Prazo', tipo: 'date', nulo: true },
    { k: 'observacoes', rotulo: 'Observações', tipo: 'textarea' }]);
  modal('Nova ordem', f.el, { acoes: (fechar) => [h('button', { onclick: fechar }, 'Cancelar'), h('button', { class: 'pri', onclick: async () => {
    const v = f.valores();
    if (!v.quantidade || v.quantidade <= 0) return toast('Informe uma quantidade maior que zero.', true);
    const r = await tentar(() => post('/ordens', { unidade_id: estado.unidadeId, ...v, prazo: v.prazo || null }), 'Ordem criada.');
    if (r) { fechar(); location.hash = `#/ordens/${r.id}`; }
  } }, 'Criar')] });
}

// ---------------------------------------------------------------- detalhe
export async function ordemDetalhe(el, id) {
  const gestor = ehGestor();
  const [o, apts, ocs, recursos] = await Promise.all([get(`/ordens/${id}`), get(`/apontamentos${qs({ ordem_id: id })}`),
    get(`/ocorrencias${qs({ ordem_id: id })}`), get(`/recursos${qs({ unidade_id: estado.unidadeId })}`)]);
  const recarregar = () => ordemDetalhe(el, id);
  const cmd = (fn, ok) => async () => { if (await tentar(fn, ok) !== undefined) recarregar(); };
  const nomeRec = (rid) => recursos.find((r) => r.id === rid)?.nome || '—';
  const aberta = ['liberada', 'em_producao', 'parada'].includes(o.status);

  const cab = h('div', { class: 'card' }, h('div', { class: 'top' },
    h('div', null, h('h1', null, o.numero), h('div', { class: 'inline' }, statusBadge(o.status), o.atrasada ? badge('Atrasada', 'b-err') : null,
      `${o.cliente || o.descricao || ''}`, `· qtd ${fmtNum(o.quantidade, 2)}`, `· prazo ${fmtDia(o.prazo)}`)),
    gestor ? h('div', { class: 'inline' },
      o.status === 'planejada' ? h('button', { class: 'pri', onclick: cmd(() => post(`/ordens/${id}/liberar`), 'Ordem liberada.') }, 'Liberar para produção') : null,
      ['liberada', 'em_producao'].includes(o.status) ? h('button', { class: 'pri', onclick: cmd(() => post(`/ordens/${id}/concluir`), 'Ordem concluída.') }, 'Concluir ordem') : null,
      !['concluida', 'cancelada'].includes(o.status) ? h('button', { class: 'dng', onclick: () => motivo('Cancelar ordem', 'Motivo do cancelamento', (m) => cmd(() => post(`/ordens/${id}/cancelar`, { motivo: m }), 'Ordem cancelada.')()) }, 'Cancelar') : null) : null),
    h('div', { class: 'grid g4' }, kpi('Tempo estimado', o.tempo_estimado_min === null ? 'Sem base' : fmtMin(o.tempo_estimado_min) + (o.estimativa_parcial ? ' *' : '')),
      kpi('Criada em', fmtData(o.criada_em)), kpi('Iniciada em', fmtData(o.iniciada_em)), kpi('Concluída em', fmtData(o.concluida_em))),
    o.observacoes ? h('p', { class: 'muted' }, o.observacoes) : null,
    o.cancelamento_motivo ? h('div', { class: 'aviso' }, `Cancelada: ${o.cancelamento_motivo}`) : null);

  const roteiro = h('div', { class: 'card' }, h('h2', null, 'Roteiro'), tabela([
    { t: '#', f: (x) => x.sequencia }, { t: 'Etapa › operação', f: (x) => `${x.etapa_nome} › ${x.nome}` }, { t: 'Recurso', f: (x) => nomeRec(x.recurso_id) },
    { t: 'Planejado', f: (x) => h('span', null, x.tempo_exec_est_min === null ? '—' : fmtMin((x.tempo_prep_est_min || 0) + x.tempo_exec_est_min), ' ', fonteBadge(x.fonte_estimativa),
      x.fonte_estimativa === 'modelo_ia' && !x.estimativa_validada ? [' ', badge('não validado', 'b-warn')] : null, x.fonte_estimativa === 'historico' ? ` (${x.amostras} amostras)` : '',
      x.detalhe_estimativa ? h('details', { class: 'small muted' }, h('summary', null, 'composição'), h('ul', null, x.detalhe_estimativa.map((e) => h('li', null, `${e.nome}: ${e.minutos === null ? 'falta dado' : fmtMin(e.minutos)}`)))) : null) },
    { t: 'Apontado', f: (x) => fmtMin(x.tempo_apontado_min) }, { t: 'Boas / refugo', f: (x) => `${fmtNum(x.qtd_boa, 2)} / ${fmtNum(x.qtd_refugo, 2)}` }, { t: 'Status', f: (x) => statusBadge(x.status) },
    { t: '', f: (x) => aberta ? h('div', { class: 'inline' },
      ['pendente', 'em_andamento'].includes(x.status) ? [
        o.status !== 'parada' ? h('button', { class: 'sm', onclick: () => iniciarApontamento(x, recarregar) }, '▶ Apontar') : null,
        h('button', { class: 'sm', onclick: cmd(() => post(`/ordens/${id}/operacoes/${x.id}/concluir`), 'Operação concluída.') }, '✓ Concluir'),
        gestor && x.opcional && x.status === 'pendente' ? h('button', { class: 'sm', onclick: cmd(() => post(`/ordens/${id}/operacoes/${x.id}/pular`)) }, 'Pular') : null] : null,
      gestor && ['concluida', 'pulada'].includes(x.status) ? h('button', { class: 'sm', onclick: cmd(() => post(`/ordens/${id}/operacoes/${x.id}/reabrir`)) }, 'Reabrir') : null) : '' }], o.operacoes));

  const secOc = h('div', { class: 'card' }, h('div', { class: 'top' }, h('h2', null, 'Ocorrências'),
    o.status !== 'cancelada' && o.status !== 'concluida' ? h('button', { onclick: () => novaOcorrencia(o, recursos, recarregar) }, '+ Registrar ocorrência') : null),
    tabela([{ t: 'Tipo', f: (c) => c.tipo }, { t: 'Causa', f: (c) => c.causa }, { t: 'Início', f: (c) => fmtData(c.inicio) },
      { t: 'Duração', f: (c) => (c.fim ? fmtMin(c.duracao_min) : badge('Em aberto', 'b-warn')) }, { t: 'Descrição', f: (c) => c.descricao },
      { t: '', f: (c) => (c.fim ? '' : h('button', { class: 'sm', onclick: cmd(() => post(`/ocorrencias/${c.id}/fechar`), 'Ocorrência encerrada.') }, 'Encerrar')) }], ocs, 'Nenhuma ocorrência.'));

  const secApt = h('div', { class: 'card' }, h('h2', null, 'Apontamentos'), tabela([
    { t: 'Operação', f: (a) => a.operacao_nome }, { t: 'Tipo', f: (a) => TIPO_APT[a.tipo] }, { t: 'Início', f: (a) => fmtData(a.inicio) },
    { t: 'Duração', f: (a) => (a.fim ? fmtMin(a.duracao_min) : badge('Em andamento', 'b-pri')) }, { t: 'Boas / refugo', f: (a) => `${fmtNum(a.quantidade_boa, 2)} / ${fmtNum(a.quantidade_refugo, 2)}` },
    { t: 'Situação', f: (a) => statusBadge(a.status) },
    { t: '', f: (a) => gestor ? h('div', { class: 'inline' },
      a.fim && a.status === 'registrado' ? h('button', { class: 'sm', onclick: cmd(() => post(`/apontamentos/${a.id}/aprovar`), 'Aprovado.') }, 'Aprovar') : null,
      h('button', { class: 'sm dng', onclick: () => motivo('Anular apontamento', 'Motivo (mín. 5 caracteres)', (m) => cmd(() => post(`/apontamentos/${a.id}/anular`, { motivo: m }), 'Anulado.')()) }, 'Anular')) : '' }], apts, 'Nenhum apontamento.'),
    gestor && aberta ? h('p', null, h('button', { class: 'sm', onclick: () => apontamentoManual(o, recursos, recarregar) }, '+ Lançamento manual (retroativo)')) : null);

  const analise = h('div', { class: 'card' }, h('h2', null, 'Planejado × realizado'), h('p', { class: 'muted' }, 'Carregando…'));
  montar(el, cab, roteiro, secOc, secApt, gestor ? analise : null);
  if (gestor) analisar(analise, o);
}

async function analisar(alvo, o) {
  const a = await get(`/ordens/${o.id}/analise`);
  const r = a.resumo;
  montar(alvo, h('div', { class: 'top' }, h('h2', null, 'Planejado × realizado'),
    h('button', { class: 'ia', onclick: () => gerarAnalise('analise_desvio', { unidade_id: o.unidade_id, ordem_id: o.id }) }, 'Explicar desvios (IA)')),
    h('div', { class: 'grid g4' }, kpi('Estimado (ops. concluídas)', fmtMin(r.estimado_min)), kpi('Realizado', fmtMin(r.realizado_min)),
      kpi('Desvio', r.desvio_pct === null ? '—' : `${fmtNum(r.desvio_pct)}%`, r.desvio_min > 0 ? 'bad' : r.desvio_min < 0 ? 'good' : ''),
      kpi('Eficiência', r.eficiencia_pct === null ? '—' : `${fmtNum(r.eficiencia_pct)}%`),
      kpi('Retrabalho', fmtMin(r.retrabalho_min)), kpi('Espera registrada', fmtMin(r.espera_registrada_min)), kpi('Fila entre operações', fmtMin(r.espera_fila_min)), kpi('Paradas', fmtMin(r.paradas_min))),
    r.comparacao_parcial || r.operacoes_sem_estimativa ? h('div', { class: 'aviso' }, 'Comparação parcial: há operações sem estimativa ou ainda não concluídas.') : null,
    tabela([{ t: 'Operação', f: (m) => m.operacao }, { t: 'Planejado', f: (m) => h('span', null, fmtMin(m.estimado_min), ' ', fonteBadge(m.fonte_estimativa)) }, { t: 'Preparação', f: (m) => fmtMin(m.preparacao_min) },
      { t: 'Execução', f: (m) => fmtMin(m.execucao_min) }, { t: 'Retrabalho', f: (m) => fmtMin(m.retrabalho_min) }, { t: 'Desvio', f: (m) => (m.desvio_pct === null ? '—' : `${fmtNum(m.desvio_pct)}%`) }], a.operacoes));
}

function motivo(titulo, rotulo, aoConfirmar) {
  const f = formulario([{ k: 'm', rotulo, tipo: 'textarea' }]);
  modal(titulo, f.el, { acoes: (fechar) => [h('button', { onclick: fechar }, 'Voltar'), h('button', { class: 'pri', onclick: () => {
    const m = f.valores().m; if (m.length < 3) return toast('Informe o motivo.', true); fechar(); aoConfirmar(m);
  } }, 'Confirmar')] });
}

function novaOcorrencia(o, recursos, aoSalvar) {
  const f = formulario([
    { k: 'tipo', rotulo: 'Tipo', tipo: 'select', opcoes: [['parada', 'Parada'], ['retrabalho', 'Retrabalho'], ['falta_material', 'Falta de material'], ['ajuste', 'Ajuste'], ['qualidade', 'Qualidade'], ['outro', 'Outro']] },
    { k: 'causa', rotulo: 'Causa / motivo' }, { k: 'recurso_id', rotulo: 'Recurso afetado', tipo: 'select', num: true, opcoes: [['', '—'], ...recursos.filter((r) => r.ativo).map((r) => [r.id, r.nome])] },
    { k: 'descricao', rotulo: 'Descrição', tipo: 'textarea' }]);
  modal('Registrar ocorrência', h('div', null, f.el, h('p', { class: 'muted small' }, 'Paradas ficam abertas até serem encerradas e mudam o status da ordem para "Parada".')),
    { acoes: (fechar) => [h('button', { onclick: fechar }, 'Cancelar'), h('button', { class: 'pri', onclick: async () => {
      if (await tentar(() => post('/ocorrencias', { ordem_id: o.id, ...f.valores() }), 'Ocorrência registrada.')) { fechar(); aoSalvar(); }
    } }, 'Registrar')] });
}

function camposExtras(op, inicial = {}) {
  return formulario((op.campos_extras || []).map((c) => ({ k: c.nome, rotulo: `${c.nome}${c.unidade ? ` (${c.unidade})` : ''}${c.obrigatorio ? ' *' : ''}`,
    tipo: c.tipo === 'numero' ? 'number' : c.tipo === 'booleano' ? 'bool' : 'text', nulo: true })), inicial);
}
const limparExtras = (v) => Object.fromEntries(Object.entries(v).filter(([, x]) => x !== null && x !== ''));

async function iniciarApontamento(op, aoSalvar) {
  const f = formulario([{ k: 'tipo', rotulo: 'O que você vai fazer?', tipo: 'select', opcoes: Object.entries(TIPO_APT) }, { k: 'observacao', rotulo: 'Observação (opcional)' }]);
  modal(`Apontar — ${op.nome}`, f.el, { acoes: (fechar) => [h('button', { onclick: fechar }, 'Cancelar'), h('button', { class: 'pri', onclick: async () => {
    if (await tentar(() => post('/apontamentos/iniciar', { ordem_operacao_id: op.id, ...f.valores() }), 'Apontamento iniciado. Finalize em "Minha fila".')) { fechar(); aoSalvar(); }
  } }, 'Iniciar')] });
}

async function apontamentoManual(o, recursos, aoSalvar) {
  const pessoas = await get(`/pessoas${qs({ unidade_id: o.unidade_id, ativo: true })}`);
  const ops = o.operacoes.filter((x) => !['pulada'].includes(x.status));
  const f = formulario([
    { k: 'ordem_operacao_id', rotulo: 'Operação', tipo: 'select', num: true, opcoes: ops.map((x) => [x.id, `${x.sequencia}. ${x.nome}`]) },
    { k: 'tipo', rotulo: 'Tipo', tipo: 'select', opcoes: Object.entries(TIPO_APT) },
    { k: 'pessoa_id', rotulo: 'Operador', tipo: 'select', num: true, opcoes: [['', '—'], ...pessoas.map((p) => [p.id, p.nome])] },
    { k: 'recurso_id', rotulo: 'Recurso', tipo: 'select', num: true, opcoes: [['', '—'], ...recursos.filter((r) => r.ativo).map((r) => [r.id, r.nome])] },
    { k: 'inicio', rotulo: 'Início', tipo: 'datetime-local' }, { k: 'fim', rotulo: 'Fim', tipo: 'datetime-local' },
    { k: 'quantidade_boa', rotulo: 'Quantidade boa', tipo: 'number', padrao: 0 }, { k: 'quantidade_refugo', rotulo: 'Refugo', tipo: 'number', padrao: 0 }, { k: 'observacao', rotulo: 'Observação' }]);
  modal('Lançamento manual', f.el, { larga: true, acoes: (fechar) => [h('button', { onclick: fechar }, 'Cancelar'), h('button', { class: 'pri', onclick: async () => {
    const v = f.valores();
    if (!v.inicio || !v.fim) return toast('Informe início e fim.', true);
    const corpo = { ...v, inicio: new Date(v.inicio).toISOString(), fim: new Date(v.fim).toISOString(), quantidade_boa: v.quantidade_boa || 0, quantidade_refugo: v.quantidade_refugo || 0 };
    if (await tentar(() => post('/apontamentos', corpo), 'Lançamento registrado.')) { fechar(); aoSalvar(); }
  } }, 'Registrar')] });
}

// ---------------------------------------------------------------- aprovações
export async function aprovacoes(el) {
  const apts = (await get(`/apontamentos${qs({ status: 'registrado', abertos: false, limite: 200 })}`)).filter((a) => a.unidade_id === estado.unidadeId);
  const marcados = new Set();
  const caixa = (a) => h('input', { type: 'checkbox', 'aria-label': `Selecionar apontamento ${a.id}`, onchange: (e) => { e.target.checked ? marcados.add(a.id) : marcados.delete(a.id); } });
  montar(el, h('h1', null, 'Apontamentos a aprovar'),
    h('p', { class: 'muted' }, 'Somente apontamentos aprovados alimentam o histórico que melhora as estimativas. Rejeite o que estiver errado.'),
    h('div', { class: 'card' }, tabela([{ t: '', f: caixa }, { t: 'Ordem', f: (a) => a.ordem_numero }, { t: 'Operação', f: (a) => a.operacao_nome }, { t: 'Tipo', f: (a) => TIPO_APT[a.tipo] },
      { t: 'Início', f: (a) => fmtData(a.inicio) }, { t: 'Duração', f: (a) => fmtMin(a.duracao_min) }, { t: 'Boas / refugo', f: (a) => `${fmtNum(a.quantidade_boa, 2)} / ${fmtNum(a.quantidade_refugo, 2)}` },
      { t: '', f: (a) => h('button', { class: 'sm', onclick: async () => { if (await tentar(() => post(`/apontamentos/${a.id}/rejeitar`), 'Rejeitado.')) aprovacoes(el); } }, 'Rejeitar') }], apts, 'Nada pendente de aprovação.'),
      apts.length ? h('p', null, h('button', { class: 'pri', onclick: async () => {
        if (!marcados.size) return toast('Selecione ao menos um apontamento.', true);
        if (await tentar(() => post('/apontamentos/aprovar-lote', { ids: [...marcados] }), 'Aprovados.')) aprovacoes(el);
      } }, 'Aprovar selecionados')) : null));
}

// ---------------------------------------------------------------- fila do operador
export async function fila(el) {
  let timer = null;
  const area = h('div');
  const carregar = async () => {
    const [ops, abertos, recursos] = await Promise.all([get(`/operador/fila${qs({ unidade_id: estado.unidadeId })}`), get('/apontamentos/abertos'), get(`/recursos${qs({ unidade_id: estado.unidadeId, ativo: true })}`)]);
    const mapaOps = new Map(ops.map((x) => [x.id, x]));
    clearInterval(timer);
    const cronos = [];
    const blocoAbertos = abertos.map((a) => {
      const t = h('div', { class: 'timer' }, '00:00:00');
      cronos.push([t, new Date(a.inicio)]);
      const op = mapaOps.get(a.ordem_operacao_id);
      return h('div', { class: 'card fila-card' }, h('div', null, h('div', { class: 'muted small' }, `${a.ordem_numero} · ${TIPO_APT[a.tipo]}`), h('strong', null, a.operacao_nome), t),
        h('div', { class: 'btns' }, h('button', { class: 'pri', onclick: () => finalizar(a, op, carregar) }, '■ Finalizar')));
    });
    const tick = () => cronos.forEach(([t, ini]) => { const s = Math.max(0, Math.floor((Date.now() - ini) / 1000)); t.textContent = [Math.floor(s / 3600), Math.floor(s / 60) % 60, s % 60].map((n) => String(n).padStart(2, '0')).join(':'); });
    tick(); timer = setInterval(tick, 1000);
    const livres = ops.filter((x) => !abertos.some((a) => a.ordem_operacao_id === x.id));
    montar(area, blocoAbertos.length ? [h('h2', null, 'Em andamento'), blocoAbertos] : null,
      h('h2', null, 'Disponíveis para apontar'),
      livres.length ? livres.map((x) => h('div', { class: 'card fila-card' },
        h('div', null, h('div', { class: 'muted small' }, `${x.ordem_numero} · qtd ${fmtNum(x.qtd_planejada, 2)}`), h('strong', null, `${x.etapa_nome} › ${x.nome}`), ' ', statusBadge(x.status)),
        h('div', { class: 'btns inline' }, ['preparacao', 'execucao', 'retrabalho', 'espera'].map((t) =>
          h('button', { class: t === 'execucao' ? 'pri' : '', disabled: abertos.length > 0, onclick: async () => {
            if (await tentar(() => post('/apontamentos/iniciar', { ordem_operacao_id: x.id, tipo: t }), `${TIPO_APT[t]} iniciada.`)) carregar();
          } }, `▶ ${TIPO_APT[t]}`))))) : h('p', { class: 'muted' }, 'Nenhuma operação liberada.'),
      h('p', null, h('button', { onclick: () => ocorrenciaRapida(recursos, carregar) }, 'Registrar parada / ocorrência')));
  };
  montar(el, h('h1', null, 'Minha fila'), area);
  await carregar();
  return () => clearInterval(timer);
}

function finalizar(a, op, aoSalvar) {
  const ex = camposExtras(op || {});
  const f = formulario([{ k: 'quantidade_boa', rotulo: 'Quantidade boa', tipo: 'number', padrao: 0, min: 0 }, { k: 'quantidade_refugo', rotulo: 'Refugo / perda', tipo: 'number', padrao: 0, min: 0 }, { k: 'observacao', rotulo: 'Observação' }]);
  const semQtd = a.tipo === 'preparacao' || a.tipo === 'espera';
  modal(`Finalizar — ${a.operacao_nome}`, h('div', null, semQtd ? h('p', { class: 'muted' }, 'Preparação e espera não levam quantidade.') : f.el, ex.el), { acoes: (fechar) => [h('button', { onclick: fechar }, 'Voltar'),
    h('button', { class: 'pri', onclick: async () => {
      const v = f.valores();
      const corpo = { quantidade_boa: semQtd ? 0 : v.quantidade_boa || 0, quantidade_refugo: semQtd ? 0 : v.quantidade_refugo || 0, observacao: v.observacao, dados_extras: limparExtras(ex.valores()) };
      if (await tentar(() => post(`/apontamentos/${a.id}/finalizar`, corpo), 'Apontamento finalizado.')) { fechar(); aoSalvar(); }
    } }, 'Finalizar')] });
}

async function ocorrenciaRapida(recursos, aoSalvar) {
  const ordensAbertas = await get(`/ordens${qs({ unidade_id: estado.unidadeId, status: 'liberada,em_producao,parada' })}`);
  const f = formulario([
    { k: 'ordem_id', rotulo: 'Ordem afetada', tipo: 'select', num: true, opcoes: [['', 'Nenhuma (só a unidade)'], ...ordensAbertas.map((x) => [x.id, x.numero])] },
    { k: 'tipo', rotulo: 'Tipo', tipo: 'select', opcoes: [['parada', 'Parada'], ['falta_material', 'Falta de material'], ['retrabalho', 'Retrabalho'], ['qualidade', 'Qualidade'], ['ajuste', 'Ajuste'], ['outro', 'Outro']] },
    { k: 'causa', rotulo: 'Motivo' }, { k: 'recurso_id', rotulo: 'Máquina/posto', tipo: 'select', num: true, opcoes: [['', '—'], ...recursos.map((r) => [r.id, r.nome])] }, { k: 'descricao', rotulo: 'Detalhes', tipo: 'textarea' }]);
  modal('Registrar ocorrência', f.el, { acoes: (fechar) => [h('button', { onclick: fechar }, 'Cancelar'), h('button', { class: 'pri', onclick: async () => {
    const v = f.valores();
    const corpo = { ...v, ordem_id: v.ordem_id || null, unidade_id: v.ordem_id ? null : estado.unidadeId };
    if (await tentar(() => post('/ocorrencias', corpo), 'Ocorrência registrada. Encerre-a na ordem quando terminar.')) { fechar(); aoSalvar(); }
  } }, 'Registrar')] });
}

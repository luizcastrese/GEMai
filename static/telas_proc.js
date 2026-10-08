import { api, get, patch, post, qs } from './api.js';
import { estado } from './estado.js';
import { confirmar, formulario, h, modal, montar, origemBadge, statusBadge, tabela, tentar, toast, badge, fmtNum, fmtData } from './ui.js';

const PARAMS = {
  tempo_preparacao_min: 'Tempo de preparação (min)', tempo_unitario_min: 'Tempo por unidade (min)',
  tamanho_lote: 'Tamanho do lote (un)', perda_percentual: 'Perda esperada (%)',
};

// ---------------------------------------------------------------- lista
export async function lista(el) {
  const ps = await get(`/processos${qs({ unidade_id: estado.unidadeId })}`);
  const f = formulario([{ k: 'nome', rotulo: 'Nome do processo' }, { k: 'macroprocesso', rotulo: 'Macroprocesso (grande fluxo)' }]);
  montar(el, h('h1', null, 'Processos'),
    h('p', { class: 'muted' }, 'Cada versão publicada é imutável; para alterar a estrutura, crie uma nova versão. Ordens ficam presas à versão com que foram criadas.'),
    h('div', { class: 'card' }, tabela([
      { t: 'Processo', f: (p) => h('a', { href: `#/processos/${p.id}` }, p.nome) }, { t: 'Macroprocesso', f: (p) => p.macroprocesso },
      { t: 'Versão', f: (p) => `v${p.versao}` }, { t: 'Status', f: (p) => statusBadge(p.status) },
      { t: 'Origem', f: (p) => (p.origem === 'ia' ? badge('Sugerido pela IA', 'b-ia') : 'Manual') }], ps, 'Nenhum processo. Use a Implantação com IA ou crie um abaixo.')),
    h('div', { class: 'card' }, h('h3', null, 'Novo processo'), f.el, h('p', null, h('button', { class: 'pri', onclick: async () => {
      const r = await tentar(() => post('/processos', { unidade_id: estado.unidadeId, ...f.valores() }), 'Processo criado.');
      if (r) location.hash = `#/processos/${r.id}`;
    } }, 'Criar'))));
}

// ---------------------------------------------------------------- detalhe
export async function detalhe(el, id) {
  const [p, recursos] = await Promise.all([get(`/processos/${id}`), get(`/recursos${qs({ unidade_id: estado.unidadeId, ativo: true })}`)]);
  const edit = p.status === 'rascunho';
  const recarregar = () => detalhe(el, id);
  const cmd = (fn, ok) => async () => { if (await tentar(fn, ok) !== undefined) recarregar(); };

  const cab = h('div', { class: 'card' }, h('div', { class: 'top' },
    h('div', null, h('h1', null, p.nome), h('div', { class: 'inline' }, statusBadge(p.status), `v${p.versao}`, p.macroprocesso ? `· ${p.macroprocesso}` : '', p.origem === 'ia' ? badge('Estrutura sugerida pela IA', 'b-ia') : null)),
    h('div', { class: 'inline' },
      edit ? h('button', { class: 'pri', onclick: async () => {
        const r = await tentar(() => post(`/processos/${id}/publicar`));
        if (r) { toast('Processo publicado.'); r.avisos.forEach((a) => toast(a, true)); recarregar(); }
      } }, 'Publicar') : null,
      !edit && p.status !== 'arquivado' ? h('button', { onclick: async () => { const r = await tentar(() => post(`/processos/${id}/nova-versao`), 'Nova versão (rascunho) criada.'); if (r) location.hash = `#/processos/${r.id}`; } }, 'Nova versão') : null,
      p.status !== 'arquivado' ? h('button', { class: 'dng', onclick: () => confirmar('Arquivar este processo? Ele deixa de aceitar novas ordens.', cmd(() => post(`/processos/${id}/arquivar`), 'Arquivado.')) }, 'Arquivar') : null)),
    edit ? h('div', { class: 'aviso' }, 'Rascunho: edite etapas e operações livremente. Ao publicar, a estrutura fica fixa (parâmetros continuam editáveis, com versionamento).') : null);

  const blocos = p.etapas.map((e, ei) => h('div', { class: 'etapa' },
    h('div', { class: 'top' }, h('strong', null, `${e.sequencia}. ${e.nome}`, e.opcional ? ` (opcional${e.condicao ? `: ${e.condicao}` : ''})` : ''),
      edit ? h('div', { class: 'inline' },
        h('button', { class: 'sm', disabled: ei === 0, onclick: cmd(() => patch(`/etapas/${e.id}`, { sequencia: e.sequencia - 1 })) }, '↑'),
        h('button', { class: 'sm', disabled: ei === p.etapas.length - 1, onclick: cmd(() => patch(`/etapas/${e.id}`, { sequencia: e.sequencia + 1 })) }, '↓'),
        h('button', { class: 'sm', onclick: () => formEtapa(e, recarregar) }, 'Editar'),
        h('button', { class: 'sm', onclick: () => formOperacao(e, null, recursos, recarregar) }, '+ Operação'),
        h('button', { class: 'sm dng', onclick: () => confirmar(`Remover a etapa "${e.nome}"?`, cmd(() => api('DELETE', `/etapas/${e.id}`), 'Etapa removida.')) }, '✕')) : null),
    (e.entradas.length || e.saidas.length) ? h('div', { class: 'muted small' }, `Entradas: ${e.entradas.join(', ') || '—'} · Saídas: ${e.saidas.join(', ') || '—'}`) : null,
    e.operacoes.map((o) => h('div', { class: 'op' }, operacaoView(o, p, edit, recursos, recarregar)))));

  montar(el, cab, h('h2', null, 'Etapas e operações'), blocos.length ? blocos : h('p', { class: 'muted' }, 'Sem etapas.'),
    edit ? h('p', null, h('button', { onclick: () => formEtapa(null, recarregar, id) }, '+ Etapa')) : null);
}

function operacaoView(o, p, edit, recursos, recarregar) {
  const alvo = h('div', { class: 'tw' }, h('span', { class: 'muted small' }, 'Carregando parâmetros…'));
  const nomeRec = recursos.find((r) => r.id === o.recurso_padrao_id)?.nome;
  const carregarParams = async () => {
    const ps = await get(`/parametros${qs({ escopo_tipo: 'operacao', escopo_id: o.id })}`);
    montar(alvo, ps.length ? tabela([
      { t: 'Parâmetro', f: (x) => PARAMS[x.nome] || x.nome }, { t: 'Valor', f: (x) => (x.valor_num === null ? h('em', null, 'a medir') : `${fmtNum(x.valor_num, 3)} ${x.unidade}`) },
      { t: 'Origem', f: (x) => origemBadge(x.origem) }, { t: 'Situação', f: (x) => (x.status_validacao === 'pendente' ? badge('Pendente de validação', 'b-warn') : x.vigente ? badge(`Vigente v${x.versao}`, 'b-ok') : badge('Histórico')) },
      { t: '', f: (x) => x.status_validacao === 'pendente' ? h('div', { class: 'inline' },
        h('button', { class: 'sm', disabled: x.valor_num === null, title: x.valor_num === null ? 'Informe o valor medido primeiro (botão Definir parâmetro).' : '', onclick: async () => { if (await tentar(() => post(`/parametros/${x.id}/validar`), 'Validado.')) carregarParams(); } }, 'Validar'),
        h('button', { class: 'sm', onclick: async () => { if (await tentar(() => post(`/parametros/${x.id}/rejeitar`), 'Rejeitado.')) carregarParams(); } }, 'Rejeitar')) : '' }], ps)
      : h('span', { class: 'muted small' }, 'Sem parâmetros.'));
  };
  carregarParams();
  return [
    h('div', { class: 'top' }, h('div', null, h('strong', null, o.nome), ' ', badge(`Fórmula: ${{ linear: 'preparação + tempo × qtd', lote: 'preparação + tempo × lotes', fixo: 'preparação + tempo fixo' }[o.formula_tipo]}`),
      nomeRec ? ` · recurso: ${nomeRec}` : '', o.alerta_ergonomia ? ' ' : '', o.alerta_ergonomia ? badge('Avaliar ergonomia', 'b-warn') : null),
      h('div', { class: 'inline' },
        h('button', { class: 'sm', onclick: () => formParametro(o, carregarParams) }, 'Definir parâmetro'),
        !edit && p.status === 'ativo' ? h('button', { class: 'sm', title: 'Usa a mediana dos apontamentos aprovados', onclick: async () => { if (await tentar(() => post(`/operacoes/${o.id}/parametros/atualizar-historico`), 'Parâmetros atualizados pelo histórico.')) carregarParams(); } }, 'Atualizar pelo histórico') : null,
        edit ? [h('button', { class: 'sm', onclick: () => formOperacao(null, o, recursos, recarregar) }, 'Editar'),
          h('button', { class: 'sm dng', onclick: () => confirmar(`Remover a operação "${o.nome}"?`, async () => { if (await tentar(() => api('DELETE', `/operacoes/${o.id}`), 'Operação removida.') !== undefined) recarregar(); }) }, '✕')] : null)),
    o.campos_extras.length ? h('div', { class: 'muted small' }, `Campos de apontamento: ${o.campos_extras.map((c) => `${c.nome} (${c.tipo}${c.obrigatorio ? ', obrigatório' : ''})`).join(', ')}`) : null,
    alvo];
}

function formEtapa(e, aoSalvar, processoId) {
  const f = formulario([{ k: 'nome', rotulo: 'Nome da etapa' }, { k: 'descricao', rotulo: 'Descrição', tipo: 'textarea' },
    { k: 'entradas', rotulo: 'Entradas (materiais, informações)', tipo: 'lista' }, { k: 'saidas', rotulo: 'Saídas', tipo: 'lista' },
    { k: 'opcional', rotulo: 'Etapa opcional / caminho alternativo', tipo: 'bool' }, { k: 'condicao', rotulo: 'Condição (quando ocorre)' }], e || {});
  modal(e ? 'Editar etapa' : 'Nova etapa', f.el, { acoes: (fechar) => [h('button', { onclick: fechar }, 'Cancelar'),
    h('button', { class: 'pri', onclick: async () => {
      const r = await tentar(() => (e ? patch(`/etapas/${e.id}`, f.valores()) : post(`/processos/${processoId}/etapas`, f.valores())), 'Salvo.');
      if (r) { fechar(); aoSalvar(); }
    } }, 'Salvar')] });
}

function formOperacao(etapa, op, recursos, aoSalvar) {
  const niveis = [['', '—'], ['baixo', 'Baixo'], ['medio', 'Médio'], ['alto', 'Alto']];
  const erg = op?.ergonomia || {};
  const f = formulario([
    { k: 'nome', rotulo: 'Nome da operação' }, { k: 'descricao', rotulo: 'Descrição', tipo: 'textarea' },
    { k: 'formula_tipo', rotulo: 'Como o tempo é calculado', tipo: 'select', opcoes: [['linear', 'Linear: preparação + tempo × quantidade'], ['lote', 'Por lote: preparação + tempo × nº de lotes'], ['fixo', 'Fixo: preparação + tempo único']] },
    { k: 'unidade_medida', rotulo: 'Unidade de medida' },
    { k: 'recurso_padrao_id', rotulo: 'Recurso padrão', tipo: 'select', num: true, opcoes: [['', '—'], ...recursos.map((r) => [r.id, r.nome])] },
    { k: 'campos', rotulo: 'Campos extras de apontamento (um por linha: nome|numero/texto/booleano|unidade|obrigatorio)', tipo: 'textarea', dica: 'temperatura|numero|°C|obrigatorio' },
    { k: 'e_rep', rotulo: 'Ergonomia — repetitividade', tipo: 'select', opcoes: niveis }, { k: 'e_esf', rotulo: 'Esforço físico', tipo: 'select', opcoes: niveis },
    { k: 'e_pos', rotulo: 'Postura', tipo: 'select', opcoes: niveis }, { k: 'e_des', rotulo: 'Deslocamento', tipo: 'select', opcoes: niveis },
    { k: 'e_pau', rotulo: 'Pausas', tipo: 'select', opcoes: [['', '—'], ['adequadas', 'Adequadas'], ['insuficientes', 'Insuficientes']] }],
  { ...(op || {}), campos: (op?.campos_extras || []).map((c) => [c.nome, c.tipo, c.unidade, c.obrigatorio ? 'obrigatorio' : ''].join('|')).join('\n'),
    e_rep: erg.repetitividade, e_esf: erg.esforco_fisico, e_pos: erg.postura, e_des: erg.deslocamento, e_pau: erg.pausas });
  modal(op ? 'Editar operação' : 'Nova operação', f.el, { larga: true, acoes: (fechar) => [h('button', { onclick: fechar }, 'Cancelar'),
    h('button', { class: 'pri', onclick: async () => {
      const v = f.valores();
      const campos_extras = v.campos.split('\n').map((l) => l.trim()).filter(Boolean).map((l) => {
        const [nome, tipo, unidade, obr] = l.split('|').map((s) => (s || '').trim());
        return { nome, tipo: tipo || 'numero', unidade: unidade || '', obrigatorio: obr === 'obrigatorio' };
      });
      const ergonomia = Object.fromEntries(Object.entries({ repetitividade: v.e_rep, esforco_fisico: v.e_esf, postura: v.e_pos, deslocamento: v.e_des, pausas: v.e_pau }).filter(([, x]) => x));
      const corpo = { nome: v.nome, descricao: v.descricao, formula_tipo: v.formula_tipo, unidade_medida: v.unidade_medida || 'un', recurso_padrao_id: v.recurso_padrao_id, campos_extras, ergonomia };
      const r = await tentar(() => (op ? patch(`/operacoes/${op.id}`, corpo) : post(`/etapas/${etapa.id}/operacoes`, corpo)), 'Salvo.');
      if (r) { fechar(); aoSalvar(); }
    } }, 'Salvar')] });
}

function formParametro(o, aoSalvar) {
  const f = formulario([
    { k: 'nome', rotulo: 'Parâmetro', tipo: 'select', opcoes: Object.entries(PARAMS) },
    { k: 'valor_num', rotulo: 'Valor', tipo: 'number' },
    { k: 'origem', rotulo: 'Como foi obtido', tipo: 'select', opcoes: [['informado', 'Informado pela empresa'], ['medido', 'Medido (cronometragem/registro)']] },
    { k: 'justificativa', rotulo: 'Justificativa / fonte', tipo: 'textarea' }]);
  modal(`Parâmetro — ${o.nome}`, h('div', null, f.el, h('p', { class: 'muted small' }, 'Cria uma nova versão, vigente e validada por você. A versão anterior fica no histórico.')),
    { acoes: (fechar) => [h('button', { onclick: fechar }, 'Cancelar'), h('button', { class: 'pri', onclick: async () => {
      const v = f.valores();
      if (v.valor_num === null) return toast('Informe o valor.', true);
      if (await tentar(() => post('/parametros', { escopo_tipo: 'operacao', escopo_id: o.id, ...v }), 'Parâmetro registrado.')) { fechar(); aoSalvar(); }
    } }, 'Salvar')] });
}

// ---------------------------------------------------------------- cadastros
const ENT = {
  recursos: { rot: 'Recursos', un: true, campos: [
    { k: 'nome', rotulo: 'Nome (ex.: Máquina 01)' }, { k: 'tipo', rotulo: 'Tipo', tipo: 'select', opcoes: [['maquina', 'Máquina'], ['posto', 'Posto'], ['ferramenta', 'Ferramenta'], ['instalacao', 'Instalação']] },
    { k: 'processos_relacionados', rotulo: 'Processos relacionados', tipo: 'lista' }, { k: 'capacidade', rotulo: 'Capacidade', tipo: 'number', nulo: true },
    { k: 'capacidade_unidade', rotulo: 'Unidade da capacidade' }, { k: 'equipes_habilitadas', rotulo: 'Equipes habilitadas', tipo: 'lista' },
    { k: 'local_posto', rotulo: 'Local / posto' }, { k: 'horas_disponiveis_dia', rotulo: 'Horas disponíveis por dia útil', tipo: 'number' },
    { k: 'ultima_manutencao', rotulo: 'Última manutenção', tipo: 'date', nulo: true }, { k: 'proxima_manutencao', rotulo: 'Próxima manutenção', tipo: 'date', nulo: true }],
    cols: [{ t: 'Nome', f: (r) => r.nome }, { t: 'Tipo', f: (r) => r.tipo }, { t: 'Capacidade', f: (r) => (r.capacidade ? `${r.capacidade} ${r.capacidade_unidade}` : '—') },
      { t: 'Tempo médio (calculado)', f: (r) => (r.tempo_medio_min ? `${fmtNum(r.tempo_medio_min, 2)} min/un` : '—') },
      { t: 'Preparação média', f: (r) => (r.tempo_preparacao_medio_min ? `${fmtNum(r.tempo_preparacao_medio_min)} min` : '—') }, { t: 'Próx. manutenção', f: (r) => r.proxima_manutencao || '—' }] },
  pessoas: { rot: 'Pessoas', un: true, campos: [{ k: 'nome', rotulo: 'Nome' }, { k: 'funcao', rotulo: 'Função' }, { k: 'equipe', rotulo: 'Equipe' }, { k: 'habilitacoes', rotulo: 'Habilitações', tipo: 'lista' }],
    cols: [{ t: 'Nome', f: (r) => r.nome }, { t: 'Função', f: (r) => r.funcao }, { t: 'Equipe', f: (r) => r.equipe }, { t: 'Habilitações', f: (r) => r.habilitacoes.join(', ') }] },
  materiais: { rot: 'Materiais', campos: [{ k: 'nome', rotulo: 'Nome' }, { k: 'tipo', rotulo: 'Tipo' }, { k: 'unidade_medida', rotulo: 'Unidade de medida' }],
    cols: [{ t: 'Nome', f: (r) => r.nome }, { t: 'Tipo', f: (r) => r.tipo }, { t: 'Unidade', f: (r) => r.unidade_medida }] },
  produtos: { rot: 'Produtos / serviços', campos: [{ k: 'nome', rotulo: 'Nome' }, { k: 'tipo', rotulo: 'Tipo', tipo: 'select', opcoes: [['produto', 'Produto'], ['servico', 'Serviço']] }, { k: 'descricao', rotulo: 'Descrição', tipo: 'textarea' }],
    cols: [{ t: 'Nome', f: (r) => r.nome }, { t: 'Tipo', f: (r) => r.tipo }, { t: 'Descrição', f: (r) => r.descricao }] },
};

export async function cadastros(el) {
  let aba = 'recursos';
  const area = h('div'); const abas = h('div', { class: 'tabs' });
  const desenhar = async () => {
    montar(abas, Object.entries(ENT).map(([k, e]) => h('button', { class: aba === k ? 'on' : '', onclick: () => { aba = k; desenhar(); } }, e.rot)));
    const e = ENT[aba];
    const itens = await get(`/${aba}${qs({ unidade_id: e.un ? estado.unidadeId : '' })}`);
    const abrir = (item) => {
      const f = formulario(e.campos, item || {});
      modal(item ? `Editar — ${item.nome}` : `Novo — ${e.rot}`, f.el, { acoes: (fechar) => [h('button', { onclick: fechar }, 'Cancelar'),
        h('button', { class: 'pri', onclick: async () => {
          const v = f.valores(); if (!item && e.un) v.unidade_id = estado.unidadeId;
          if (await tentar(() => (item ? patch(`/${aba}/${item.id}`, v) : post(`/${aba}`, v)), 'Salvo.')) { fechar(); desenhar(); }
        } }, 'Salvar')] });
    };
    montar(area, h('p', null, h('button', { class: 'pri', onclick: () => abrir() }, `+ Novo`)),
      h('div', { class: 'card' }, tabela([...e.cols, { t: 'Situação', f: (r) => (r.ativo ? badge('Ativo', 'b-ok') : badge('Inativo')) },
        { t: '', f: (r) => h('div', { class: 'inline' }, h('button', { class: 'sm', onclick: () => abrir(r) }, 'Editar'),
          h('button', { class: 'sm', onclick: async () => { if (await tentar(() => patch(`/${aba}/${r.id}`, { ativo: !r.ativo }))) desenhar(); } }, r.ativo ? 'Desativar' : 'Reativar')) }], itens)),
      h('p', { class: 'muted small' }, 'Itens não são excluídos para preservar o histórico; desative o que não for mais usado.'));
  };
  montar(el, h('h1', null, 'Recursos e cadastros'), abas, area);
  await desenhar();
}

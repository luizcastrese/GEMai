import { api, get, patch, post, qs } from './api.js';
import { estado, ehGestor } from './estado.js';
import { avisoIA, confirmar, detalhes, fmtMin, fonteBadge, formulario, h, modal, montar, origemBadge, statusBadge, tabela, tentar, toast, badge, fmtNum, fmtData } from './ui.js';
import { gerarAnalise } from './ia_view.js';

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
const textoPrevisao = (est) => {
  if (!est || est.fonte === 'sem_base') return h('span', { class: 'prev' }, 'Sem previsão de tempo ainda');
  const rot = { modelo_ia: est.validada ? badge('Previsão da IA confirmada', 'b-ok') : badge('Previsão da IA — falta confirmar', 'b-warn'),
    parametro: badge('Tempo informado', 'b-pri'), historico: badge('Baseada no histórico real', 'b-ok') }[est.fonte];
  return h('span', { class: 'prev' }, `Previsão: ${fmtMin(est.total_min)} para ${fmtNum(est.quantidade, 0)} un `, rot);
};

export async function detalhe(el, id) {
  const [p, recursos] = await Promise.all([get(`/processos/${id}`), get(`/recursos${qs({ unidade_id: estado.unidadeId, ativo: true })}`)]);
  const edit = p.status === 'rascunho';
  const recarregar = () => detalhe(el, id);
  const cmd = (fn, ok) => async () => { if (await tentar(fn, ok) !== undefined) recarregar(); };
  const todasOps = p.etapas.flatMap((e) => e.operacoes.map((o) => ({ o, e })));
  const previsoes = new Map(await Promise.all(todasOps.map(async ({ o }) => [o.id, await get(`/operacoes/${o.id}/estimativa?quantidade=10`).catch(() => null)])));

  // Um único "Publicar": pede a previsão de tempo à IA onde faltar e publica.
  const publicar = async () => {
    try { await post(`/processos/${id}/modelar-tempos`); } catch { /* sem IA ou sem dados: segue só com a publicação */ }
    const r = await tentar(() => post(`/processos/${id}/publicar`));
    if (r) { toast('Processo publicado. Confirme as previsões de tempo da IA abaixo.'); recarregar(); }
  };
  const cab = h('div', { class: 'card' }, h('div', { class: 'top' },
    h('div', null, h('h1', null, p.nome), h('div', { class: 'inline' }, statusBadge(p.status), `versão ${p.versao}`, p.origem === 'ia' ? badge('Montado com a IA', 'b-ia') : null)),
    ehGestor() ? h('div', { class: 'inline' },
      edit ? h('button', { class: 'pri big', onclick: publicar }, 'Publicar') : null,
      !edit && p.status !== 'arquivado' ? h('button', { onclick: async () => { const r = await tentar(() => post(`/processos/${id}/nova-versao`), 'Nova versão criada para edição.'); if (r) location.hash = `#/processos/${r.id}`; } }, 'Editar (nova versão)') : null,
      p.status !== 'arquivado' ? h('button', { class: 'dng', onclick: () => confirmar('Arquivar este processo? Ele deixa de aceitar novas ordens.', cmd(() => post(`/processos/${id}/arquivar`), 'Arquivado.')) }, 'Arquivar') : null) : null),
    edit ? h('div', { class: 'aviso' }, 'Em preparação: ajuste as tarefas à vontade. Ao publicar, a IA prevê o tempo de cada tarefa e o processo passa a aceitar ordens.') : null);

  const pront = h('div', { class: 'card' }, h('p', { class: 'muted' }, 'Verificando…'));
  prontidaoPainel(pront, p, recarregar, todasOps);

  const blocos = p.etapas.map((e, ei) => h('div', { class: 'etapa' },
    h('div', { class: 'top' }, h('strong', null, `${e.sequencia}. ${e.nome}`, e.opcional ? ' (opcional)' : ''),
      edit ? h('div', { class: 'inline' },
        h('button', { class: 'sm', disabled: ei === 0, onclick: cmd(() => patch(`/etapas/${e.id}`, { sequencia: e.sequencia - 1 })) }, '↑'),
        h('button', { class: 'sm', disabled: ei === p.etapas.length - 1, onclick: cmd(() => patch(`/etapas/${e.id}`, { sequencia: e.sequencia + 1 })) }, '↓'),
        h('button', { class: 'sm', onclick: () => formEtapa(e, recarregar) }, 'Renomear'),
        h('button', { class: 'sm', onclick: () => formOperacao(e, null, recursos, recarregar) }, '+ Tarefa'),
        h('button', { class: 'sm dng', onclick: () => confirmar(`Remover a etapa "${e.nome}"?`, cmd(() => api('DELETE', `/etapas/${e.id}`), 'Etapa removida.')) }, '✕')) : null),
    e.operacoes.map((o) => h('div', { class: 'op' },
      h('div', { class: 'top' }, h('div', null, h('strong', null, o.nome), ' ', o.alerta_ergonomia ? badge('Atenção: esforço físico', 'b-warn') : null, h('div', null, textoPrevisao(previsoes.get(o.id)))),
        ehGestor() ? h('div', { class: 'inline' },
          h('button', { class: 'sm', onclick: () => formTempoSimples(o, recarregar) }, 'Já sei o tempo'),
          edit ? [h('button', { class: 'sm', onclick: () => formOperacao(e, o, recursos, recarregar) }, 'Editar'),
            h('button', { class: 'sm dng', onclick: () => confirmar(`Remover "${o.nome}"?`, cmd(() => api('DELETE', `/operacoes/${o.id}`), 'Tarefa removida.')) }, '✕')] : null) : null),
      estado.avancado ? detalhes('Detalhes técnicos', operacaoView(o, p, edit, recursos, recarregar)) : null))));

  montar(el, cab, pront, h('h2', null, 'Etapas e tarefas'), blocos.length ? blocos : h('p', { class: 'muted' }, 'Sem etapas.'),
    edit ? h('p', null, h('button', { onclick: () => formEtapa(null, recarregar, id) }, '+ Etapa')) : null);
}

// "Já sei o tempo": o usuário informa o tempo medido e ele passa a valer no lugar da estimativa da IA.
function formTempoSimples(o, aoSalvar) {
  const f = formulario([{ k: 'unit', rotulo: 'Tempo por unidade (minutos)', tipo: 'number' }, { k: 'prep', rotulo: 'Tempo de preparação por ordem (minutos, opcional)', tipo: 'number', nulo: true }]);
  modal(`Tempo de "${o.nome}"`, h('div', null, f.el, h('p', { class: 'muted small' }, 'O tempo que você informar passa a valer no lugar da estimativa da IA.')),
    { acoes: (fechar) => [h('button', { onclick: fechar }, 'Cancelar'), h('button', { class: 'pri', onclick: async () => {
      const v = f.valores();
      if (!v.unit || v.unit <= 0) return toast('Informe o tempo por unidade.', true);
      const base = { escopo_tipo: 'operacao', escopo_id: o.id, origem: 'informado', justificativa: 'Informado pelo usuário.' };
      const ok1 = await tentar(() => post('/parametros', { ...base, nome: 'tempo_unitario_min', valor_num: v.unit }));
      const ok2 = v.prep ? await tentar(() => post('/parametros', { ...base, nome: 'tempo_preparacao_min', valor_num: v.prep })) : true;
      if (ok1 && ok2) { toast('Tempo registrado.'); fechar(); aoSalvar(); }
    } }, 'Salvar')] });
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
    alvo,
    modeloTempoView(o, p, recarregar)];
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

async function formOperacao(etapa, op, recursos, aoSalvar) {
  const esp = await get(`/espacos${qs({ unidade_id: estado.unidadeId, ativo: true })}`);
  const optEsp = [['', '—'], ...esp.map((x) => [x.id, x.nome])];
  // Essencial: o que qualquer pessoa sabe responder.
  const basico = formulario([
    { k: 'nome', rotulo: 'O que é feito nesta tarefa?', dica: 'ex.: Cortar chapas' },
    { k: 'funcao_requerida', rotulo: 'Quem executa? (função)', dica: 'ex.: auxiliar, marceneiro' },
    { k: 'num_pessoas', rotulo: 'Quantas pessoas fazem juntas?', tipo: 'number', padrao: 1, min: 1 },
    { k: 'recurso_padrao_id', rotulo: 'Equipamento ou posto usado', tipo: 'select', num: true, opcoes: [['', 'Nenhum (trabalho manual)'], ...recursos.map((r) => [r.id, r.nome])] },
    { k: 'espaco_origem_id', rotulo: 'De onde a peça sai?', tipo: 'select', num: true, opcoes: optEsp },
    { k: 'espaco_destino_id', rotulo: 'Para onde ela vai?', tipo: 'select', num: true, opcoes: optEsp },
    { k: 'item_peso_kg', rotulo: 'Peso de cada peça (kg)', tipo: 'number', nulo: true },
    { k: 'unidade_medida', rotulo: 'Contar em quê?', dica: 'ex.: peças, chapas, kg', padrao: 'un' },
    { k: 'inicio_marco', rotulo: 'Quando a tarefa COMEÇA?', dica: 'ex.: quando pega a primeira chapa' },
    { k: 'fim_marco', rotulo: 'Quando ela TERMINA?', dica: 'ex.: quando solta a última peça cortada' }], op || {});

  // Modo especialista: o restante (fatores técnicos, ergonomia, campos extras).
  let avancado = null;
  if (estado.avancado) {
    const perfis = await get(`/perfis-mao-de-obra${qs({ unidade_id: estado.unidadeId, ativo: true })}`);
    const niveis = [['', '—'], ['baixo', 'Baixo'], ['medio', 'Médio'], ['alto', 'Alto']];
    const erg = op?.ergonomia || {};
    const lev0 = op?.levantamento || {};
    avancado = formulario([
      { k: 'descricao', rotulo: 'Descrição', tipo: 'textarea' },
      { k: 'perfil_id', rotulo: 'Perfil de mão de obra (ritmo e limites de carga)', tipo: 'select', num: true, opcoes: [['', '—'], ...perfis.map((x) => [x.id, x.nome])] },
      { k: 'tipo_movimento', rotulo: 'Tipo de movimento predominante', tipo: 'select', opcoes: [['', '—'], ['alcance_curto', 'Alcance curto'], ['transporte_passos', 'Transporte a poucos passos'], ['levantamento_curvado', 'Curvar e levantar'], ['posicionamento_preciso', 'Posicionamento de precisão'], ['empurrar_puxar', 'Empurrar / puxar'], ['giro_tronco', 'Giro de tronco'], ['repetitivo_fino', 'Repetitivo fino'], ['outro', 'Outro']] },
      { k: 'postura_trabalho', rotulo: 'Postura de trabalho', tipo: 'select', opcoes: [['', '—'], ['em_pe', 'Em pé'], ['sentado', 'Sentado'], ['alternada', 'Alternada'], ['agachado', 'Agachado'], ['curvado', 'Curvado']] },
      { k: 'altura_trabalho_m', rotulo: 'Altura da superfície de trabalho (m)', tipo: 'number', nulo: true },
      { k: 'gasto_energetico_kcal_min', rotulo: 'Gasto energético (kcal/min)', tipo: 'number', nulo: true },
      { k: 'distancia_m', rotulo: 'Distância manual (m), se diferente da tabela de distâncias', tipo: 'number', nulo: true },
      { k: 'item_comprimento_m', rotulo: 'Peça: comprimento (m)', tipo: 'number', nulo: true }, { k: 'item_largura_m', rotulo: 'Largura (m)', tipo: 'number', nulo: true }, { k: 'item_altura_m', rotulo: 'Altura (m)', tipo: 'number', nulo: true },
      { k: 'lev_carga_kg', rotulo: 'Levantamento manual (NIOSH): carga (kg)', tipo: 'number', nulo: true },
      { k: 'lev_h_cm', rotulo: 'H: distância horizontal (cm)', tipo: 'number', nulo: true }, { k: 'lev_v_cm', rotulo: 'V: altura da pega (cm)', tipo: 'number', nulo: true },
      { k: 'lev_d_cm', rotulo: 'D: deslocamento vertical (cm)', tipo: 'number', nulo: true }, { k: 'lev_a_graus', rotulo: 'A: assimetria (graus)', tipo: 'number', nulo: true },
      { k: 'lev_freq_por_min', rotulo: 'Frequência (levantamentos/min)', tipo: 'number', nulo: true },
      { k: 'lev_duracao', rotulo: 'Duração do trabalho com levantamento', tipo: 'select', opcoes: [['', '—'], ['ate_1h', 'Até 1 h'], ['1_2h', '1 a 2 h'], ['2_8h', '2 a 8 h']] },
      { k: 'lev_pega', rotulo: 'Qualidade da pega', tipo: 'select', opcoes: [['', '—'], ['boa', 'Boa'], ['regular', 'Regular'], ['ruim', 'Ruim']] },
      { k: 'formula_tipo', rotulo: 'Cálculo do tempo manual/parâmetro', tipo: 'select', opcoes: [['linear', 'Linear'], ['lote', 'Por lote'], ['fixo', 'Fixo']] },
      { k: 'campos', rotulo: 'Campos extras de apontamento (nome|numero/texto/booleano|unidade|obrigatorio)', tipo: 'textarea' },
      { k: 'e_rep', rotulo: 'Ergonomia: repetitividade', tipo: 'select', opcoes: niveis }, { k: 'e_esf', rotulo: 'Esforço físico', tipo: 'select', opcoes: niveis },
      { k: 'e_pos', rotulo: 'Postura', tipo: 'select', opcoes: niveis }, { k: 'e_des', rotulo: 'Deslocamento', tipo: 'select', opcoes: niveis },
      { k: 'e_pau', rotulo: 'Pausas', tipo: 'select', opcoes: [['', '—'], ['adequadas', 'Adequadas'], ['insuficientes', 'Insuficientes']] }],
    { ...(op || {}), campos: (op?.campos_extras || []).map((c) => [c.nome, c.tipo, c.unidade, c.obrigatorio ? 'obrigatorio' : ''].join('|')).join('\n'),
      e_rep: erg.repetitividade, e_esf: erg.esforco_fisico, e_pos: erg.postura, e_des: erg.deslocamento, e_pau: erg.pausas,
      lev_carga_kg: lev0.carga_kg, lev_h_cm: lev0.h_cm, lev_v_cm: lev0.v_cm, lev_d_cm: lev0.d_cm, lev_a_graus: lev0.a_graus, lev_freq_por_min: lev0.freq_por_min, lev_duracao: lev0.duracao, lev_pega: lev0.pega });
  }
  const corpoModal = h('div', null,
    h('p', { class: 'muted small' }, 'Responda o que souber. A IA usa estas respostas para prever o tempo; o que faltar ela avisa depois.'),
    basico.el, avancado ? detalhes('Opções de especialista', avancado.el) : null);
  modal(op ? 'Editar tarefa' : 'Nova tarefa', corpoModal, { larga: true, acoes: (fechar) => [h('button', { onclick: fechar }, 'Cancelar'),
    h('button', { class: 'pri', onclick: async () => {
      const b = basico.valores();
      if (!b.nome) return toast('Diga o que é feito nesta tarefa.', true);
      const corpo = { ...b, num_pessoas: Math.max(1, Math.round(b.num_pessoas || 1)), unidade_medida: b.unidade_medida || 'un' };
      if (avancado) {
        const v = avancado.valores();
        const levBruto = { carga_kg: v.lev_carga_kg, h_cm: v.lev_h_cm, v_cm: v.lev_v_cm, d_cm: v.lev_d_cm, a_graus: v.lev_a_graus, freq_por_min: v.lev_freq_por_min, duracao: v.lev_duracao, pega: v.lev_pega };
        const lev = Object.fromEntries(Object.entries(levBruto).filter(([, x]) => x !== null && x !== ''));
        const campos_extras = v.campos.split('\n').map((l) => l.trim()).filter(Boolean).map((l) => {
          const [nome, tipo, unidade, obr] = l.split('|').map((x) => (x || '').trim());
          return { nome, tipo: tipo || 'numero', unidade: unidade || '', obrigatorio: obr === 'obrigatorio' };
        });
        const ergonomia = Object.fromEntries(Object.entries({ repetitividade: v.e_rep, esforco_fisico: v.e_esf, postura: v.e_pos, deslocamento: v.e_des, pausas: v.e_pau }).filter(([, x]) => x));
        const { campos, e_rep, e_esf, e_pos, e_des, e_pau, lev_carga_kg, lev_h_cm, lev_v_cm, lev_d_cm, lev_a_graus, lev_freq_por_min, lev_duracao, lev_pega, ...resto } = v;
        Object.assign(corpo, resto, { campos_extras, ergonomia, levantamento: Object.keys(lev).length ? lev : null });
      }
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
    { k: 'capacidade_unidade', rotulo: 'Unidade da capacidade (use un/h ou un/min para o gêmeo digital)', padrao: 'un/h' }, { k: 'equipes_habilitadas', rotulo: 'Equipes habilitadas', tipo: 'lista' },
    { k: 'local_posto', rotulo: 'Local / posto' }, { k: 'horas_disponiveis_dia', rotulo: 'Horas disponíveis por dia útil', tipo: 'number', padrao: 8 },
    { k: 'ultima_manutencao', rotulo: 'Última manutenção', tipo: 'date', nulo: true }, { k: 'proxima_manutencao', rotulo: 'Próxima manutenção', tipo: 'date', nulo: true }],
    cols: [{ t: 'Nome', f: (r) => r.nome }, { t: 'Tipo', f: (r) => r.tipo }, { t: 'Capacidade', f: (r) => (r.capacidade ? `${r.capacidade} ${r.capacidade_unidade}` : '—') },
      { t: 'Tempo médio (calculado)', f: (r) => (r.tempo_medio_min ? `${fmtNum(r.tempo_medio_min, 2)} min/un` : '—') },
      { t: 'Preparação média', f: (r) => (r.tempo_preparacao_medio_min ? `${fmtNum(r.tempo_preparacao_medio_min)} min` : '—') }, { t: 'Próx. manutenção', f: (r) => r.proxima_manutencao || '—' }] },
  espacos: { rot: 'Espaços (contorno físico)', un: true, campos: [
    { k: 'nome', rotulo: 'Nome (ex.: Estoque de chapas)' }, { k: 'tipo', rotulo: 'Tipo', tipo: 'select', opcoes: [['area', 'Área'], ['posto', 'Posto'], ['estoque', 'Estoque'], ['expedicao', 'Expedição']] },
    { k: 'comprimento_m', rotulo: 'Comprimento (m)', tipo: 'number', nulo: true }, { k: 'largura_m', rotulo: 'Largura (m)', tipo: 'number', nulo: true },
    { k: 'pe_direito_m', rotulo: 'Pé-direito (m)', tipo: 'number', nulo: true }, { k: 'piso', rotulo: 'Piso' },
    { k: 'temperatura_c', rotulo: 'Temperatura média (°C)', tipo: 'number', nulo: true }, { k: 'umidade_pct', rotulo: 'Umidade relativa (%)', tipo: 'number', nulo: true },
    { k: 'ruido_db', rotulo: 'Ruído (dB(A))', tipo: 'number', nulo: true }, { k: 'iluminancia_lux', rotulo: 'Iluminância (lux)', tipo: 'number', nulo: true }, { k: 'observacoes', rotulo: 'Observações', tipo: 'textarea' }],
    cols: [{ t: 'Nome', f: (r) => r.nome }, { t: 'Tipo', f: (r) => r.tipo }, { t: 'Dimensões', f: (r) => (r.comprimento_m && r.largura_m ? `${r.comprimento_m} × ${r.largura_m} m` : '—') },
      { t: 'Temperatura', f: (r) => (r.temperatura_c === null ? '—' : `${r.temperatura_c} °C`) }, { t: 'Origem', f: (r) => (r.origem === 'ia' ? badge('Sugerido pela IA', 'b-ia') : 'Manual') }] },
  'perfis-mao-de-obra': { rot: 'Perfis de mão de obra', un: true, aviso: 'Perfis de REFERÊNCIA (não são pessoas). Sexo, estatura e peso corporal servem apenas a limites de carga e conferências ergonômicas; NÃO alteram o tempo nem medem produtividade. O ritmo deve ser calibrado por medição. Não use estes dados para decisões de contratação ou alocação de pessoas.',
    campos: [{ k: 'nome', rotulo: 'Nome do perfil (ex.: Auxiliar de corte)' },
      { k: 'sexo', rotulo: 'Sexo de referência (para limites de carga)', tipo: 'select', opcoes: [['nao_informado', 'Não informado'], ['feminino', 'Feminino'], ['masculino', 'Masculino'], ['misto', 'Misto']] },
      { k: 'faixa_etaria', rotulo: 'Faixa etária', tipo: 'select', opcoes: [['adulto', 'Adulto'], ['menor_18', 'Menor de 18 anos']] },
      { k: 'estatura_cm', rotulo: 'Estatura (cm)', tipo: 'number', nulo: true }, { k: 'peso_corporal_kg', rotulo: 'Peso corporal (kg)', tipo: 'number', nulo: true },
      { k: 'altura_cotovelo_cm', rotulo: 'Altura do cotovelo (cm) — para comparar com a altura de trabalho', tipo: 'number', nulo: true },
      { k: 'experiencia', rotulo: 'Experiência', tipo: 'select', opcoes: [['iniciante', 'Iniciante'], ['intermediario', 'Intermediário'], ['experiente', 'Experiente']] },
      { k: 'ritmo_pct', rotulo: 'Ritmo (100 = normal; calibre por medição)', tipo: 'number', padrao: 100 },
      { k: 'limite_energetico_kcal_min', rotulo: 'Limite de gasto energético adotado (kcal/min) — para o descanso de Murrell; opcional, as fontes divergem', tipo: 'number', nulo: true },
      { k: 'observacoes', rotulo: 'Observações', tipo: 'textarea' }],
    cols: [{ t: 'Perfil', f: (r) => r.nome }, { t: 'Sexo ref.', f: (r) => r.sexo }, { t: 'Estatura', f: (r) => (r.estatura_cm ? `${r.estatura_cm} cm` : '—') },
      { t: 'Peso corporal', f: (r) => (r.peso_corporal_kg ? `${r.peso_corporal_kg} kg` : '—') }, { t: 'Experiência', f: (r) => r.experiencia }, { t: 'Ritmo', f: (r) => `${r.ritmo_pct}%` }] },
  pessoas: { rot: 'Pessoas', un: true, campos: [{ k: 'nome', rotulo: 'Nome' }, { k: 'funcao', rotulo: 'Função' }, { k: 'equipe', rotulo: 'Equipe' }, { k: 'habilitacoes', rotulo: 'Habilitações', tipo: 'lista' }],
    cols: [{ t: 'Nome', f: (r) => r.nome }, { t: 'Função', f: (r) => r.funcao }, { t: 'Equipe', f: (r) => r.equipe }, { t: 'Habilitações', f: (r) => r.habilitacoes.join(', ') }] },
  materiais: { rot: 'Materiais', campos: [{ k: 'nome', rotulo: 'Nome' }, { k: 'tipo', rotulo: 'Tipo' }, { k: 'unidade_medida', rotulo: 'Unidade de medida' }],
    cols: [{ t: 'Nome', f: (r) => r.nome }, { t: 'Tipo', f: (r) => r.tipo }, { t: 'Unidade', f: (r) => r.unidade_medida }] },
  produtos: { rot: 'Produtos / serviços', campos: [{ k: 'nome', rotulo: 'Nome' }, { k: 'tipo', rotulo: 'Tipo', tipo: 'select', opcoes: [['produto', 'Produto'], ['servico', 'Serviço']] }, { k: 'descricao', rotulo: 'Descrição', tipo: 'textarea' },
    { k: 'peso_kg', rotulo: 'Peso (kg)', tipo: 'number', nulo: true }, { k: 'comprimento_m', rotulo: 'Comprimento (m)', tipo: 'number', nulo: true }, { k: 'largura_m', rotulo: 'Largura (m)', tipo: 'number', nulo: true }, { k: 'altura_m', rotulo: 'Altura (m)', tipo: 'number', nulo: true }],
    cols: [{ t: 'Nome', f: (r) => r.nome }, { t: 'Tipo', f: (r) => r.tipo }, { t: 'Peso', f: (r) => (r.peso_kg === null ? '—' : `${r.peso_kg} kg`) }, { t: 'Descrição', f: (r) => r.descricao }] },
};

// Campos e colunas que só aparecem no modo especialista.
const AVANCADO = {
  recursos: ['processos_relacionados', 'equipes_habilitadas', 'local_posto', 'horas_disponiveis_dia', 'ultima_manutencao', 'proxima_manutencao', 'capacidade_unidade'],
  espacos: ['pe_direito_m', 'piso', 'temperatura_c', 'umidade_pct', 'ruido_db', 'iluminancia_lux', 'observacoes'],
  pessoas: ['habilitacoes'], produtos: ['comprimento_m', 'largura_m', 'altura_m'],
};
const COLS_SIMPLES = { recursos: 3, espacos: 3, pessoas: 3, 'perfis-mao-de-obra': 6 };
const ROTULOS = { recursos: 'Equipamentos', espacos: 'Locais', pessoas: 'Equipe', materiais: 'Materiais', produtos: 'Produtos e serviços', 'perfis-mao-de-obra': 'Perfis de mão de obra' };
const AJUSTES = { recursos: { capacidade: 'Quantas peças por hora faz? (opcional, ajuda a IA a prever o tempo)' }, espacos: { nome: 'Nome do local (ex.: Estoque de chapas)' } };

export async function cadastros(el) {
  let aba = 'recursos';
  const area = h('div'); const abas = h('div', { class: 'tabs' });
  const desenhar = async () => {
    montar(abas, Object.entries(ENT).filter(([k]) => estado.avancado || k !== 'perfis-mao-de-obra').map(([k, e]) => h('button', { class: aba === k ? 'on' : '', onclick: () => { aba = k; desenhar(); } }, ROTULOS[k] || e.rot)));
    const e = ENT[aba];
    const itens = await get(`/${aba}${qs({ unidade_id: e.un ? estado.unidadeId : '' })}`);
    const espacos = aba === 'recursos' ? await get(`/espacos${qs({ unidade_id: estado.unidadeId, ativo: true })}`) : [];
    const abrir = (item) => {
      let campos = aba === 'recursos' ? [...e.campos, { k: 'espaco_id', rotulo: 'Em que local fica?', tipo: 'select', num: true, opcoes: [['', '—'], ...espacos.map((x) => [x.id, x.nome])] }] : e.campos;
      campos = campos.filter((c) => estado.avancado || !(AVANCADO[aba] || []).includes(c.k)).map((c) => ((AJUSTES[aba] || {})[c.k] ? { ...c, rotulo: AJUSTES[aba][c.k] } : c));
      const f = formulario(campos, item || {});
      modal(item ? `Editar — ${item.nome}` : `Novo — ${e.rot}`, f.el, { acoes: (fechar) => [h('button', { onclick: fechar }, 'Cancelar'),
        h('button', { class: 'pri', onclick: async () => {
          const v = f.valores(); if (!item && e.un) v.unidade_id = estado.unidadeId;
          if (await tentar(() => (item ? patch(`/${aba}/${item.id}`, v) : post(`/${aba}`, v)), 'Salvo.')) { fechar(); desenhar(); }
        } }, 'Salvar')] });
    };
    montar(area, e.aviso ? h('div', { class: 'aviso' }, e.aviso) : null, h('p', null, h('button', { class: 'pri', onclick: () => abrir() }, '+ Adicionar')),
      h('div', { class: 'card' }, tabela([...(estado.avancado ? e.cols : e.cols.slice(0, COLS_SIMPLES[aba] || 99)), { t: 'Situação', f: (r) => (r.ativo ? badge('Ativo', 'b-ok') : badge('Inativo')) },
        { t: '', f: (r) => h('div', { class: 'inline' }, h('button', { class: 'sm', onclick: () => abrir(r) }, 'Editar'),
          h('button', { class: 'sm', onclick: async () => { if (await tentar(() => patch(`/${aba}/${r.id}`, { ativo: !r.ativo }))) desenhar(); } }, r.ativo ? 'Desativar' : 'Reativar')) }], itens)),
      aba === 'espacos' ? await painelDistancias(itens, desenhar) : null,
      h('p', { class: 'muted small' }, 'Itens não são excluídos para preservar o histórico; desative o que não for mais usado.'));
  };
  montar(el, h('h1', null, 'Equipamentos e locais'), h('p', { class: 'muted' }, 'Cadastre o que existe na sua operação. Quanto mais a IA souber (capacidades, locais, distâncias, pesos), melhor ela prevê o tempo.'), abas, area);
  await desenhar();
}


// ---------------------------------------------------------------- gêmeo digital
async function prontidaoPainel(alvo, p, recarregar, todasOps) {
  const r = await get(`/processos/${p.id}/prontidao`);
  const visivel = (i) => (estado.avancado || i.categoria !== 'tecnico') && (i.nivel !== 'info' || estado.avancado || i.msg.includes('aguarda'));
  const linhas = r.operacoes.map((o) => ({ o, itens: o.itens.filter(visivel) })).filter((x) => x.itens.length);
  const aConfirmar = r.operacoes.filter((o) => o.itens.some((i) => i.msg.includes('aguarda a sua confirmação'))).length;
  const semPrevisao = r.operacoes.some((o) => o.itens.some((i) => i.msg.includes('sem previsão de tempo')));
  const edit = p.status === 'rascunho';
  const etapaDe = (opId) => p.etapas.find((e) => e.operacoes.some((x) => x.id === opId));
  const opDe = (opId) => p.etapas.flatMap((e) => e.operacoes).find((x) => x.id === opId);
  montar(alvo, h('div', { class: 'top' }, h('h2', null, 'Está tudo pronto?'),
    ehGestor() ? h('div', { class: 'inline' },
      h('button', { class: semPrevisao ? 'ia' : '', onclick: async () => {
        const c = await tentar(() => post(`/processos/${p.id}/modelar-tempos`));
        if (c) { toast(c.length ? 'A IA preparou as previsões de tempo. Confira e confirme.' : 'Todas as tarefas já têm previsão.'); recarregar(); }
      } }, 'Pedir previsão de tempo à IA'),
      aConfirmar ? h('button', { class: 'pri', onclick: async () => {
        const c = await tentar(() => post(`/processos/${p.id}/confirmar-previsoes`));
        if (c) { toast(`${c.confirmadas} previsão(ões) confirmada(s).`); recarregar(); }
      } }, `Confirmar ${aConfirmar} previsão(ões)`) : null,
      estado.avancado ? h('button', { class: 'ia', onclick: () => gerarAnalise('revisao_processo', { unidade_id: p.unidade_id, processo_id: p.id }) }, 'Como deixar o processo consistente? (IA)') : null) : null),
    linhas.length ? h('div', { class: 'pronto' }, linhas.map(({ o, itens }) => h('div', null, h('strong', null, o.nome),
      h('ul', null, itens.map((i) => h('li', { class: i.categoria === 'seguranca' ? 'seg' : '' }, i.categoria === 'seguranca' ? '⚠ ' : '', i.msg, estado.avancado && i.detalhe ? h('div', { class: 'muted small' }, i.detalhe) : null))),
      edit && ehGestor() && etapaDe(o.operacao_id) ? h('button', { class: 'sm', onclick: () => formOperacaoPorId(etapaDe(o.operacao_id), opDe(o.operacao_id), recarregar) }, 'Editar tarefa') : null)))
      : h('div', { class: 'ok-box card' }, h('strong', null, '✓ Tudo certo.'), ' Nenhuma pendência nas tarefas deste processo.'));
}

async function formOperacaoPorId(etapa, op, recarregar) {
  const recursos = await get(`/recursos${qs({ unidade_id: estado.unidadeId, ativo: true })}`);
  formOperacao(etapa, op, recursos, recarregar);
}

function modeloTempoView(o, p, recarregar) {
  const corpo = h('div', { class: 'muted small' }, 'Abra para ver o modelo de tempo.');
  const det = h('details', { class: 'small' }, h('summary', null, 'Modelo de tempo (gêmeo digital)'), corpo);
  let carregado = false;
  const carregar = async () => {
    const [modelos, sim, erg] = await Promise.all([get(`/operacoes/${o.id}/modelo-tempo`), get(`/operacoes/${o.id}/estimativa?quantidade=${qtdSim.valor}`), get(`/operacoes/${o.id}/ergonomia`)]);
    const n = erg.niosh;
    const ergBox = h('div', null, h('strong', null, 'Ergonomia e carga (triagem)'),
      n.completo ? h('div', null, `NIOSH: limite recomendado ${fmtNum(n.rwl_kg, 2)} kg · índice de levantamento ${n.li_infinito ? '∞' : fmtNum(n.li, 2)} — ${n.leitura}.`)
        : h('div', { class: 'muted' }, n.faltantes?.length && n.faltantes.length < 8 && (o.levantamento) ? `Levantamento incompleto: ${n.faltantes.join('; ')}.` : 'Sem levantamento manual informado.'),
      erg.alertas.length ? h('ul', null, erg.alertas.map((a) => h('li', null, a))) : null,
      h('div', { class: 'muted small' }, 'Triagem; não substitui a análise ergonômica do trabalho (NR-17) por profissional competente.'));
    const m = modelos.find((x) => x.status_validacao !== 'rejeitado');
    montar(corpo,
      h('div', { class: 'inline' },
        h('button', { class: 'sm ia', onclick: async () => { if (await tentar(() => post(`/operacoes/${o.id}/modelo-tempo/gerar`), 'Modelo gerado. Revise e valide.')) carregar(); } }, m ? 'Gerar nova versão (IA)' : 'Modelar tempo (IA)'),
        h('label', { class: 'inline' }, 'Simular quantidade:', h('input', { type: 'number', min: '1', value: qtdSim.valor, style: undefined, onchange: (e) => { qtdSim.valor = Number(e.target.value) || 1; carregar(); } }))),
      h('div', { class: 'card' }, h('strong', null, 'Tempo planejado: '), fonteBadge(sim.fonte), sim.fonte === 'modelo_ia' && !sim.validada ? [' ', badge('Não validado', 'b-warn')] : null,
        ' ', sim.total_min === null ? 'sem estimativa' : `${fmtMin(sim.total_min)} (preparação ${fmtMin(sim.preparacao_min)} + execução ${fmtMin(sim.execucao_min)})`,
        sim.avisos.length ? h('ul', { class: 'muted' }, sim.avisos.map((a) => h('li', null, a))) : null),
      h('div', { class: 'card' }, ergBox),
      m ? h('div', null,
        h('div', { class: 'inline' }, badge(m.origem === 'ia' ? `IA · ${m.provedor}` : 'Manual', m.origem === 'ia' ? 'b-ia' : ''), statusBadge(m.status_validacao),
          badge(`Confiança ${m.confianca}`, m.confianca === 'baixa' ? 'b-warn' : 'b-ok'), badge(`v${m.versao}`), m.fator_ambiente !== 1 ? badge(`Fator de ambiente ${m.fator_ambiente}`) : null),
        m.origem === 'ia' ? avisoIA('Estimativa gerada por IA: não é um fato. O sistema calcula; você valida e compara com o tempo real.') : null,
        tabela([{ t: 'Elemento', f: (e) => e.nome }, { t: 'Tipo', f: (e) => e.tipo }, { t: 'Método', f: (e) => e.metodo },
          { t: 'Minutos (simulação)', f: (e) => { const x = (sim.elementos || []).find((y) => y.nome === e.nome); return x ? (x.minutos === null ? h('span', { class: 'muted' }, 'falta dado') : fmtNum(x.minutos, 2)) : '—'; } },
          { t: 'Justificativa', f: (e) => e.justificativa }], m.elementos, 'Modelo sem elementos.'),
        m.tolerancias?.length ? h('div', null, h('strong', null, `Tolerâncias (tempo padrão = tempo normal × FT; ritmo ${m.ritmo_pct}%)`),
          tabela([{ t: 'Categoria', f: (x) => x.categoria }, { t: '%', f: (x) => fmtNum(x.percentual, 2) }, { t: 'Fonte', f: (x) => x.fonte }, { t: 'Justificativa', f: (x) => x.justificativa }], m.tolerancias)) : null,
        m.premissas.length ? h('div', null, h('strong', null, 'Premissas'), h('ul', null, m.premissas.map((x) => h('li', null, x)))) : null,
        m.dados_faltantes.length ? h('div', { class: 'aviso' }, h('strong', null, 'Dados que faltam para um tempo consistente'), h('ul', null, m.dados_faltantes.map((x) => h('li', null, x)))) : null,
        m.padrao_apontamento?.inicio ? h('div', { class: 'muted' }, `Padrão de apontamento sugerido — início: ${m.padrao_apontamento.inicio} · fim: ${m.padrao_apontamento.fim} · contagem: ${m.padrao_apontamento.unidade_contagem}`) : null,
        m.justificativa ? h('div', { class: 'muted' }, m.justificativa) : null,
        m.status_validacao === 'pendente' ? h('div', { class: 'inline' },
          h('button', { class: 'sm pri', onclick: async () => { if (await tentar(() => post(`/modelos-tempo/${m.id}/validar`), 'Modelo validado.')) { carregar(); } } }, 'Validar modelo'),
          h('button', { class: 'sm dng', onclick: async () => { if (await tentar(() => post(`/modelos-tempo/${m.id}/rejeitar`), 'Modelo rejeitado.')) carregar(); } }, 'Rejeitar')) : null) : null);
  };
  const qtdSim = { valor: 10 };
  det.addEventListener('toggle', () => { if (det.open && !carregado) { carregado = true; carregar(); } });
  return det;
}


async function painelDistancias(espacos, refazer) {
  const ativos = espacos.filter((x) => x.ativo);
  const ds = await get(`/distancias${qs({ unidade_id: estado.unidadeId })}`);
  const nome = (id) => espacos.find((x) => x.id === id)?.nome || id;
  const f = formulario([{ k: 'origem_id', rotulo: 'Entre', tipo: 'select', num: true, opcoes: ativos.map((x) => [x.id, x.nome]) },
    { k: 'destino_id', rotulo: 'e', tipo: 'select', num: true, opcoes: ativos.map((x) => [x.id, x.nome]) }, { k: 'metros', rotulo: 'Distância (m)', tipo: 'number' }]);
  return h('div', { class: 'card' }, h('h3', null, 'Distâncias entre espaços'),
    h('p', { class: 'muted small' }, 'Valem nos dois sentidos e alimentam o cálculo de deslocamento do tempo planejado.'),
    tabela([{ t: 'Espaços', f: (d) => `${nome(d.origem_id)} ↔ ${nome(d.destino_id)}` }, { t: 'Metros', f: (d) => fmtNum(d.metros, 1) }], ds, 'Nenhuma distância cadastrada.'),
    f.el, h('p', null, h('button', { class: 'pri', onclick: async () => {
      const v = f.valores();
      if (!v.origem_id || !v.destino_id || v.metros === null) return toast('Escolha os dois espaços e informe a distância.', true);
      if (await tentar(() => api('PUT', '/distancias', v), 'Distância salva.')) refazer();
    } }, 'Salvar distância')));
}

// Atividades (módulos de tempo): a empresa descreve uma atividade que o catálogo ainda não tem; a IA a DELIMITA (como o tempo é
// calculado, o que medir, o que pedir na ficha do equipamento) e uma pessoa confere e valida. Nenhum minuto é digitado.
import { get, post } from './api.js';
import { badge, confirmar, detalhes, fmtMin, h, montar, statusBadge, tentar } from './ui.js';

const ARQ = {
  processamento_meio: 'Feita por um equipamento',
  manual: 'Feita à mão',
  deslocamento: 'Levar de um lugar a outro',
  espera: 'Espera (secagem, cura…)',
};
const POR = { peca: 'por peça', unidade_produto: 'por unidade do produto' };
const CAMPO = {
  '{qtd}': 'quantidade de peças', '{area_m2}': 'área da peça (m²)', '{perimetro_m}': 'perímetro da peça (m)', '{comp}': 'comprimento (m)',
  '{peso_kg}': 'peso (kg)', '{volume_m3}': 'volume (m³)', '{unidade}': 'uma vez',
};
const comoMede = (e) => CAMPO[e.driver] || e.driver;

function decidir(m, acao, depois) {
  const ok = acao === 'validar';
  confirmar(ok ? 'Validar esta atividade? Ela passa a entrar nos novos planos.' : 'Descartar esta proposta?', async () => {
    if (await tentar(() => post(`/modulos/empresa/${m.id}/${acao}`, {}), ok ? 'Atividade validada.' : 'Proposta descartada.')) depois();
  }, ok ? 'Validar' : 'Descartar');
}

function cartao(m, depois) {
  const e = m.espec || {};
  const ex = m.exemplo;
  return h('div', { class: 'card' },
    h('h3', null, m.titulo, ' ', statusBadge(m.status), m.vigente ? [' ', badge('Em uso', 'b-ok')] : null),
    h('p', null, h('strong', null, ARQ[m.arquetipo] || m.arquetipo), ` · medida por ${comoMede(e)}, ${POR[e.unidade_contagem] || ''}.`),
    e.taxa ? h('p', { class: 'small' }, 'Precisa na ficha do equipamento: ', h('strong', null, `${e.taxa.descricao} (${e.taxa.unidade})`),
      e.funcao_meio ? ` · cadastre o equipamento com a função "${e.funcao_meio}"` : '') : null,
    e.acoes && e.acoes.length ? h('p', { class: 'small muted' }, 'Movimentos: ', e.acoes.map((a) => a.nome).join(', '), '.') : null,
    m.problemas && m.problemas.length ? h('div', { class: 'aviso' }, 'Falta corrigir: ', m.problemas.join('; ')) : null,
    m.dados_faltantes && m.dados_faltantes.length ? h('div', { class: 'aviso' }, 'Para o tempo ficar bom: ', m.dados_faltantes.join('; ')) : null,
    m.status === 'pendente' ? h('div', { class: 'inline' },
      h('button', { class: 'pri', disabled: !!(m.problemas && m.problemas.length), onclick: () => decidir(m, 'validar', depois) }, 'Validar'),
      h('button', { onclick: () => decidir(m, 'rejeitar', depois) }, 'Descartar')) : null,
    detalhes('Ver como o tempo é calculado',
      h('p', { class: 'small' }, `Fórmula da quantidade: ${e.driver} (${e.unidade_driver}). Preparação: ${e.preparacao}.`),
      ex ? [h('p', { class: 'small' }, `Exemplo com ${ex.peca}: `, h('strong', null, ex.tempo_padrao_min !== null ? fmtMin(ex.tempo_padrao_min) : 'sem tempo')),
        h('ul', null, (ex.composicao || []).map((l) => h('li', { class: 'small' }, `${l.nome}: ${l.minutos !== null ? fmtMin(l.minutos) : '—'}`))),
        h('p', { class: 'muted small' }, ex.aviso)] : null,
      (e.premissas || []).length ? h('ul', null, e.premissas.map((p) => h('li', { class: 'small muted' }, p))) : null,
      m.justificativa ? h('p', { class: 'muted small' }, m.justificativa) : null,
      h('p', { class: 'muted small' }, `Proposta por ${m.origem === 'ia' ? (m.provedor || 'IA') : 'pessoa'} · versão ${m.versao}.`)));
}

export async function modulos(el) {
  const carregar = async () => {
    const [proprios, catalogo] = await Promise.all([get('/modulos/empresa'), get('/modulos')]);
    const pendentes = proprios.filter((m) => m.status === 'pendente');
    const emUso = proprios.filter((m) => m.vigente);
    const embutidos = catalogo.filter((m) => m.pacote !== 'empresa');
    const nome = h('input', { placeholder: 'Ex.: Lixar peças, Pintar, Embalar, Costurar barra' });
    const desc = h('textarea', { placeholder: 'Como é feito? Com qual equipamento? (opcional)' });
    montar(el,
      h('h1', null, 'Atividades'),
      h('p', { class: 'muted' }, 'O que a sua produção faz. Falta alguma? Descreva e a IA monta como o tempo é calculado; você confere e valida.'),
      h('div', { class: 'card' },
        h('label', null, 'Atividade', nome), h('label', null, 'Descrição', desc),
        h('div', { class: 'inline' }, h('button', { class: 'pri', onclick: async () => {
          if (!nome.value.trim()) return;
          if (await tentar(() => post('/modulos/propor', { nome: nome.value.trim(), descricao: desc.value.trim() }), 'Proposta pronta para conferir.')) carregar();
        } }, 'Montar com a IA'))),
      pendentes.length ? [h('h2', null, `Para conferir (${pendentes.length})`), pendentes.map((m) => cartao(m, carregar))] : null,
      emUso.length ? [h('h2', null, 'Em uso'), emUso.map((m) => cartao(m, carregar))] : null,
      detalhes(`Atividades que já vêm prontas (${embutidos.length})`,
        h('ul', null, embutidos.map((m) => h('li', { class: 'small' }, h('strong', null, m.titulo), ` — ${m.descricao}`)))));
  };
  await carregar();
}

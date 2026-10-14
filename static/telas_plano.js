import { api, baixar, del, get, patch, post, qs } from './api.js';
import { estado } from './estado.js';
import { avisoIA, badge, confirmar, detalhes, fmtData, fmtMin, fmtNum, h, kpi, modal, montar, statusBadge, tabela, tentar, toast } from './ui.js';

const num = (v) => (v === '' || v === null || v === undefined ? null : Number(v));
const METODOS = [['parafuso', 'Parafuso'], ['cavilha', 'Cavilha'], ['minifix', 'Minifix'], ['dobradica', 'Dobradiça'], ['corredica', 'Corrediça'],
  ['cola', 'Cola'], ['prego', 'Prego'], ['encaixe', 'Encaixe'], ['puxador', 'Puxador'], ['outro', 'Outro']];
const rotMetodo = (m) => (METODOS.find((x) => x[0] === m) || [m, m])[1];
const TIPO_PASSO = { movimentacao: 'Transporte', corte: 'Corte', furacao: 'Furação', bordo: 'Borda', montagem: 'Montagem', inspecao: 'Conferência', outro: 'Outro' };
const diaSem = (iso) => new Date(iso).toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: '2-digit' });
const hora = (iso) => new Date(iso).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
const dataChave = (iso) => new Date(iso).toLocaleDateString('pt-BR');

function entrada(tipo, valor, extra = {}) { return h('input', { type: tipo, value: valor ?? '', ...extra }); }

// ---------------------------------------------------------------- gerar / recalcular
const isoLocal = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);

export async function abrirGerar({ produtoId, produtoNome, plano }) {
  const cfg = plano?.config || {};
  const [un, perfis] = await Promise.all([get(`/unidades/${estado.unidadeId}`),
    estado.avancado ? get(`/perfis-mao-de-obra${qs({ unidade_id: estado.unidadeId, ativo: true })}`) : []]);
  const f = {
    qtd: entrada('number', plano?.quantidade ?? 1, { min: '0', step: 'any' }),
    ini: entrada('datetime-local', cfg.inicio ? isoLocal(new Date(cfg.inicio)) : isoLocal(new Date())),
    perfil: h('select', null, h('option', { value: '' }, 'Padrão'), perfis.map((x) => h('option', { value: x.id }, x.nome))),
    fadiga: entrada('number', cfg.fadiga_pct_hora ?? 0, { min: '0', max: '10', step: 'any' }),
  };
  if (cfg.perfil_id) f.perfil.value = cfg.perfil_id;
  const horario = (un.jornada?.blocos || []).map(([a, b]) => `${a}–${b}`).join(' e ');
  const corpo = h('div', null,
    h('div', { class: 'row' }, h('div', null, h('label', null, 'Quantas unidades?'), f.qtd), h('div', null, h('label', null, 'Quando começa?'), f.ini)),
    h('p', { class: 'muted small' }, `Equipe de ${un.equipe_pessoas ?? 1} pessoa(s), trabalhando ${horario || 'no horário padrão'}${un.jornada?.so_dias_uteis === false ? '' : ', de segunda a sexta'}. Altere na seção Agentes do item.`),
    estado.avancado ? detalhes('Opções de especialista', h('label', null, 'Perfil de mão de obra (ritmo do operador)'), f.perfil,
      h('label', null, 'Perda de rendimento por hora trabalhada no dia (%) — opcional, informe só se tiver medido'), f.fadiga) : null);
  modal(plano ? 'Recalcular plano' : `Plano de trabalho — ${produtoNome}`, corpo, { acoes: (fechar) => [h('button', { onclick: fechar }, 'Cancelar'),
    h('button', { class: 'pri', onclick: async (e) => {
      const corpoReq = { produto_id: produtoId, unidade_id: estado.unidadeId, quantidade: Number(f.qtd.value) || 1,
        inicio: f.ini.value ? new Date(f.ini.value).toISOString() : null, perfil_id: num(f.perfil.value), fadiga_pct_hora: Number(f.fadiga.value) || 0 };
      e.target.disabled = true;
      const r = await tentar(() => (plano ? post(`/planos/${plano.id}/recalcular`, corpoReq) : post('/planos', corpoReq)));
      e.target.disabled = false;
      if (r) { fechar(); if (plano) window.dispatchEvent(new HashChangeEvent('hashchange')); else location.hash = `#/planos/${r.id}`; }
    } }, plano ? 'Recalcular' : 'Gerar plano')] });
}

// ---------------------------------------------------------------- planos
export async function planos(el) {
  const [ps, prods] = await Promise.all([get(`/planos${qs({ unidade_id: estado.unidadeId })}`), get('/produtos?ativo=true')]);
  const itens = prods.filter((x) => x.tipo === 'produto');
  const nome = (id) => prods.find((x) => x.id === id)?.nome ?? '—';
  const escolha = h('select', null, h('option', { value: '' }, 'Escolha o item…'), itens.map((x) => h('option', { value: x.id }, x.nome)));
  const novo = itens.length
    ? h('div', { class: 'card' }, h('div', { class: 'row' }, escolha, h('button', { class: 'pri', onclick: () => {
      if (!escolha.value) return toast('Escolha o item.', true);
      location.hash = `#/itens/${escolha.value}`;
    } }, 'Novo plano: informar peças, agentes e ambiente')))
    : h('div', { class: 'card aviso-box' }, h('strong', null, 'Ainda não há item.'), ' ', h('a', { class: 'btn pri', href: '#/itens' }, 'Informar o item e as peças →'));
  montar(el, h('h1', null, 'Planos de trabalho'),
    h('p', { class: 'muted' }, 'Cada plano é uma sugestão calculada a partir do item, das peças, dos agentes e do ambiente que você informou. Só vale depois que você confirmar.'),
    novo,
    h('div', { class: 'card' }, tabela([
      { t: 'Plano', f: (p) => h('a', { href: `#/planos/${p.id}` }, p.nome) },
      { t: 'Situação', f: (p) => (p.status === 'rascunho' ? badge('Rascunho', 'b-warn') : p.status === 'cancelado' ? badge('Cancelado', 'b-err') : statusBadge(p.status)) },
      { t: 'Tempo de trabalho', f: (p) => fmtMin(p.totais.tempo_padrao_min) }, { t: 'Termina', f: (p) => fmtData(p.totais.fim) },
      { t: 'Pendências', f: (p) => (p.totais.completo ? badge('Completo', 'b-ok') : badge('Incompleto', 'b-warn')) },
      { t: 'Ordem', f: (p) => (p.ordem_id ? h('a', { href: `#/ordens/${p.ordem_id}` }, 'Ver ordem') : '—') }], ps, 'Nenhum plano ainda. Escolha um item acima.')));
}

export async function planoDetalhe(el, id) {
  const p = await get(`/planos/${id}`);
  const t = p.totais;
  const ops = p.passos;
  const recarregar = () => window.dispatchEvent(new HashChangeEvent('hashchange'));
  const alertas = [...p.alertas, ...ops.flatMap((s) => s.alertas.map((a) => ({ ...a, passo: s.nome })))];
  const vistos = new Set();
  const unicos = alertas.filter((a) => { const k = a.msg; if (vistos.has(k)) return false; vistos.add(k); return true; });

  let dia = null;
  const linhas = [];
  ops.forEach((s) => {
    if (s.inicio_prev) {
      const d = dataChave(s.inicio_prev);
      if (d !== dia) { dia = d; linhas.push(h('tr', { class: 'dia' }, h('td', { colspan: '6' }, diaSem(s.inicio_prev)))); }
    }
    const quem = [`${s.pessoas} pessoa${s.pessoas > 1 ? 's' : ''}`, s.recurso_nome, s.origem_nome && s.destino_nome && s.origem_nome !== s.destino_nome ? `${s.origem_nome} → ${s.destino_nome}` : (s.destino_nome || s.origem_nome)].filter(Boolean).join(' · ');
    linhas.push(h('tr', { class: s.tempo_padrao_min === null ? 'semtempo' : '' },
      h('td', null, s.sequencia),
      h('td', null, h('strong', null, s.nome), h('div', { class: 'muted small' }, `${TIPO_PASSO[s.tipo] || s.tipo} · ${quem}`),
        s.faltantes.length ? h('div', { class: 'warn-l small' }, `Falta: ${s.faltantes.join('; ')}`) : null,
        s.alertas.map((a) => h('div', { class: `small ${a.categoria === 'seguranca' ? 'seg-l' : 'warn-l'}` }, a.msg)),
        s.tolerancias.filter((t) => t.categoria.startsWith('ergonomia')).map((t) => h('div', { class: 'small erg-l' }, `Ergonomia: +${fmtNum(t.percentual, 1)}% de fadiga. ${t.justificativa}`)),
        estado.avancado ? detalhes('Como o tempo foi calculado', s.composicao.map((c) => h('div', { class: 'small' }, `${c.nome}: ${c.minutos === null ? c.motivo : `${fmtNum(c.minutos, 2)} min`}`)),
          s.elementos.map((e) => (e.justificativa ? h('div', { class: 'muted small' }, `• ${e.nome}: ${e.justificativa}`) : null))) : null),
      h('td', null, s.inicio_prev ? hora(s.inicio_prev) : '—'), h('td', null, s.fim_prev ? hora(s.fim_prev) : '—'),
      h('td', null, s.tempo_padrao_min === null ? badge('Sem tempo', 'b-warn') : fmtMin(s.tempo_padrao_min)),
      h('td', { class: 'noprint' }, s.tempo_prep_min ? h('span', { class: 'muted small' }, `preparo ${fmtMin(s.tempo_prep_min)}`) : '')));
  });

  const acoes = h('div', { class: 'inline noprint' },
    p.status === 'rascunho' ? h('button', { class: 'pri big', onclick: () => confirmar(t.completo
      ? 'Confirmar este plano? Os tempos passam a valer como plano de referência.'
      : 'Este plano tem pendências (passos sem tempo). Confirmar mesmo assim? Esses passos ficarão "sem base" na ordem.', async () => {
      if (await tentar(() => post(`/planos/${id}/confirmar`), 'Plano confirmado.')) recarregar();
    }, 'Confirmar plano') }, 'Confirmar plano') : null,
    p.status === 'confirmado' && !p.ordem_id ? h('button', { class: 'pri big', onclick: () => gerarOrdem(p) }, 'Gerar ordem de produção') : null,
    p.ordem_id ? h('a', { class: 'btn big', href: `#/ordens/${p.ordem_id}` }, 'Abrir a ordem') : null,
    p.status === 'rascunho' ? h('button', { onclick: () => abrirGerar({ produtoId: p.produto_id, produtoNome: p.produto_nome, plano: p }) }, 'Recalcular') : null,
    h('button', { onclick: () => window.print() }, 'Imprimir'),
    h('button', { onclick: () => tentar(() => baixar(`/planos/${id}/exportar.csv`, `plano-${id}.csv`)) }, 'Baixar planilha'),
    p.status !== 'cancelado' && !p.ordem_id ? h('button', { class: 'dng', onclick: () => confirmar('Cancelar este plano?', async () => { if (await tentar(() => post(`/planos/${id}/cancelar`))) recarregar(); }, 'Cancelar plano') }, 'Cancelar plano') : null);

  montar(el, h('p', { class: 'noprint' }, h('a', { href: '#/planos' }, '← Planos de trabalho')),
    h('h1', null, p.nome), h('div', { class: 'inline' }, p.status === 'rascunho' ? badge('Rascunho: falta você conferir e confirmar', 'b-warn') : statusBadge(p.status),
      badge(`Confiança: ${{ baixa: 'baixa', media: 'média', alta: 'alta' }[p.confianca]}`, p.confianca === 'baixa' ? 'b-warn' : ''), badge(p.provedor.startsWith('claude') ? 'Montado pela IA' : 'Montado por regras locais', 'b-ia')),
    (p.provedor.startsWith('claude') ? avisoIA : (txt) => h('div', { class: 'aviso-ia' }, h('strong', null, 'Sugestão automática. '), txt))('Este plano é uma estimativa. Tempos de montagem e conferência partem de referências genéricas até você informar os seus (seção Agentes do item) ou medir a produção. Quando houver apontamentos reais, compare com o previsto.'),
    h('div', { class: 'grid g4' }, kpi('Tempo de trabalho', fmtMin(t.tempo_padrao_min)), kpi('Pessoas-hora', `${fmtNum(t.horas_homem, 1)} h`),
      kpi('Começa', t.inicio ? fmtData(t.inicio) : '—', 'peq'), kpi('Termina', t.fim ? fmtData(t.fim) : '—', 'peq'), kpi('Dias de trabalho', t.dias || '—')),
    p.faltantes.length ? h('div', { class: 'aviso' }, h('strong', null, 'Para o plano ficar completo, faltam: '), h('ul', null, p.faltantes.map((f) => h('li', null, f))),
      h('div', { class: 'inline noprint' }, h('a', { class: 'btn pri', href: `#/itens/${p.produto_id}` }, 'Completar peças, agentes e ambiente'),
        p.status === 'rascunho' ? h('span', { class: 'muted small' }, 'Depois, use "Recalcular".') : null)) : null,
    unicos.length ? h('div', { class: 'card' }, h('h3', null, 'Atenção'), h('ul', null, unicos.map((a) => h('li', { class: a.categoria === 'seguranca' ? 'seg-l' : '' }, a.msg)))) : null,
    h('div', { class: 'card' }, h('div', { class: 'tw' }, h('table', null, h('thead', null, h('tr', null, ['#', 'Passo', 'Começa', 'Termina', 'Tempo', ''].map((x) => h('th', null, x)))), h('tbody', null, linhas)))),
    acoes,
    detalhes('Premissas do plano', h('ul', null, p.premissas.map((x) => h('li', { class: 'small' }, x)))));
}

function gerarOrdem(p) {
  const cliente = h('input', { placeholder: 'opcional' }); const prazo = h('input', { type: 'date' });
  modal('Gerar ordem de produção', h('div', null, h('p', { class: 'muted' }, 'A ordem usa os passos e tempos deste plano. Depois é só liberar e acompanhar na fila.'), h('label', null, 'Cliente'), cliente, h('label', null, 'Prazo'), prazo),
    { acoes: (fechar) => [h('button', { onclick: fechar }, 'Cancelar'), h('button', { class: 'pri', onclick: async () => {
      const r = await tentar(() => post(`/planos/${p.id}/gerar-ordem`, { cliente: cliente.value.trim() || null, prazo: prazo.value || null }), 'Ordem criada.');
      if (r) { fechar(); location.hash = `#/ordens/${r.id}`; }
    } }, 'Gerar ordem')] });
}

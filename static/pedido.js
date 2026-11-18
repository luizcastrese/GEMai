// Pedido em dois toques e o valor do trabalho, na língua do dono do negócio.
// "Comecei" / "Terminei" (ou "Levei X horas") mede o pedido inteiro; o sistema distribui pelos passos e aprende com isso.
import { get, post } from './api.js';
import { estado } from './estado.js';
import { fmtData, fmtMin, fmtNum, h, modal, montar, tentar, toast } from './ui.js';

const reais = (v) => (v === null || v === undefined ? '—' : Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }));

function resultado(r) {
  const d = r.desvio_pct;
  const frase = d === null || d === undefined ? '' : (Math.abs(d) < 5 ? 'Bem perto do previsto.' : d > 0 ? `Levou ${fmtNum(d, 0)}% a mais que o previsto.` : `Levou ${fmtNum(-d, 0)}% a menos que o previsto.`);
  toast(`Pedido encerrado: ${fmtMin(r.total_min)}. ${frase}${r.conferencia_pendente ? ' Outra pessoa da equipe precisa conferir o registro.' : ''}`);
}

function leveiHoras(o, depois) {
  const horas = h('input', { type: 'number', min: '0.1', step: '0.25', placeholder: 'ex.: 3,5', inputmode: 'decimal' });
  modal('Quanto tempo levou?', h('div', null, h('p', { class: 'muted' }, 'O tempo do começo ao fim deste pedido, em horas (pode ser aproximado).'), h('label', null, 'Horas'), horas),
    { acoes: (fechar) => [h('button', { onclick: fechar }, 'Cancelar'), h('button', { class: 'pri', onclick: async () => {
      const v = Number(String(horas.value).replace(',', '.'));
      if (!(v > 0)) return toast('Informe as horas.', true);
      const r = await tentar(() => post(`/ordens/${o.id}/terminar`, { horas: v }));
      if (r) { fechar(); resultado(r); depois(); }
    } }, 'Encerrar pedido')] });
}

// Cartão do pedido: o que fazer agora (começar, terminar) em um toque.
export function cartaoPedido(o, depois, { titulo } = {}) {
  const el = h('div', { class: 'card pedido' });
  const desenhar = () => {
    const aberto = ['planejada', 'liberada', 'em_producao', 'parada'].includes(o.status);
    const andando = o.status === 'em_producao' && o.iniciada_em;
    montar(el,
      h('h3', null, titulo || `Pedido ${o.numero}`, o.descricao ? h('span', { class: 'muted small' }, ` · ${o.descricao}`) : null),
      !aberto ? h('p', { class: 'muted' }, o.status === 'concluida' ? `Encerrado em ${fmtData(o.concluida_em)}.` : 'Pedido cancelado.')
        : h('div', null,
          h('p', { class: 'muted small' }, andando ? `Começou ${fmtData(o.iniciada_em)}.` : `Previsto: ${o.tempo_estimado_min ? fmtMin(o.tempo_estimado_min) : 'sem tempo'}.`),
          h('div', { class: 'inline btns' },
            andando ? h('button', { class: 'pri big', onclick: async () => {
              const r = await tentar(() => post(`/ordens/${o.id}/terminar`, {}));
              if (r) { resultado(r); depois(); }
            } }, '■ Terminei') : h('button', { class: 'pri big', onclick: async () => {
              const r = await tentar(() => post(`/ordens/${o.id}/comecar`), 'Bom trabalho! Toque em "Terminei" quando acabar.');
              if (r) { Object.assign(o, r); desenhar(); }
            } }, '▶ Comecei'),
            h('button', { onclick: () => leveiHoras(o, depois) }, 'Já terminei: levei X horas')),
          h('p', { class: 'muted small' }, 'Cada pedido medido deixa o próximo prazo mais certo.')));
  };
  desenhar();
  return el;
}

// Valor do trabalho e mensagem pronta para o cliente.
export function cartaoValor(p) {
  const t = p.totais || {};
  const c = p.custo_mao_de_obra;
  const prazo = t.fim ? fmtData(t.fim) : null;
  const texto = [`${p.produto_nome || p.nome}${p.variante ? ` (${p.variante})` : ''} × ${fmtNum(p.quantidade, 2)}`,
    prazo ? `Entrega prevista: ${prazo}.` : null,
    c ? `Mão de obra: a partir de ${reais(c.total)}${c.por_unidade !== null ? ` (${reais(c.por_unidade)} por unidade)` : ''}, mais material.` : null]
    .filter(Boolean).join('\n');
  const copiar = async () => {
    try { await navigator.clipboard.writeText(texto); toast('Mensagem copiada. É só colar no WhatsApp.'); } catch { modal('Mensagem para o cliente', h('textarea', { value: texto, rows: '5' })); }
  };
  return h('div', { class: 'card valor noprint' },
    h('h2', null, 'Prazo e valor'),
    prazo ? h('p', { class: 'big-txt' }, `Fica pronto em ${prazo}`, t.completo ? '' : ' (pode atrasar: há passos sem tempo)', '.') : null,
    c ? h('p', null, 'Mão de obra: ', h('strong', null, reais(c.total)), c.por_unidade !== null ? ` · ${reais(c.por_unidade)} por unidade` : '', ' + material.',
      h('div', { class: 'muted small' }, `${fmtNum(c.horas_homem, 1)} h de trabalho × ${reais(c.valor_hora)}/h.`))
      : h('p', { class: 'muted small' }, 'Diga quanto quer ganhar por hora em Configurações › Empresa e o sistema mostra o valor mínimo da mão de obra.'),
    h('button', { onclick: copiar }, 'Copiar mensagem para o cliente'));
}

export const temValorHora = () => !!estado.empresa?.valor_hora;

// "O que o real mostrou": corrigir o PADRÃO (calibrar) ou o FLUXO (ajustar o jeito de fazer), e as alternativas recalculadas.
const ACAO = { corrigir_fluxo: 'Ajustar o fluxo', corrigir_padrao: 'Ajustar o tempo', manter: 'Seguindo o padrão', medir_mais: 'Medir mais', medir_passo_a_passo: 'Medir passo a passo' };

export function cartaoCiclo(p, c) {
  const alt = h('div');
  const d = c.decisao;
  const ped = c.pedido;
  const gerarAjustado = async (escolha) => {
    const cfg = p.config || {};
    const corpo = { produto_id: p.produto_id, unidade_id: p.unidade_id, quantidade: p.quantidade, especificacoes: p.especificacoes || {},
      blocos: cfg.blocos || undefined, so_dias_uteis: cfg.so_dias_uteis ?? true, perfil_id: cfg.perfil_id ?? null, escolha };
    const r = await tentar(() => post('/planos/de-arranjo', corpo), 'Plano ajustado gerado. Confirme e meça o próximo pedido.');
    if (r) location.hash = `#/planos/${r.id}`;
  };
  const verAlternativas = async (ev) => {
    ev.target.disabled = true;
    const r = await tentar(() => get(`/planos/${p.id}/ciclo?alternativas=true`));
    ev.target.disabled = false;
    if (!r) return;
    montar(alt, r.alternativas.length ? h('div', null, h('p', { class: 'small muted' }, 'Calculadas pelo mesmo motor do plano (equipe, lotes, meio de movimentação):'),
      r.alternativas.map((x) => h('div', { class: 'lig' }, h('span', null, h('strong', null, x.principio), ` · ${x.rotulo}: termina em ${fmtMin(x.prazo_min)}, ${fmtNum(x.pessoas_hora, 1)} h de trabalho`),
        x.principio === 'Atual' ? null : h('button', { class: 'sm', onclick: () => gerarAjustado(x.escolha) }, 'Gerar plano assim'))))
      : h('p', { class: 'muted small' }, 'Sem alternativa de equipe, lotes ou meio que o motor consiga calcular com os dados atuais.'));
  };
  return h('div', { class: 'card ciclo noprint' },
    h('h2', null, 'O que o real mostrou'),
    ped && ped.medido ? h('p', null, `Previsto ${fmtMin(ped.previsto_min)} · levou ${fmtMin(ped.realizado_min)}`,
      ped.desvio_pct !== null ? ` (${ped.desvio_pct > 0 ? '+' : ''}${fmtNum(ped.desvio_pct, 0)}%)` : '', ped.forma === 'total' ? ' · medido no total' : ' · medido passo a passo') : null,
    h('p', { class: 'big-txt' }, h('strong', null, `${ACAO[d.acao] || d.acao}: `), d.texto),
    d.acao === 'corrigir_padrao' ? h('a', { class: 'btn pri', href: '#/calibracao' }, 'Ajustar meus tempos') : null,
    c.sugestoes.length ? h('div', null, h('h3', null, 'Como ajustar o jeito de fazer'),
      h('ul', null, c.sugestoes.map((s) => h('li', null, h('strong', null, `${s.principio}: `), s.texto, h('span', { class: 'muted small' }, ` (${s.etapa})`)))),
      h('p', { class: 'muted small' }, 'Depois de ajustar, meça o próximo pedido: o ciclo mostra se voltou ao padrão.'),
      h('button', { onclick: verAlternativas }, 'Ver alternativas recalculadas'), alt) : null,
    c.atividades.length ? h('details', { class: 'det' }, h('summary', null, 'Leitura de cada atividade'),
      h('ul', null, c.atividades.map((a) => h('li', { class: 'small' }, h('strong', null, `${a.etapa}: `), a.texto,
        a.pedidos ? h('span', { class: 'muted' }, ` · ${a.pedidos} pedido(s)${a.desvio_tipico_pct !== null ? `, desvio típico ${a.desvio_tipico_pct > 0 ? '+' : ''}${fmtNum(a.desvio_tipico_pct, 1)}%` : ''}`) : null))),
      h('p', { class: 'muted small' }, c.metodo)) : null);
}

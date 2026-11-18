// Pedido em dois toques e o valor do trabalho, na língua do dono do negócio.
// "Comecei" / "Terminei" (ou "Levei X horas") mede o pedido inteiro; o sistema distribui pelos passos e aprende com isso.
import { post } from './api.js';
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

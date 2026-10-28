import { get, qs } from './api.js';
import { estado } from './estado.js';
import { h, montar } from './ui.js';

// "Primeiros passos": Produto → Oficina → Plano → Conferir → Produzir (o servidor deduz o que já foi feito).
export async function carregarJornada() {
  try { return await get(`/jornada${qs({ unidade_id: estado.unidadeId })}`); } catch { return null; }
}

const bolinha = (p, atual) => h('span', { class: `bol${p.feito ? ' ok' : ''}${p.numero === atual ? ' at' : ''}`, 'aria-hidden': 'true' }, p.feito ? '✓' : p.numero);

// Cartão grande da tela inicial: todos os passos, o atual em destaque com botão.
export function cartaoJornada(j) {
  return h('div', { class: 'card jornada' }, h('h2', null, 'Comece por aqui: do produto à primeira ordem'),
    h('p', { class: 'muted' }, `${j.feitos} de ${j.total} passos feitos. Siga na ordem; cada passo leva uns minutos.`),
    h('ol', { class: 'passos' }, j.passos.map((p) => h('li', { class: p.feito ? 'fe' : p.numero === j.atual ? 'at' : 'fu' },
      bolinha(p, j.atual),
      h('div', { class: 'tx' }, h('strong', null, p.titulo, p.feito ? ' — feito' : ''),
        p.numero === j.atual ? [h('p', null, p.explicacao), h('a', { class: 'btn pri big', href: p.link }, `${p.botao} →`)] : null)))));
}

// Faixa no topo de cada tela do caminho: onde você está, o que fazer aqui e qual é o próximo passo.
// `texto` troca a explicação padrão; `proximo: false` esconde o botão "Próximo passo".
export async function faixa(codigo, { texto, proximo = true } = {}) {
  const j = await carregarJornada();
  const p = j?.passos.find((x) => x.codigo === codigo);
  if (!p) return null;
  const prox = proximo && p.feito && j.atual && j.atual > p.numero ? j.passos[j.atual - 1] : null;
  return h('div', { class: 'faixa' },
    h('div', { class: 'dots' }, j.passos.map((x) => {
      const corpo = [bolinha(x, p.numero), x.rotulo];
      const cls = x.codigo === codigo ? 'aqui' : '';
      return x.feito || x.codigo === codigo ? h('a', { href: x.link, class: cls }, corpo) : h('span', { class: 'd' }, corpo);
    })),
    h('div', { class: 'msg' }, h('strong', null, `Passo ${p.numero} de ${j.total}: ${p.titulo}${p.feito ? ' — feito ✓' : ''}`),
      texto || (p.feito ? 'Esta parte já está pronta. Você pode ajustar o que quiser aqui ou seguir para o próximo passo.' : p.explicacao)),
    prox ? h('a', { class: 'btn pri', href: prox.link }, `Próximo passo: ${prox.rotulo} →`)
      : (j.atual === null && proximo ? h('span', { class: 'badge b-ok' }, '✓ Você completou todos os passos') : null));
}

// Preenche (sem travar a tela) o espaço `el` com a faixa do passo.
export function faixaEm(el, codigo, opcoes) {
  faixa(codigo, opcoes).then((f) => montar(el, f)).catch(() => {});
}

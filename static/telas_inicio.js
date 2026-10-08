import { get, qs } from './api.js';
import { estado, ehGestor } from './estado.js';
import { fmtPct, h, kpi, montar, tentar } from './ui.js';

// Tela inicial: o que precisa de atenção agora, em linguagem comum.
export async function inicio(el) {
  if (!ehGestor()) { location.hash = '#/fila'; return; }
  const [r, d] = await Promise.all([get(`/inicio${qs({ unidade_id: estado.unidadeId })}`), tentar(() => get(`/dashboard${qs({ unidade_id: estado.unidadeId })}`))]);
  const n = r.numeros || {};
  const eff = d?.planejado_x_realizado?.eficiencia_pct;
  const real = eff ? Math.round((100 / eff - 1) * 100) : null;
  montar(el, h('h1', null, `Olá, ${estado.usuario.nome.split(' ')[0]}`),
    h('h2', null, 'O que precisa da sua atenção'),
    r.acoes.length ? r.acoes.map((a) => h('div', { class: `card acao ${a.nivel}` }, h('div', { class: 't' }, a.titulo),
      h('a', { class: 'btn', href: a.link }, a.codigo === 'configurar' ? 'Começar' : 'Ver')))
      : h('div', { class: 'card ok-box' }, h('strong', null, '✓ Tudo em dia.'), ' Nada pendente agora.'),
    h('div', { class: 'grid g4' },
      kpi('Ordens em andamento', n.ordens_abertas ?? 0),
      kpi('Ordens atrasadas', n.atrasadas ?? 0, n.atrasadas ? 'bad' : 'good'),
      kpi('Paradas em aberto', n.paradas_abertas ?? 0, n.paradas_abertas ? 'bad' : ''),
      kpi('Retrabalho (últimos 30 dias)', fmtPct(d?.retrabalho?.pct_do_tempo_de_trabalho)),
      real === null ? null : kpi('Tempo real × previsto', real === 0 ? 'No previsto' : `${real > 0 ? '+' : ''}${real}%`, real > 10 ? 'bad' : '')),
    h('h2', null, 'Atalhos'),
    h('div', { class: 'inline' }, h('a', { class: 'btn big', href: '#/ordens' }, 'Ordens de produção'), h('a', { class: 'btn big', href: '#/fila' }, 'Minha fila'),
      h('a', { class: 'btn big', href: '#/implantacao' }, 'Configurar com a IA')));
}

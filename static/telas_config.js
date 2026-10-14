import { definirAvancado, estado } from './estado.js';
import { h, montar } from './ui.js';
import * as admin from './telas_admin.js';

// Configurações: empresa, equipe, histórico e preferências, numa página só.
export async function configuracoes(el) {
  let aba = 'empresa';
  const abas = h('div', { class: 'tabs' }); const area = h('div');
  const desenhar = async () => {
    montar(abas, [['empresa', 'Empresa'], ['equipe', 'Equipe'], ['historico', 'Histórico de alterações'], ['preferencias', 'Preferências']].map(([k, r]) =>
      h('button', { class: aba === k ? 'on' : '', onclick: () => { aba = k; desenhar(); } }, r)));
    montar(area, h('p', { class: 'muted' }, 'Carregando…'));
    if (aba === 'empresa') await admin.empresa(area);
    else if (aba === 'equipe') await admin.usuarios(area);
    else if (aba === 'historico') await admin.auditoria(area);
    else preferencias(area);
  };
  montar(el, h('h1', null, 'Configurações'), abas, area);
  await desenhar();
}

function preferencias(area) {
  montar(area, h('div', { class: 'card' }, h('h2', null, 'Preferências'),
    h('label', { class: 'inline' }, h('input', { type: 'checkbox', checked: estado.avancado, onchange: (e) => { definirAvancado(e.target.checked); location.reload(); } }),
      'Mostrar detalhes técnicos'),
    h('p', { class: 'muted small' }, 'Mostra fórmulas, tolerâncias, composição do tempo, normas e as análises completas. Quem não precisa disso pode deixar desligado: tudo funciona do mesmo jeito.'),
    estado.avancado ? h('p', null, h('a', { class: 'btn', href: '#/cadastros' }, 'Cadastros avançados (perfis, pessoas, materiais)')) : null));
}

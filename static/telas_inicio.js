import { get, qs } from './api.js';
import { estado } from './estado.js';
import { fmtMin, h, montar, statusBadge, tabela, tempoPorUnidade } from './ui.js';

// Tela inicial: o caminho em 3 passos até o tempo padrão do trabalho.
// 1. Produto (o que fazer) → 2. Oficina (máquinas e espaço) → 3. Plano de trabalho (roteiro + tempo padrão).
export async function inicio(el) {
  const [produtos, c, planos] = await Promise.all([
    get('/produtos?ativo=true'), get(`/contorno${qs({ unidade_id: estado.unidadeId })}`), get(`/planos${qs({ unidade_id: estado.unidadeId })}`)]);
  const prods = produtos.filter((p) => p.tipo === 'produto');
  const oficinaOk = c.locais.length > 0 && c.pendentes === 0;
  const passo = (n, titulo, texto, feito, href, rotulo, extra) => h('div', { class: `card passo${feito ? ' feito' : ''}` },
    h('div', { class: 'num' }, feito ? '✓' : n),
    h('div', { class: 'corpo' }, h('h3', null, titulo), h('p', { class: 'muted' }, texto), extra ? h('p', { class: 'small' }, extra) : null),
    h('a', { class: `btn${feito ? '' : ' pri'}`, href }, rotulo));

  montar(el, h('h1', null, `Olá, ${estado.usuario.nome.split(' ')[0]}`),
    h('p', { class: 'muted' }, 'Três passos para saber quanto tempo leva.'),
    passo(1, 'O produto', 'O que você vai fazer.', prods.length > 0, '#/produtos',
      prods.length ? 'Ver produtos' : 'Cadastrar produto', prods.length ? `${prods.length} produto(s) cadastrado(s).` : null),
    passo(2, 'A oficina', 'Onde fica cada coisa e quais máquinas você tem.',
      oficinaOk, '#/contorno', oficinaOk ? 'Ver oficina' : 'Preencher oficina',
      c.pendentes ? `Faltam ${c.pendentes} informação(ões): ${c.faltando.slice(0, 2).join('; ')}${c.faltando.length > 2 ? '…' : ''}` : null),
    passo(3, 'O plano de trabalho', 'O tempo por unidade e o prazo.',
      planos.length > 0, '#/planos', planos.length ? 'Ver planos' : 'Gerar o primeiro plano', null),
    planos.length ? h('div', null, h('h2', null, 'Planos recentes'), h('div', { class: 'card' }, tabela([
      { t: 'Plano', f: (p) => h('a', { href: `#/planos/${p.id}` }, p.nome) },
      { t: 'Tempo por unidade', f: (p) => (tempoPorUnidade(p) !== null ? fmtMin(tempoPorUnidade(p)) : '—') },
      { t: 'Situação', f: (p) => (p.status === 'rascunho' ? 'Para conferir' : statusBadge(p.status)) }],
      planos.slice(0, 3)))) : null);
}

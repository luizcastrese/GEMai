import { get, qs } from './api.js';
import { estado } from './estado.js';
import { fmtData, fmtMin, h, montar, statusBadge, tabela } from './ui.js';

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
    h('p', { class: 'muted' }, 'Quanto tempo leva para fazer este produto? Em três passos o sistema monta o roteiro e calcula o tempo padrão, para você aceitar prazos sabendo o que está prometendo.'),
    passo(1, 'O produto', 'Diga o que vai fazer: escreva em texto livre ou liste as peças e como se juntam.', prods.length > 0, '#/produtos',
      prods.length ? 'Ver produtos' : 'Cadastrar produto', prods.length ? `${prods.length} produto(s) cadastrado(s).` : null),
    passo(2, 'A oficina', 'Onde as coisas ficam, a distância entre os locais e as máquinas. Não sabe quanto a máquina produz por hora? A IA estima por descrição ou foto.',
      oficinaOk, '#/contorno', oficinaOk ? 'Ver oficina' : 'Preencher oficina',
      c.pendentes ? `Faltam ${c.pendentes} informação(ões): ${c.faltando.slice(0, 2).join('; ')}${c.faltando.length > 2 ? '…' : ''}` : null),
    passo(3, 'O plano de trabalho', 'Com o produto e a oficina, o sistema propõe o roteiro e calcula o tempo padrão por unidade e o prazo realista.',
      planos.length > 0, '#/planos', planos.length ? 'Ver planos' : 'Gerar o primeiro plano', null),
    planos.length ? h('div', null, h('h2', null, 'Planos recentes'), h('div', { class: 'card' }, tabela([
      { t: 'Plano', f: (p) => h('a', { href: `#/planos/${p.id}` }, p.nome) },
      { t: 'Tempo padrão por unidade', f: (p) => (p.totais.completo || p.totais.tempo_padrao_min ? fmtMin(p.totais.tempo_padrao_min / (p.quantidade || 1)) : '—') },
      { t: 'Termina', f: (p) => fmtData(p.totais.fim) }, { t: 'Situação', f: (p) => (p.status === 'rascunho' ? 'Para conferir' : statusBadge(p.status)) }],
      planos.slice(0, 5)))) : null);
}

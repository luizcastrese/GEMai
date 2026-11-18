import { get, qs } from './api.js';
import { estado } from './estado.js';
import { fmtMin, h, montar, statusBadge, tabela, tempoPorUnidade } from './ui.js';
import { cartaoPedido } from './pedido.js';

// Tela inicial: o caminho até o tempo padrão e o ciclo que o melhora, para qualquer tipo de produção.
// 1. O que se produz → 2. O que se faz (atividades) → 3. Onde e com o quê → 4. Plano → 5. Medir o real → 6. Comparar.
export async function inicio(el) {
  const u = estado.unidadeId;
  const [produtos, c, planos, atividades, calibracoes] = await Promise.all([
    get('/produtos?ativo=true'), get(`/contorno${qs({ unidade_id: u })}`), get(`/planos${qs({ unidade_id: u })}`), get('/modulos'),
    get(`/calibracao/modulos${qs({ unidade_id: u })}`).catch(() => [])]);
  const andamento = (await get(`/ordens${qs({ unidade_id: u, status: 'planejada,liberada,em_producao,parada' })}`).catch(() => [])).filter((o) => o.plano_id);
  const recarregar = () => inicio(el);
  const prods = produtos.filter((p) => p.tipo === 'produto');
  const localOk = c.locais.length > 0 && c.pendentes === 0;
  const daEmpresa = atividades.filter((m) => m.pacote === 'empresa').length;
  const comOrdem = planos.filter((p) => p.ordem_id).length;
  const passo = (n, titulo, texto, feito, href, rotulo, extra) => h('div', { class: `card passo${feito ? ' feito' : ''}` },
    h('div', { class: 'num' }, feito ? '✓' : n),
    h('div', { class: 'corpo' }, h('h3', null, titulo), h('p', { class: 'muted' }, texto), extra ? h('p', { class: 'small' }, extra) : null),
    h('a', { class: `btn${feito ? '' : ' pri'}`, href }, rotulo));

  const configurado = prods.length > 0 && atividades.length > 0 && localOk;
  const etapa = (nome, texto, href, rotulo, ativo) => h('a', { class: `etapa-ciclo${ativo ? ' on' : ''}`, href }, h('strong', null, nome), h('span', { class: 'muted small' }, texto), h('span', { class: 'small' }, `${rotulo} →`));
  montar(el, h('h1', null, `Olá, ${estado.usuario.nome.split(' ')[0]}`),
    h('p', { class: 'muted' }, configurado ? 'Tudo configurado. A cada pedido: gere o plano, meça e veja o que o real mostrou.' : 'Configure uma vez; depois, a cada pedido, o tempo fica mais certo.'),
    andamento.length ? h('div', null, h('h2', null, `Pedidos em andamento (${andamento.length})`), andamento.slice(0, 5).map((o) => cartaoPedido(o, recarregar))) : null,
    h('h2', null, 'A cada pedido'),
    h('div', { class: 'ciclo-passos' },
      etapa('Plano', 'Prazo, valor e passos do pedido.', '#/planos', planos.length ? 'Ver planos' : 'Gerar o primeiro', true),
      etapa('Medir', 'Toque em ▶ Comecei e ■ Terminei.', '#/ordens', comOrdem ? `${comOrdem} pedido(s)` : 'Ver pedidos', comOrdem > 0),
      etapa('O que o real mostrou', 'Ajustar o tempo ou o jeito de fazer.', '#/calibracao', 'Ajustar meus tempos', calibracoes.some((x) => x.vigente))),
    h('h2', null, configurado ? 'Configuração (feita)' : 'Configurar (uma vez)'),
    passo(1, 'O que você produz', 'Os produtos e seus itens (medidas, peso e outros dados).', prods.length > 0, '#/produtos',
      prods.length ? 'Ver produtos' : 'Cadastrar produto', prods.length ? `${prods.length} produto(s) cadastrado(s).` : null),
    passo(2, 'O que você faz', 'As atividades da sua produção. Falta alguma? A IA monta e você valida.', atividades.length > 0, '#/atividades',
      'Ver atividades', `${atividades.length} atividade(s) disponível(is)${daEmpresa ? `, ${daEmpresa} criada(s) por vocês` : ''}.`),
    passo(3, 'Onde e com o quê', 'Os locais, a distância entre eles e o que suas máquinas fazem por minuto.',
      localOk, '#/contorno', localOk ? 'Ver local de produção' : 'Preencher',
      c.pendentes ? `Faltam ${c.pendentes} informação(ões): ${c.faltando.slice(0, 2).join('; ')}${c.faltando.length > 2 ? '…' : ''}` : null),
    planos.length ? h('div', null, h('h2', null, 'Planos recentes'), h('div', { class: 'card' }, tabela([
      { t: 'Plano', f: (p) => h('a', { href: `#/planos/${p.id}` }, p.nome) },
      { t: 'Tempo por unidade', f: (p) => (tempoPorUnidade(p) !== null ? fmtMin(tempoPorUnidade(p)) : '—') },
      { t: 'Situação', f: (p) => (p.status === 'rascunho' ? 'Para conferir' : statusBadge(p.status)) }],
      planos.slice(0, 3)))) : null);
}

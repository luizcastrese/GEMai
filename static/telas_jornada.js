import { api, del, get, patch, post, qs } from './api.js';
import { estado } from './estado.js';
import { badge, detalhes, fmtNum, h, montar, tentar, toast } from './ui.js';

// Trilha guiada: Atividades → Entradas → Agentes transformadores → Ambiente → Plano.
// A pessoa nunca escolhe o que fazer a seguir: cada etapa só abre quando a anterior está completa,
// e a lista de pendências diz exatamente o que falta. As regras vivem em app/services/jornada.py.

const num = (v) => (v === '' || v === null || v === undefined ? null : Number(v));
export const carregarTrilha = () => get(`/jornada${qs({ unidade_id: estado.unidadeId })}`);

const REF_ROTULOS = { conferencia_final: 'Conferência final de cada unidade', 'fixador:parafuso': 'Colocar 1 parafuso', 'fixador:cavilha': 'Colocar 1 cavilha',
  'fixador:minifix': 'Colocar 1 minifix', 'fixador:dobradica': 'Instalar 1 dobradiça', 'fixador:corredica': 'Instalar 1 corrediça', 'fixador:cola': 'Colar 1 junção',
  'fixador:prego': 'Pregar 1 prego', 'fixador:encaixe': 'Fazer 1 encaixe', 'fixador:puxador': 'Instalar 1 puxador', 'fixador:outro': 'Outro tipo de fixação (1 un.)' };
const TIPOS_LOCAL = [['area', 'Área de trabalho'], ['estoque', 'Estoque (início)'], ['montagem', 'Montagem'], ['posto', 'Posto'], ['expedicao', 'Expedição']];

// ---------------------------------------------------------------- estrutura comum
const marca = { concluido: '✓', atual: '●', bloqueado: '🔒' };

/** Faixa com as quatro etapas, sempre no topo da preparação. */
export function faixaTrilha(j, atual) {
  return h('ol', { class: 'trilha', 'aria-label': 'Etapas da preparação' }, j.passos.map((p) => {
    const conteudo = [h('span', { class: 'n' }, p.estado === 'concluido' ? '✓' : p.numero), h('span', { class: 't' }, p.titulo)];
    const cls = `${p.estado}${p.codigo === atual ? ' aqui' : ''}`;
    return h('li', { class: cls }, p.estado === 'bloqueado' ? h('span', { title: 'Complete a etapa anterior' }, conteudo) : h('a', { href: p.rota }, conteudo));
  }));
}

/** Caixa de pendências: o que falta e, quando nada falta, o botão para a próxima etapa. */
export function caixaPendencias(passo, proxima) {
  if (passo.pendencias.length) {
    return h('div', { class: 'card aviso-box' }, h('strong', null, 'Para continuar, falta:'), h('ul', null, passo.pendencias.map((t) => h('li', null, t))),
      h('button', { class: 'pri big', disabled: true }, proxima ? `Continuar para ${proxima.titulo}` : 'Continuar'));
  }
  return h('div', { class: 'card ok-box' }, h('strong', null, `✓ ${passo.titulo} completo.`), ' ',
    h('a', { class: 'btn pri big', href: proxima ? proxima.rota : '#/planos' }, proxima ? `Continuar: ${proxima.titulo} →` : 'Ir para o plano de trabalho →'));
}

/**
 * Monta uma etapa. `construir(j, ctx)` devolve os blocos do miolo; `ctx.recarregar()` refaz tudo,
 * `ctx.atualizar()` refaz só a faixa e a caixa de pendências (sem perder o que está sendo digitado).
 */
async function etapa(el, codigo, construir) {
  const j0 = await carregarTrilha();
  const alvo = j0.passos.find((p) => p.codigo === codigo);
  if (alvo.estado === 'bloqueado') {
    const aberta = j0.passos.find((p) => !p.completo);
    toast(`Antes, termine a etapa ${aberta.numero}: ${aberta.titulo}.`, true);
    location.hash = aberta.rota;
    return;
  }
  const [faixa, cabeca, miolo, rodape] = [h('div'), h('div'), h('div'), h('div')];
  montar(el, faixa, cabeca, miolo, rodape);
  const ctx = {};
  const atualizar = async () => {
    const j = await carregarTrilha();
    estado.trilha = j;
    const p = j.passos.find((x) => x.codigo === codigo);
    montar(faixa, faixaTrilha(j, codigo));
    montar(cabeca, h('h1', null, `Etapa ${p.numero} — ${p.titulo}`), h('p', { class: 'pergunta' }, p.pergunta));
    montar(rodape, caixaPendencias(p, j.passos[p.numero]));
    ctx.j = j;
    return j;
  };
  ctx.atualizar = atualizar;
  ctx.recarregar = async () => { const j = await atualizar(); montar(miolo, await construir(j, ctx)); };
  await ctx.recarregar();
}

/** `#/preparar`: leva direto à etapa em que a unidade está. */
export async function preparar() {
  const j = await carregarTrilha();
  const aberta = j.passos.find((p) => !p.completo);
  location.hash = aberta ? aberta.rota : '#/planos';
}

const aviso = (txt) => h('p', { class: 'muted' }, txt);
const secao = (titulo, ajuda, ...filhos) => h('div', { class: 'card' }, h('h2', null, titulo), ajuda ? h('p', { class: 'muted small' }, ajuda) : null, ...filhos);
const campoNum = (valor, aoMudar, extra = {}) => {
  const i = h('input', { type: 'number', min: '0', step: 'any', value: valor ?? '', ...extra });
  i.addEventListener('change', () => aoMudar(i.value === '' ? null : Number(i.value)));
  return i;
};

// ---------------------------------------------------------------- 1. Atividades
export const atividades = (el) => etapa(el, 'atividades', (j) => {
  const marcadas = new Set(j.atividades ?? j.catalogo.map((a) => a.codigo)); // sugestão inicial: todas; a pessoa tira o que não faz
  const caixas = j.catalogo.map((a) => ({ a, c: h('input', { type: 'checkbox', checked: marcadas.has(a.codigo), id: `at-${a.codigo}` }) }));
  const salvar = async () => {
    const lista = caixas.filter((x) => x.c.checked).map((x) => x.a.codigo);
    if (!lista.length) return toast('Marque ao menos uma atividade.', true);
    if (await tentar(() => patch(`/unidades/${estado.unidadeId}`, { atividades: lista }), 'Atividades salvas.')) {
      const nova = await carregarTrilha();
      location.hash = nova.passos[1].rota;
    }
  };
  return [
    secao('O que a sua operação faz?', 'Marque as atividades que acontecem entre o estoque e o produto pronto. Cada uma indica o que vai ser pedido nas próximas etapas.',
      h('div', { class: 'atividades' }, caixas.map(({ a, c }) => h('label', { class: 'atividade', for: `at-${a.codigo}` }, c,
        h('div', null, h('strong', null, a.titulo), h('div', { class: 'muted small' }, a.descricao),
          h('div', { class: 'precisa small' }, h('span', null, `Entradas: ${a.entradas}`), h('span', null, `Agentes: ${a.agentes}`), h('span', null, `Ambiente: ${a.ambiente}`)))))),
      h('p', null, h('button', { class: 'pri big', onclick: salvar }, j.atividades ? 'Salvar e continuar' : 'Confirmar atividades e continuar'))),
  ];
});

// ---------------------------------------------------------------- 2. Entradas
export const entradas = (el) => etapa(el, 'entradas', async (j) => {
  const produtos = (await get('/produtos?ativo=true')).filter((p) => p.tipo === 'produto');
  const nome = h('input', { placeholder: 'ex.: Armário de cozinha' });
  const criar = async () => {
    if (!nome.value.trim()) return toast('Digite o nome do produto.', true);
    const r = await tentar(() => post('/produtos', { nome: nome.value.trim(), tipo: 'produto' }));
    if (r) location.hash = `#/preparar/entradas/${r.id}`;
  };
  return [
    secao('Produto', 'Entrada = o que vira produto: as peças, o material, as medidas e como elas se ligam. Abra o produto para preenchê-lo (ou descreva em texto e deixe a IA propor a lista).',
      produtos.length ? produtos.map((p) => {
        const pend = j.pendencias_produto[String(p.id)] || [];
        return h('div', { class: 'linha-prod' }, h('div', null, h('a', { href: `#/preparar/entradas/${p.id}`, class: 'big-txt' }, p.nome),
          pend.length ? h('ul', { class: 'small warn-l' }, pend.slice(0, 4).map((t) => h('li', null, t))) : h('div', { class: 'small' }, badge('Pronto para planejar', 'b-ok'))),
          h('a', { class: pend.length ? 'btn pri' : 'btn', href: `#/preparar/entradas/${p.id}` }, pend.length ? 'Completar' : 'Revisar'));
      }) : aviso('Nenhum produto ainda. Crie o primeiro abaixo.'),
      h('div', { class: 'row' }, nome, h('button', { class: 'pri', onclick: criar }, '+ Criar produto'))),
  ];
});

// ---------------------------------------------------------------- 3. Agentes transformadores
export const agentes = (el) => etapa(el, 'agentes', async (j, ctx) => {
  const un = await get(`/unidades/${estado.unidadeId}`);
  const [recursos, refs] = await Promise.all([get(`/recursos${qs({ unidade_id: estado.unidadeId })}`), get('/referencias-tempo')]);
  const ativos = recursos.filter((r) => r.ativo);

  // ---- mão de obra
  const bl = un.jornada?.blocos ?? [['08:00', '12:00'], ['13:00', '17:00']];
  const f = {
    pessoas: h('input', { type: 'number', min: '1', max: '50', step: '1', value: un.equipe_pessoas ?? '', placeholder: 'ex.: 3' }),
    m1: h('input', { type: 'time', value: bl[0]?.[0] ?? '' }), m2: h('input', { type: 'time', value: bl[0]?.[1] ?? '' }),
    t1: h('input', { type: 'time', value: bl[1]?.[0] ?? '' }), t2: h('input', { type: 'time', value: bl[1]?.[1] ?? '' }),
    uteis: h('input', { type: 'checkbox', checked: un.jornada?.so_dias_uteis ?? true }),
  };
  const salvarEquipe = async () => {
    const blocos = [[f.m1.value, f.m2.value], [f.t1.value, f.t2.value]].filter((b) => b[0] && b[1]);
    if (!f.pessoas.value || Number(f.pessoas.value) < 1) return toast('Informe quantas pessoas trabalham.', true);
    if (!blocos.length) return toast('Informe ao menos um bloco de horário.', true);
    if (await tentar(() => patch(`/unidades/${estado.unidadeId}`, { equipe_pessoas: Number(f.pessoas.value), jornada: { blocos, so_dias_uteis: f.uteis.checked } }), 'Mão de obra salva.')) ctx.recarregar();
  };
  const maoDeObra = secao('Mão de obra', 'As pessoas que executam as atividades. O horário define quando cada passo do plano começa e termina.',
    h('div', { class: 'row' }, h('div', null, h('label', null, 'Quantas pessoas trabalham juntas?'), f.pessoas)),
    h('div', { class: 'row' }, h('div', null, h('label', null, 'Manhã: das'), f.m1), h('div', null, h('label', null, 'até'), f.m2),
      h('div', null, h('label', null, 'Tarde: das'), f.t1), h('div', null, h('label', null, 'até'), f.t2)),
    h('label', { class: 'inline' }, f.uteis, ' Trabalhar só de segunda a sexta'),
    h('p', null, h('button', { class: 'pri', onclick: salvarEquipe }, un.equipe_pessoas ? 'Salvar mão de obra' : 'Confirmar mão de obra')));

  // ---- uma máquina por atividade que precisa de equipamento
  const doTipo = j.catalogo.filter((a) => a.funcao && j.atividades?.includes(a.codigo));
  const blocoMaquina = (a) => {
    const lista = ativos.filter((r) => r.funcao === a.funcao);
    const nomeNovo = h('input', { placeholder: `ex.: ${a.funcao === 'corte' ? 'Seccionadora' : a.funcao === 'bordo' ? 'Coladeira de borda' : 'Furadeira'}` });
    const capNova = h('input', { type: 'number', min: '0', step: 'any', placeholder: 'peças por hora' });
    const adicionar = async () => {
      if (!nomeNovo.value.trim()) return toast('Digite o nome da máquina.', true);
      if (await tentar(() => post('/recursos', { unidade_id: estado.unidadeId, nome: nomeNovo.value.trim(), tipo: 'maquina', funcao: a.funcao,
        capacidade: num(capNova.value), capacidade_unidade: 'un/h' }), 'Máquina cadastrada.')) ctx.recarregar();
    };
    return h('div', { class: 'maquina' }, h('h3', null, a.titulo), h('p', { class: 'muted small' }, `Qual máquina faz ${a.titulo.toLowerCase()} e quantas peças por hora ela faz?`),
      lista.map((r) => h('div', { class: 'row' }, h('div', null, h('label', null, 'Máquina'), h('input', { value: r.nome, onchange: async (e) => { if (e.target.value.trim()) { await tentar(() => patch(`/recursos/${r.id}`, { nome: e.target.value.trim() }), 'Salvo.'); } } })),
        h('div', null, h('label', null, 'Peças por hora'), campoNum(r.capacidade, async (v) => { if (await tentar(() => patch(`/recursos/${r.id}`, { capacidade: v, capacidade_unidade: 'un/h' }), 'Salvo.') !== undefined) ctx.atualizar(); }, { placeholder: 'ex.: 60' })),
        h('button', { class: 'sm dng', title: 'Remover', onclick: async () => { if (await tentar(() => patch(`/recursos/${r.id}`, { ativo: false }))) ctx.recarregar(); } }, '✕'))),
      h('div', { class: 'row' }, nomeNovo, capNova, h('button', { onclick: adicionar }, lista.length ? '+ Outra máquina' : '+ Adicionar máquina')));
  };
  const maquinas = doTipo.length
    ? secao('Máquinas', 'Uma para cada atividade que usa equipamento. A capacidade (peças por hora) é o que permite a IA calcular o tempo de máquina.', doTipo.map(blocoMaquina))
    : secao('Máquinas', null, aviso('As atividades escolhidas são todas feitas por pessoas: nenhuma máquina é necessária.'));

  // ---- opcional: tempos da oficina
  const tempos = detalhes('Opcional: tempos de montagem da sua oficina',
    h('div', { class: 'card' }, h('p', { class: 'muted small' }, 'Valores genéricos de partida. Troque pelos da sua oficina (em minutos): o plano passa a usá-los e avisa que são seus.'),
      refs.map((r) => h('div', { class: 'row ref' }, h('div', { class: 'l' }, REF_ROTULOS[r.chave] || r.chave,
        h('span', { class: 'muted small' }, r.informada ? ` (seu valor; padrão ${fmtNum(r.padrao_minutos, 2)} min)` : ' (valor genérico)')),
        campoNum(r.minutos, async (v) => { if (v !== null && await tentar(() => api('PUT', '/referencias-tempo', { chave: r.chave, minutos: v }), 'Salvo.')) ctx.recarregar(); }),
        r.informada ? h('button', { class: 'sm', onclick: async () => { if (await tentar(() => del(`/referencias-tempo/${encodeURIComponent(r.chave)}`))) ctx.recarregar(); } }, 'Voltar ao padrão') : h('span')))));
  return [maoDeObra, maquinas, tempos];
});

// ---------------------------------------------------------------- 4. Ambiente
export const ambiente = (el) => etapa(el, 'ambiente', async (j, ctx) => {
  const c = await get(`/contorno${qs({ unidade_id: estado.unidadeId })}`);
  const [locais, equip] = [c.locais, c.equipamentos];
  const usam = new Set(j.catalogo.filter((a) => a.funcao && j.atividades?.includes(a.codigo)).map((a) => a.funcao));
  const maquinas = equip.filter((e) => usam.has(e.funcao));
  const criarLocal = async (nome, tipo = 'area') => { if (await tentar(() => post('/espacos', { unidade_id: estado.unidadeId, nome, tipo }))) ctx.recarregar(); };
  const tem = (tipo, palavra) => locais.some((l) => l.tipo === tipo || l.nome.toLowerCase().includes(palavra));
  const falta = [];
  if (j.atividades?.includes('movimentacao') && !tem('estoque', 'estoque')) falta.push(['Estoque', 'estoque']);
  if ((j.atividades?.includes('montagem') || j.atividades?.includes('inspecao')) && !tem('montagem', 'montag')) falta.push(['Montagem', 'montagem']);

  // ---- locais
  const novo = h('input', { placeholder: 'ex.: Bancada de corte' });
  const tipoNovo = h('select', { 'aria-label': 'Tipo do local' }, TIPOS_LOCAL.map(([v, r]) => h('option', { value: v }, r)));
  const sLocais = secao('Locais', 'Os lugares por onde a peça passa. Estoque e montagem são obrigatórios; o resto depende das máquinas.',
    falta.length ? h('div', { class: 'inline' }, falta.map(([n, t]) => h('button', { class: 'pri', onclick: () => criarLocal(n, t) }, `+ Criar “${n}”`))) : null,
    locais.map((l) => h('div', { class: 'row' }, h('input', { value: l.nome, 'aria-label': 'Nome do local', onchange: async (e) => { if (e.target.value.trim() && await tentar(() => patch(`/espacos/${l.id}`, { nome: e.target.value.trim() }), 'Salvo.')) ctx.atualizar(); } }),
      (() => { const t = h('select', { 'aria-label': 'Tipo do local', onchange: async (e) => { if (await tentar(() => patch(`/espacos/${l.id}`, { tipo: e.target.value }))) ctx.recarregar(); } }, TIPOS_LOCAL.map(([v, r]) => h('option', { value: v }, r))); t.value = l.tipo; return t; })(),
      h('button', { class: 'sm dng', title: 'Remover', onclick: async () => { if (await tentar(() => patch(`/espacos/${l.id}`, { ativo: false }))) ctx.recarregar(); } }, '✕'))),
    h('div', { class: 'row' }, novo, tipoNovo, h('button', { onclick: () => { if (!novo.value.trim()) return toast('Digite o nome do local.', true); criarLocal(novo.value.trim(), tipoNovo.value); } }, '+ Adicionar local')));

  // ---- onde fica cada máquina
  const sOnde = secao('Onde fica cada máquina', maquinas.length ? null : 'As atividades escolhidas não usam máquina.',
    maquinas.map((m) => h('div', { class: 'row' }, h('div', { class: 'l' }, h('strong', null, m.nome)),
      (() => { const s = h('select', { 'aria-label': `Local de ${m.nome}`, onchange: async (e) => { if (await tentar(() => patch(`/recursos/${m.id}`, { espaco_id: num(e.target.value) }), 'Salvo.') !== undefined) ctx.recarregar(); } },
        h('option', { value: '' }, 'Escolha o local…'), locais.map((l) => h('option', { value: l.id }, l.nome))); s.value = m.espaco_id ?? ''; return s; })())));

  // ---- distâncias
  const sDist = j.atividades?.includes('movimentacao') ? secao('Distância entre os locais (em metros)', 'Só as distâncias que o transporte das peças realmente usa.',
    c.distancias.length ? c.distancias.map((d) => h('div', { class: 'row' }, h('div', { class: 'l' }, `${d.origem} ↔ ${d.destino}`),
      campoNum(d.metros, async (v) => { if (v !== null && await tentar(() => api('PUT', '/distancias', { origem_id: d.origem_id, destino_id: d.destino_id, metros: v }), 'Salvo.') !== undefined) ctx.recarregar(); }, { placeholder: 'metros' })))
      : aviso('Aparecem aqui quando houver estoque, locais de máquina e montagem cadastrados.')) : null;

  // ---- opcional: condições
  const sCond = detalhes('Opcional: condições do ambiente (calor, ruído) em cada local',
    h('div', { class: 'card' }, h('p', { class: 'muted small' }, 'Se informar, o plano alerta quando passar de limites de referência. A “folga extra” (%) aumenta o tempo dos passos feitos naquele local; só use se souber o valor.'),
      locais.length ? locais.map((l) => h('div', { class: 'row' }, h('div', { class: 'l' }, l.nome),
        [['temperatura_c', 'Temperatura (°C)', l.temperatura_c], ['ruido_db', 'Ruído (dB)', l.ruido_db], ['tolerancia_ambiente_pct', 'Folga extra (%)', l.tolerancia_ambiente_pct]].map(([k, rot, v]) =>
          h('div', null, h('label', null, rot), campoNum(v, async (n) => { await tentar(() => patch(`/espacos/${l.id}`, { [k]: n }), 'Salvo.'); })))))
        : aviso('Cadastre os locais primeiro.')));
  return [sLocais, sOnde, sDist, sCond];
});

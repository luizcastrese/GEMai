import { api, get, patch, post, qs } from './api.js';
import { estado } from './estado.js';
import { h, montar, tentar, toast } from './ui.js';
import { secaoMeios } from './telas_meios.js';

const num = (v) => (v === '' || v === null || v === undefined ? null : Number(v));
const opcoes = (lista, vazio) => [h('option', { value: '' }, vazio), ...lista.map((x) => h('option', { value: x.id }, x.nome))];
const seletor = (lista, valor, vazio, aoMudar) => {
  const s = h('select', { onchange: (e) => aoMudar(num(e.target.value)) }, opcoes(lista, vazio));
  s.value = valor ?? '';
  return s;
};

const TIPOS_LOCAL = [['area', 'Outro / área de trabalho'], ['estoque', 'Estoque (início)'], ['montagem', 'Montagem'], ['posto', 'Posto'], ['expedicao', 'Expedição']];
const FUNCOES = [['', 'Não informado'], ['corte', 'Cortar'], ['bordo', 'Colar borda'], ['furacao', 'Furar'], ['movimentacao', 'Movimentar peças'], ['acabamento', 'Acabamento'], ['montagem', 'Montagem'], ['outro', 'Outro']];
// Contorno físico MÍNIMO: onde as coisas ficam, a que distância, a ficha técnica de cada meio e quanto pesa a peça.
export async function contorno(el) {
  const uid = estado.unidadeId;
  const topo = h('div'); const secoes = h('div');
  montar(el, h('h1', null, 'Contorno físico'),
    h('p', { class: 'muted' }, 'Só o essencial para calcular o tempo: onde as coisas ficam, a que distância, a ficha técnica de cada equipamento e quanto pesa cada peça. O tempo nunca é digitado. Tudo é salvo ao preencher.'),
    topo, secoes);

  const progresso = async () => {
    const c = await get(`/contorno${qs({ unidade_id: uid })}`);
    const barra = h('div', { class: 'bar' }, h('i')); barra.firstChild.style.width = `${c.progresso_pct}%`;
    montar(topo, h('div', { class: c.completo ? 'card ok-box' : 'card' },
      c.completo ? h('div', null, h('strong', null, '✓ Contorno físico completo.'), ' A IA já consegue prever o tempo. ', h('a', { class: 'btn', href: '#/planos' }, 'Ir para os planos de trabalho'), ' ', h('a', { class: 'btn', href: '#/processos' }, 'Ir para os processos'))
        : h('div', null, h('strong', null, `${c.progresso_pct}% preenchido`), c.tarefas.length ? ` — faltam ${c.pendentes} informação(ões):` : ' — crie um processo primeiro (Configurar com a IA).',
          c.faltando.length ? h('ul', null, c.faltando.slice(0, 6).map((f) => h('li', null, f)), c.faltando.length > 6 ? h('li', { class: 'muted' }, `e mais ${c.faltando.length - 6}…`) : null) : null),
      barra));
    return c;
  };
  const salvar = async (fn) => { const r = await tentar(fn); if (r !== undefined) { await progresso(); toast('Salvo.'); } };

  const desenhar = async () => {
    const c = await progresso();
    const [locais, equip, pecas] = [c.locais, c.equipamentos, c.pecas];

    // ---- 1. locais
    const novoLocal = h('input', { placeholder: 'ex.: Estoque de chapas' });
    const sLocais = h('div', { class: 'card' }, h('h2', null, '1. Locais por onde a peça passa'),
      locais.length ? locais.map((l) => h('div', { class: 'row' }, h('input', { value: l.nome, onchange: (e) => salvar(() => patch(`/espacos/${l.id}`, { nome: e.target.value })) }),
        (() => { const t = h('select', { 'aria-label': 'Tipo do local', onchange: async (e) => { if (await tentar(() => patch(`/espacos/${l.id}`, { tipo: e.target.value }))) desenhar(); } },
          TIPOS_LOCAL.map(([v, r]) => h('option', { value: v }, r))); t.value = l.tipo; return t; })(),
        h('button', { class: 'sm dng', title: 'Remover', onclick: async () => { if (await tentar(() => patch(`/espacos/${l.id}`, { ativo: false }))) desenhar(); } }, '✕')))
        : h('p', { class: 'muted' }, 'Nenhum local ainda. Ex.: estoque, bancada de corte, montagem, expedição.'),
      h('div', { class: 'row' }, novoLocal, h('button', { onclick: async () => {
        if (!novoLocal.value.trim()) return toast('Digite o nome do local.', true);
        if (await tentar(() => post('/espacos', { unidade_id: uid, nome: novoLocal.value.trim() }))) desenhar();
      } }, '+ Adicionar local')));

    // ---- 2. distâncias
    const [oSel, dSel, metros] = [h('select', null, opcoes(locais, 'De…')), h('select', null, opcoes(locais, 'Até…')), h('input', { type: 'number', min: '0', step: 'any', placeholder: 'metros' })];
    const sDist = h('div', { class: 'card' }, h('h2', null, '2. Distância entre os locais (em metros)'),
      c.distancias.length ? c.distancias.map((d) => h('div', { class: 'row' }, h('div', null, `${d.origem} ↔ ${d.destino}`),
        (() => { const i = h('input', { type: 'number', min: '0', step: 'any', value: d.metros ?? '', placeholder: 'metros' });
          i.addEventListener('change', () => { if (i.value !== '') salvar(() => api('PUT', '/distancias', { origem_id: d.origem_id, destino_id: d.destino_id, metros: Number(i.value) })); }); return i; })()))
        : h('p', { class: 'muted' }, 'As distâncias necessárias aparecem aqui quando as tarefas (seção 4) tiverem "de onde" e "para onde".'),
      locais.length > 1 ? h('details', { class: 'det' }, h('summary', null, 'Informar outra distância'),
        h('div', { class: 'row' }, oSel, dSel, metros, h('button', { onclick: async () => {
          if (!oSel.value || !dSel.value || metros.value === '') return toast('Escolha os dois locais e a distância.', true);
          if (await tentar(() => api('PUT', '/distancias', { origem_id: Number(oSel.value), destino_id: Number(dSel.value), metros: Number(metros.value) }))) desenhar();
        } }, 'Salvar'))) : null);

    // ---- 3. equipamentos
    const novoEq = h('input', { placeholder: 'ex.: Seccionadora' });
    const sEq = h('div', { class: 'card' }, h('h2', null, '3. Máquinas e equipamentos'),
      equip.length ? h('div', { class: 'tw' }, h('table', null, h('thead', null, h('tr', null, ['Equipamento', 'Para que serve?', 'Em que local fica?'].map((t) => h('th', null, t)))),
        h('tbody', null, equip.map((r) => h('tr', null, h('td', null, r.nome, r.usado || r.funcao ? '' : h('span', { class: 'muted small' }, ' (não usado em tarefas)')),
          h('td', null, (() => { const f = h('select', { 'aria-label': 'Para que serve', onchange: async (e) => { if (await tentar(() => patch(`/recursos/${r.id}`, { funcao: e.target.value }))) desenhar(); } }, FUNCOES.map(([v, t]) => h('option', { value: v }, t))); f.value = r.funcao || ''; return f; })()),
          h('td', null, seletor(locais, r.espaco_id, '—', async (v) => { if (await tentar(() => patch(`/recursos/${r.id}`, { espaco_id: v }))) desenhar(); })))))))
        : h('p', { class: 'muted' }, 'Nenhum equipamento. Deixe vazio se o trabalho for todo manual.'),
      h('div', { class: 'row' }, novoEq, h('button', { onclick: async () => {
        if (!novoEq.value.trim()) return toast('Digite o nome do equipamento.', true);
        if (await tentar(() => post('/recursos', { unidade_id: uid, nome: novoEq.value.trim(), tipo: 'maquina' }))) desenhar();
      } }, '+ Adicionar equipamento')));

    // ---- 4. tarefas
    const sTar = !c.tarefas.length ? null : h('div', { class: 'card' }, h('h2', null, '4. Cada tarefa'),
      c.tarefas.length ? h('div', { class: 'tw' }, h('table', null, h('thead', null, h('tr', null, ['Tarefa', 'Equipamento', 'De onde sai?', 'Para onde vai?', 'Peso da peça (kg)'].map((t) => h('th', null, t)))),
        h('tbody', null, c.tarefas.map((t) => h('tr', null, h('td', null, t.nome, h('div', { class: 'muted small' }, t.processo)),
          h('td', null, seletor(equip, t.recurso_padrao_id, 'Manual', (v) => salvar(() => patch(`/operacoes/${t.operacao_id}`, { recurso_padrao_id: v })))),
          h('td', null, seletor(locais, t.espaco_origem_id, '—', async (v) => { if (await tentar(() => patch(`/operacoes/${t.operacao_id}`, { espaco_origem_id: v }))) desenhar(); })),
          h('td', null, seletor(locais, t.espaco_destino_id, '—', async (v) => { if (await tentar(() => patch(`/operacoes/${t.operacao_id}`, { espaco_destino_id: v }))) desenhar(); })),
          h('td', null, (() => { const i = h('input', { type: 'number', min: '0', step: 'any', value: t.item_peso_kg ?? '', placeholder: 'ex.: 8' });
            i.addEventListener('change', () => salvar(() => patch(`/operacoes/${t.operacao_id}`, { item_peso_kg: num(i.value) }))); return i; })()))))))
        : h('p', { class: 'muted' }, 'Ainda não há tarefas. Use "Configurar com a IA" para montar o processo.'));

    // ---- 5. peças (opcional)
    const novaPeca = h('input', { placeholder: 'ex.: Armário de cozinha' });
    const sPecas = h('details', { class: 'det' }, h('summary', null, 'Opcional: peças ou produtos com pesos diferentes'),
      h('div', { class: 'card' }, h('p', { class: 'muted small' }, 'Se cada ordem tem uma peça diferente, informe o peso de cada uma. Ao criar a ordem, a IA usa o peso da peça escolhida.'),
        pecas.map((p) => h('div', { class: 'row' }, h('div', null, p.nome),
          (() => { const i = h('input', { type: 'number', min: '0', step: 'any', value: p.peso_kg ?? '', placeholder: 'peso (kg)' });
            i.addEventListener('change', () => salvar(() => patch(`/produtos/${p.id}`, { peso_kg: num(i.value) }))); return i; })())),
        h('div', { class: 'row' }, novaPeca, h('button', { onclick: async () => {
          if (!novaPeca.value.trim()) return toast('Digite o nome da peça.', true);
          if (await tentar(() => post('/produtos', { nome: novaPeca.value.trim(), tipo: 'produto' }))) desenhar();
        } }, '+ Adicionar peça'))));
    // ---- 7. ambiente (opcional)
    const sAmb = h('details', { class: 'det' }, h('summary', null, 'Opcional: condições do ambiente (calor, ruído) em cada local'),
      h('div', { class: 'card' }, h('p', { class: 'muted small' }, 'Se informar, o plano alerta quando passar de limites de referência (ruído, temperatura). Não há "folga" digitada: o efeito do ambiente no tempo só entra quando for calculado de norma verificável.'),
        locais.length ? locais.map((l) => h('div', { class: 'row' }, h('div', null, l.nome),
          ...[['temperatura_c', 'Temperatura (°C)', l.temperatura_c], ['ruido_db', 'Ruído (dB)', l.ruido_db]].map(([k, rot, v]) =>
            h('div', null, h('label', null, rot), (() => { const i = h('input', { type: 'number', step: 'any', value: v ?? '' }); i.addEventListener('change', () => salvar(() => patch(`/espacos/${l.id}`, { [k]: num(i.value) }))); return i; })()))))
          : h('p', { class: 'muted' }, 'Cadastre os locais primeiro.')));
    const sMeios = await secaoMeios(uid, desenhar);
    montar(secoes, sLocais, sDist, sEq, sMeios, sTar, sPecas, sAmb);
  };
  await desenhar();
}

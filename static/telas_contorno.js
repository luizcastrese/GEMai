import { api, get, patch, post, qs } from './api.js';
import { estado } from './estado.js';
import { avisoIA, badge, fmtNum, h, modal, montar, tentar, toast } from './ui.js';
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

// Capacidade da máquina: o usuário mede e informa, OU a IA estima a partir de descrição/foto (ele confere antes de valer).
function celulaCapacidade(r, recarregar, salvar) {
  const i = h('input', { type: 'number', min: '0', step: 'any', value: r.pecas_por_hora ?? '', placeholder: 'não sei' });
  i.addEventListener('change', () => salvar(() => patch(`/recursos/${r.id}`, { capacidade: num(i.value), capacidade_unidade: 'un/h', capacidade_origem: i.value === '' ? '' : 'medido' })));
  const origem = r.pecas_por_hora == null ? null : r.capacidade_origem === 'ia' ? badge('estimado pela IA', 'b-ia') : r.capacidade_origem === 'medido' ? badge('medido', 'b-ok') : null;
  return h('div', null, i, h('div', { class: 'inline' }, origem,
    h('button', { class: 'sm ia', onclick: () => estimarComIA(r, recarregar) }, r.pecas_por_hora == null ? 'Não sei: a IA estima' : 'Reestimar com a IA')));
}

// Reduz a foto no navegador (o servidor aceita até ~600 KB) e devolve {tipo, base64}.
async function prepararFoto(arquivo) {
  const bmp = await createImageBitmap(arquivo);
  const f = Math.min(1, 1280 / Math.max(bmp.width, bmp.height));
  const cv = document.createElement('canvas');
  cv.width = Math.round(bmp.width * f); cv.height = Math.round(bmp.height * f);
  cv.getContext('2d').drawImage(bmp, 0, 0, cv.width, cv.height);
  for (const q of [0.8, 0.6, 0.4]) {
    const url = cv.toDataURL('image/jpeg', q);
    const b64 = url.slice(url.indexOf(',') + 1);
    if (b64.length * 0.75 < 600000) return { tipo: 'image/jpeg', base64: b64 };
  }
  throw new Error('Foto muito grande. Tente outra.');
}

function estimarComIA(r, recarregar) {
  const desc = h('textarea', { placeholder: 'Ex.: Seccionadora Fulano 3200, motor 5 cv, corta chapas de MDF de 18 mm' });
  const arq = h('input', { type: 'file', accept: 'image/*', capture: 'environment' });
  const area = h('div');
  const rodar = async (btn) => {
    let foto = null;
    if (arq.files[0]) { try { foto = await prepararFoto(arq.files[0]); } catch (e) { return toast(e.message || 'Não consegui ler a foto.', true); } }
    if (!desc.value.trim() && !foto) return toast('Descreva a máquina ou envie uma foto.', true);
    btn.disabled = true;
    const e = await tentar(() => post(`/recursos/${r.id}/estimar-capacidade`, { descricao: desc.value.trim(), imagem_base64: foto?.base64, imagem_tipo: foto?.tipo }));
    btn.disabled = false;
    if (!e) return;
    const valor = h('input', { type: 'number', min: '0', step: 'any', value: e.pecas_por_hora ?? '' });
    montar(area, avisoIA('É uma estimativa, não uma medição. Confira se faz sentido para a sua oficina; se puder cronometrar depois, substitua pelo valor medido.'),
      e.pecas_por_hora == null ? h('div', { class: 'aviso' }, 'A IA não conseguiu estimar com o que foi enviado.')
        : h('div', null, h('strong', null, `Cerca de ${fmtNum(e.pecas_por_hora, 0)} peças por hora`),
          e.minimo != null && e.maximo != null && e.maximo > e.minimo ? ` (entre ${fmtNum(e.minimo, 0)} e ${fmtNum(e.maximo, 0)})` : '', ` · confiança ${e.confianca}`),
      e.premissas.length ? h('ul', null, e.premissas.map((x) => h('li', { class: 'small' }, x))) : null,
      e.dados_faltantes.length ? h('div', { class: 'aviso' }, h('strong', null, 'Para estimar melhor, informe: '), h('ul', null, e.dados_faltantes.map((x) => h('li', null, x)))) : null,
      e.aviso ? h('p', { class: 'muted small' }, e.aviso) : null,
      e.pecas_por_hora == null ? null : h('div', null, h('label', null, 'Valor a usar (você pode ajustar)'), valor,
        h('button', { class: 'pri', onclick: async () => {
          if (valor.value === '' || Number(valor.value) <= 0) return toast('Informe um valor maior que zero.', true);
          if (await tentar(() => patch(`/recursos/${r.id}`, { capacidade: Number(valor.value), capacidade_unidade: 'un/h', capacidade_origem: 'ia' }), 'Salvo como estimativa da IA.')) { fecharModal(); recarregar(); }
        } }, 'Usar este valor')));
  };
  const fecharModal = modal(`A IA estima — ${r.nome}`, h('div', null,
    h('p', { class: 'muted' }, 'Você não precisa saber quantas peças a máquina faz por hora. Conte o que souber (marca, modelo, potência, o que ela faz) e/ou envie uma foto.'),
    h('label', null, 'Descrição'), desc, h('label', null, 'Foto da máquina ou da plaqueta (opcional)'), arq, area),
  { acoes: (fechar) => [h('button', { onclick: fechar }, 'Fechar'), h('button', { class: 'ia', onclick: (ev) => rodar(ev.target) }, 'Estimar')] });
}

// Contorno físico MÍNIMO: onde as coisas ficam, a que distância, quanto cada máquina produz e quanto pesa a peça.
export async function contornoAvancado(el) {
  const uid = estado.unidadeId;
  const topo = h('div'); const secoes = h('div');
  montar(el, h('p', { class: 'noprint' }, h('a', { href: '#/contorno' }, '← Voltar ao passo a passo')), h('h1', null, 'Oficina: ajustes avançados'),
    h('p', { class: 'muted' }, 'Todos os dados da oficina numa tela só: locais, distâncias, máquinas, ficha técnica, tarefas, pesos e ambiente. O tempo nunca é digitado. Tudo é salvo ao preencher.'),
    topo, secoes);

  const progresso = async () => {
    const c = await get(`/contorno${qs({ unidade_id: uid })}`);
    const barra = h('div', { class: 'bar' }, h('i')); barra.firstChild.style.width = `${c.progresso_pct}%`;
    montar(topo, h('div', { class: c.completo ? 'card ok-box' : 'card' },
      c.completo ? h('div', null, h('strong', null, '✓ Oficina completa.'), ' A IA já consegue prever o tempo. ', h('a', { class: 'btn', href: '#/planos' }, 'Ir para os planos de trabalho'), estado.avancado ? [' ', h('a', { class: 'btn', href: '#/processos' }, 'Ir para os processos')] : null)
        : h('div', null, h('strong', null, `${c.progresso_pct}% preenchido`), c.tarefas.length || c.pendentes ? ` — faltam ${c.pendentes} informação(ões):` : ' — cadastre os locais, as distâncias e as máquinas.',
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
    const sLocais = h('div', { class: 'card', id: 'oficina-locais' }, h('h2', null, '1. Locais por onde a peça passa'),
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
    const sDist = h('div', { class: 'card', id: 'oficina-distancias' }, h('h2', null, '2. Distância entre os locais (em metros)'),
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
    const sEq = h('div', { class: 'card', id: 'oficina-equipamentos' }, h('h2', null, '3. Máquinas e equipamentos'),
      equip.length ? h('div', { class: 'tw' }, h('table', null, h('thead', null, h('tr', null, ['Equipamento', 'Para que serve?', 'Quantas peças por hora faz?', 'Em que local fica?'].map((t) => h('th', null, t)))),
        h('tbody', null, equip.map((r) => h('tr', null, h('td', null, r.nome, r.usado || r.funcao ? '' : h('span', { class: 'muted small' }, ' (não usado em tarefas)')),
          h('td', null, (() => { const f = h('select', { 'aria-label': 'Para que serve', onchange: async (e) => { if (await tentar(() => patch(`/recursos/${r.id}`, { funcao: e.target.value }))) desenhar(); } }, FUNCOES.map(([v, t]) => h('option', { value: v }, t))); f.value = r.funcao || ''; return f; })()),
          h('td', null, celulaCapacidade(r, () => desenhar(), salvar)),
          h('td', null, seletor(locais, r.espaco_id, '—', async (v) => { if (await tentar(() => patch(`/recursos/${r.id}`, { espaco_id: v }))) desenhar(); })))))))
        : h('p', { class: 'muted' }, 'Nenhum equipamento. Deixe vazio se o trabalho for todo manual.'),
      h('div', { class: 'row' }, novoEq, h('button', { onclick: async () => {
        if (!novoEq.value.trim()) return toast('Digite o nome do equipamento.', true);
        if (await tentar(() => post('/recursos', { unidade_id: uid, nome: novoEq.value.trim(), tipo: 'maquina', capacidade_unidade: 'un/h' }))) desenhar();
      } }, '+ Adicionar equipamento')));

    // ---- 4. tarefas
    const sTar = !c.tarefas.length ? null : h('div', { class: 'card', id: 'oficina-tarefas' }, h('h2', null, '4. Cada tarefa'),
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
    // veio de "Faltam dados da oficina": leva direto ao bloco certo (uma vez só)
    const alvo = estado.foco && document.getElementById(`oficina-${estado.foco}`);
    estado.foco = null;
    if (alvo) { alvo.classList.add('destaque'); alvo.scrollIntoView({ block: 'start', behavior: 'smooth' }); }
  };
  await desenhar();
}

// ---------------------------------------------------------------- passo a passo
// Uma pergunta por vez, na língua da oficina. Os mesmos dados da tela avançada, só que em etapas curtas.
const SUG_LOCAL = [['Estoque de chapas', 'estoque'], ['Bancada de corte', 'area'], ['Montagem', 'montagem'], ['Expedição', 'expedicao']];
const SUG_MAQ = [['Seccionadora', 'corte'], ['Coladeira de borda', 'bordo'], ['Furadeira', 'furacao']];
const DIST_RAPIDAS = [['Lado a lado', 2], ['Mesma sala', 8], ['Outra sala', 20]];
const PASSOS = ['Locais', 'Máquinas', 'Ritmo', 'Distâncias', 'Pronto'];
const PASSO_DA_SECAO = { locais: 0, equipamentos: 2, distancias: 3 };
const FUNCOES_PILULA = FUNCOES.filter(([v]) => v);

export async function contorno(el) {
  const uid = estado.unidadeId;
  if (estado.foco === 'tarefas' || estado.foco === 'equipamentos') { location.hash = '#/contorno/avancado'; return undefined; }
  let passo = null; // null: abre no primeiro passo que ainda falta
  const topo = h('div'); const corpo = h('div'); const rodape = h('div', { class: 'assist-nav' });
  montar(el, h('h1', null, 'Oficina'),
    h('p', { class: 'muted' }, 'Vamos montar a sua oficina em poucos passos. Tudo é salvo ao preencher e você pode voltar quando quiser.'),
    topo, corpo, rodape);

  const pend = (c, secao) => c.pendencias.some((p) => p.secao === secao);
  // ✓ só onde há algo realmente preenchido (ou já visitado): evita marcar "Pronto" antes da hora
  const feito = (c, i) => [c.locais.length > 0, c.equipamentos.length > 0, c.equipamentos.length > 0 && c.equipamentos.every((r) => r.pecas_por_hora != null),
    passo > 3 && !pend(c, 'distancias'), false][i];
  const primeiroIncompleto = (c) => {
    if (!c.locais.length) return 0;
    if (!c.equipamentos.length) return 1;
    if (c.equipamentos.some((r) => r.pecas_por_hora == null)) return 2; // ritmo (capacidade) é opcional, mas oferecemos o passo
    if (pend(c, 'distancias')) return 3;
    return 4;
  };

  const desenharTopo = (c) => montar(topo, h('ol', { class: 'passos', 'aria-label': 'Passos da oficina' }, PASSOS.map((nome, i) =>
    h('li', { class: i === passo ? 'on' : feito(c, i) ? 'ok' : '' },
      h('button', { type: 'button', 'aria-current': i === passo ? 'step' : undefined, onclick: () => { passo = i; desenhar(); } },
        h('span', { class: 'bolha' }, feito(c, i) && i !== passo ? '✓' : i + 1), h('span', { class: 'rot' }, nome))))));

  // edição de um campo: salva e só atualiza o topo (não redesenha, para não perder o foco ao navegar de campo em campo)
  const leve = async (fn) => {
    const r = await tentar(fn);
    if (r === undefined) return;
    toast('Salvo.');
    desenharTopo(await get(`/contorno${qs({ unidade_id: uid })}`));
  };
  const estrutural = async (fn) => { if (await tentar(fn) !== undefined) desenhar(); };

  const pergunta = (titulo, ajuda, ...filhos) => h('div', { class: 'card pergunta' }, h('h2', null, titulo), h('p', { class: 'muted' }, ajuda), ...filhos);

  // 1. Locais
  const passoLocais = (c) => {
    const novo = h('input', { placeholder: 'ou escreva outro local', 'aria-label': 'Nome do novo local' });
    const add = (nome, tipo = 'area') => (nome.trim() ? estrutural(() => post('/espacos', { unidade_id: uid, nome: nome.trim(), tipo })) : toast('Digite o nome do local.', true));
    const jaTem = (n) => c.locais.some((l) => l.nome.toLowerCase() === n.toLowerCase());
    const sug = SUG_LOCAL.filter(([n]) => !jaTem(n));
    return pergunta('Onde você trabalha?', 'Os lugares por onde a peça passa. Toque nos que existem na sua oficina.',
      sug.length ? h('div', { class: 'chips' }, sug.map(([n, t]) => h('button', { type: 'button', class: 'chip', onclick: () => add(n, t) }, `+ ${n}`))) : null,
      c.locais.length ? h('div', { class: 'itens' }, c.locais.map((l) => h('div', { class: 'item' },
        h('input', { value: l.nome, 'aria-label': 'Nome do local', onchange: (e) => leve(() => patch(`/espacos/${l.id}`, { nome: e.target.value })) }),
        (() => { const t = h('select', { 'aria-label': 'Tipo do local', onchange: (e) => estrutural(() => patch(`/espacos/${l.id}`, { tipo: e.target.value })) },
          TIPOS_LOCAL.map(([v, r]) => h('option', { value: v }, r))); t.value = l.tipo; return t; })(),
        h('button', { type: 'button', class: 'sm dng', title: 'Remover', 'aria-label': `Remover ${l.nome}`, onclick: () => estrutural(() => patch(`/espacos/${l.id}`, { ativo: false })) }, '✕')))) : null,
      h('div', { class: 'row' }, novo, h('button', { type: 'button', onclick: () => add(novo.value) }, '+ Adicionar')));
  };

  // 2. Máquinas
  const passoMaquinas = (c) => {
    const novo = h('input', { placeholder: 'ou escreva outra máquina', 'aria-label': 'Nome da nova máquina' });
    const add = (nome, funcao = '') => (nome.trim() ? estrutural(() => post('/recursos', { unidade_id: uid, nome: nome.trim(), tipo: 'maquina', capacidade_unidade: 'un/h', funcao })) : toast('Digite o nome da máquina.', true));
    const jaTem = (n) => c.equipamentos.some((r) => r.nome.toLowerCase() === n.toLowerCase());
    const sug = SUG_MAQ.filter(([n]) => !jaTem(n));
    return pergunta('Quais máquinas você usa?', 'Toque nas que você tem e diga para que cada uma serve. Trabalho todo manual? Pode seguir sem máquinas.',
      sug.length ? h('div', { class: 'chips' }, sug.map(([n, f]) => h('button', { type: 'button', class: 'chip', onclick: () => add(n, f) }, `+ ${n}`))) : null,
      c.equipamentos.length ? h('div', { class: 'itens' }, c.equipamentos.map((r) => h('div', { class: 'item maq' },
        h('div', { class: 'linha' },
          h('input', { value: r.nome, 'aria-label': 'Nome da máquina', onchange: (e) => leve(() => patch(`/recursos/${r.id}`, { nome: e.target.value })) }),
          h('button', { type: 'button', class: 'sm dng', title: 'Remover', 'aria-label': `Remover ${r.nome}`, onclick: () => estrutural(() => patch(`/recursos/${r.id}`, { ativo: false })) }, '✕')),
        h('div', { class: 'muted small' }, 'Para que serve?'),
        h('div', { class: 'pilulas', role: 'group', 'aria-label': `Para que serve ${r.nome}` }, FUNCOES_PILULA.map(([v, t]) =>
          h('button', { type: 'button', class: `pilula${r.funcao === v ? ' on' : ''}`, 'aria-pressed': r.funcao === v ? 'true' : 'false',
            onclick: () => estrutural(() => patch(`/recursos/${r.id}`, { funcao: r.funcao === v ? '' : v })) }, t))),
        c.locais.length ? h('div', null, h('div', { class: 'muted small' }, 'Em que local fica?'), seletor(c.locais, r.espaco_id, 'Escolha…', (v) => estrutural(() => patch(`/recursos/${r.id}`, { espaco_id: v })))) : null))) : null,
      h('div', { class: 'row' }, novo, h('button', { type: 'button', onclick: () => add(novo.value) }, '+ Adicionar')));
  };

  // 3. Ritmo (peças por hora): medido ou estimado pela IA
  const passoRitmo = (c) => pergunta('Quantas peças cada máquina faz por hora?',
    'Opcional: o tempo de máquina vem da ficha técnica (avanço, velocidade), não deste número. Se quiser registrar uma medição ou uma estimativa da IA (rotulada nas premissas do plano), preencha aqui.',
    c.equipamentos.length ? h('div', { class: 'itens' }, c.equipamentos.map((r) => h('div', { class: 'item maq' },
      h('div', { class: 'linha' }, h('strong', null, r.nome), h('span', { class: 'muted small' }, (FUNCOES.find((f) => f[0] === r.funcao) || [])[1] || '')),
      celulaCapacidade(r, desenhar, leve))))
      : h('p', { class: 'muted' }, 'Nenhuma máquina cadastrada: nada a informar aqui. Pode continuar.'));

  // 4. Distâncias: toque numa opção (ou digite os metros)
  const passoDistancias = (c) => pergunta('Qual a distância entre os locais?',
    'Só o que o sistema precisa para contar o tempo de levar a peça de um lugar a outro. Escolha a opção mais próxima; se souber, digite os metros.',
    c.distancias.length ? h('div', { class: 'itens' }, c.distancias.map((d) => {
      const gravar = (m) => api('PUT', '/distancias', { origem_id: d.origem_id, destino_id: d.destino_id, metros: m });
      const i = h('input', { type: 'number', min: '0', step: 'any', value: d.metros ?? '', placeholder: 'metros', 'aria-label': `Metros entre ${d.origem} e ${d.destino}` });
      i.addEventListener('change', () => { if (i.value !== '') leve(() => gravar(Number(i.value))); });
      return h('div', { class: 'item maq' }, h('div', { class: 'linha' }, h('strong', null, `${d.origem} ↔ ${d.destino}`)),
        h('div', { class: 'pilulas' }, DIST_RAPIDAS.map(([t, m]) => h('button', { type: 'button', class: `pilula${d.metros === m ? ' on' : ''}`, 'aria-pressed': d.metros === m ? 'true' : 'false',
          onclick: () => estrutural(() => gravar(m)) }, `${t} (${m} m)`))),
        h('div', { class: 'inline' }, i, h('span', { class: 'muted small' }, 'metros')));
    })) : h('p', { class: 'muted' }, 'Nenhuma distância necessária por enquanto. Elas aparecem quando os seus locais e máquinas formarem o caminho da peça (estoque, corte, borda, furação, montagem).'));

  // 5. Pronto
  const passoPronto = (c) => {
    const faltas = [...c.pendencias];
    return faltas.length === 0
      ? h('div', { class: 'card ok-box pergunta' }, h('h2', null, '✓ Oficina pronta'), h('p', null, 'Agora a IA já consegue prever o tempo. Falta só gerar o plano de trabalho.'),
        h('a', { class: 'btn pri big', href: '#/planos' }, 'Ir para os planos de trabalho'))
      : h('div', { class: 'card pergunta' }, h('h2', null, 'Quase lá'), h('p', { class: 'muted' }, `Faltam ${faltas.length} informação(ões) para o plano ficar completo. Sem elas, os passos afetados ficam "sem tempo":`),
        h('ul', { class: 'pend' }, faltas.slice(0, 6).map((p) => h('li', null, p.texto, ' ',
          p.secao === 'tarefas' || p.secao === 'equipamentos' ? h('a', { class: 'btn sm', href: '#/contorno/avancado' }, 'Preencher')
            : h('button', { type: 'button', class: 'sm', onclick: () => { passo = PASSO_DA_SECAO[p.secao] ?? 0; desenhar(); } }, 'Preencher'))),
          faltas.length > 6 ? h('li', { class: 'muted' }, `e mais ${faltas.length - 6}…`) : null),
        h('p', { class: 'small muted' }, 'Pode seguir mesmo assim: ', h('a', { href: '#/planos' }, 'ir para os planos de trabalho'), '.'));
  };

  const PASSO_FN = [passoLocais, passoMaquinas, passoRitmo, passoDistancias, passoPronto];
  async function desenhar() {
    const c = await get(`/contorno${qs({ unidade_id: uid })}`);
    if (passo === null) { passo = PASSO_DA_SECAO[estado.foco] ?? primeiroIncompleto(c); estado.foco = null; }
    desenharTopo(c);
    montar(corpo, PASSO_FN[passo](c));
    montar(rodape,
      passo > 0 ? h('button', { type: 'button', onclick: () => { passo -= 1; desenhar(); window.scrollTo({ top: 0, behavior: 'smooth' }); } }, '← Voltar') : h('span'),
      h('a', { class: 'small muted', href: '#/contorno/avancado' }, 'Ver tudo numa tela só (avançado)'),
      passo < PASSOS.length - 1 ? h('button', { type: 'button', class: 'pri', onclick: () => { passo += 1; desenhar(); window.scrollTo({ top: 0, behavior: 'smooth' }); } }, 'Continuar →') : h('span'));
  }
  await desenhar();
  return undefined;
}

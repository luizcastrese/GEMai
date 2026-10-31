import { api, del, get, patch, post, qs } from './api.js';
import { estado } from './estado.js';
import { avisoIA, badge, detalhes, fmtNum, h, modal, montar, tentar, toast } from './ui.js';

const num = (v) => (v === '' || v === null || v === undefined ? null : Number(v));
const opcoes = (lista, vazio) => [h('option', { value: '' }, vazio), ...lista.map((x) => h('option', { value: x.id }, x.nome))];
const seletor = (lista, valor, vazio, aoMudar) => {
  const s = h('select', { onchange: (e) => aoMudar(num(e.target.value)) }, opcoes(lista, vazio));
  s.value = valor ?? '';
  return s;
};

const TIPOS_LOCAL = [['area', 'Outro / área de trabalho'], ['estoque', 'Estoque (início)'], ['montagem', 'Montagem'], ['posto', 'Posto'], ['expedicao', 'Expedição']];
const FUNCOES = [['', 'Não informado'], ['corte', 'Cortar'], ['bordo', 'Colar borda'], ['furacao', 'Furar'], ['acabamento', 'Acabamento'], ['montagem', 'Montagem'], ['outro', 'Outro']];
const REF_ROTULOS = { 'conferencia_final': 'Conferência final de cada unidade', 'fixador:parafuso': 'Colocar 1 parafuso', 'fixador:cavilha': 'Colocar 1 cavilha', 'fixador:minifix': 'Colocar 1 minifix',
  'fixador:dobradica': 'Instalar 1 dobradiça', 'fixador:corredica': 'Instalar 1 corrediça', 'fixador:cola': 'Colar 1 junção', 'fixador:prego': 'Pregar 1 prego', 'fixador:encaixe': 'Fazer 1 encaixe',
  'fixador:puxador': 'Instalar 1 puxador', 'fixador:outro': 'Outro tipo de fixação (1 un.)' };

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
export async function contorno(el) {
  let refAberto = false;
  const uid = estado.unidadeId;
  const topo = h('div'); const secoes = h('div');
  montar(el, h('h1', null, 'Oficina'),
    h('p', { class: 'muted' }, 'Onde as coisas ficam, a que distância e quais máquinas você tem. Se não souber quanto cada máquina produz por hora, a IA estima por descrição ou foto. Tudo é salvo ao preencher.'),
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
    // ---- 6. referências de montagem (planos de trabalho)
    const refs = await get('/referencias-tempo');
    const sRef = h('details', { class: 'det', open: refAberto, ontoggle: (e) => { refAberto = e.target.open; } }, h('summary', null, 'Tempos de montagem usados nos planos de trabalho'),
      h('div', { class: 'card' }, h('p', { class: 'muted small' }, 'Valores genéricos de partida. Troque pelos da sua oficina (em minutos) — o plano passa a usá-los e avisa que são seus.'),
        refs.map((r) => h('div', { class: 'row ref' }, h('div', { class: 'l' }, REF_ROTULOS[r.chave] || r.chave, r.informada ? h('span', { class: 'muted small' }, ` (seu valor; padrão ${fmtNum(r.padrao_minutos, 2)} min)`) : h('span', { class: 'muted small' }, ' (valor genérico)')),
          (() => { const i = h('input', { type: 'number', min: '0', step: 'any', value: r.minutos, 'aria-label': 'minutos' });
            i.addEventListener('change', async () => { if (i.value !== '' && await tentar(() => api('PUT', '/referencias-tempo', { chave: r.chave, minutos: Number(i.value) }), 'Salvo.')) desenhar(); }); return i; })(),
          r.informada ? h('button', { class: 'sm', onclick: async () => { if (await tentar(() => del(`/referencias-tempo/${encodeURIComponent(r.chave)}`))) desenhar(); } }, 'Voltar ao padrão') : h('span')))));

    // ---- 7. ambiente (opcional)
    const sAmb = h('details', { class: 'det' }, h('summary', null, 'Opcional: condições do ambiente (calor, ruído) em cada local'),
      h('div', { class: 'card' }, h('p', { class: 'muted small' }, 'Se informar, o plano alerta quando passar de limites de referência. A "folga extra" (%) aumenta o tempo dos passos feitos naquele local, por exemplo em ambiente muito quente; só use se souber o valor.'),
        locais.length ? locais.map((l) => h('div', { class: 'row' }, h('div', null, l.nome),
          ...[['temperatura_c', 'Temperatura (°C)', l.temperatura_c], ['ruido_db', 'Ruído (dB)', l.ruido_db], ['tolerancia_ambiente_pct', 'Folga extra (%)', l.tolerancia_ambiente_pct]].map(([k, rot, v]) =>
            h('div', null, h('label', null, rot), (() => { const i = h('input', { type: 'number', step: 'any', value: v ?? '' }); i.addEventListener('change', () => salvar(() => patch(`/espacos/${l.id}`, { [k]: num(i.value) }))); return i; })()))))
          : h('p', { class: 'muted' }, 'Cadastre os locais primeiro.')));
    montar(secoes, sLocais, sDist, sEq, sTar, sPecas, sRef, sAmb);
  };
  await desenhar();
}

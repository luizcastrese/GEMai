// Variante do pedido: o produto é a família ("Armário"); tamanho, tipo e as peças/parafusos de CADA pedido ficam no plano.
import { patch } from './api.js';
import { confirmar, h, montar, tentar, toast } from './ui.js';
import { atributoDoPacote } from './estado.js';

const num = (v) => (v === '' || v === null || v === undefined ? null : Number(String(v).replace(',', '.')));
const METODOS = [['parafuso', 'Parafuso'], ['cavilha', 'Cavilha'], ['minifix', 'Minifix'], ['dobradica', 'Dobradiça'], ['corredica', 'Corrediça'],
  ['cola', 'Cola'], ['prego', 'Prego'], ['encaixe', 'Encaixe'], ['puxador', 'Puxador'], ['outro', 'Outro']];
const rotMetodo = (m) => (METODOS.find((x) => x[0] === m) || [m, m])[1];
const TIPOS = [['numero', 'Número'], ['opcao', 'Escolha'], ['texto', 'Texto']];
const rotCampo = (c) => `${c.nome}${c.unidade ? ` (${c.unidade})` : ''}${c.obrigatorio ? ' *' : ''}`;

// ---------------------------------------------------------------- campos que mudam de pedido para pedido (tela do produto)
export function cartaoCampos(produto, depois) {
  const campos = produto.campos_especificacao || [];
  const salvar = async (lista) => { if (await tentar(() => patch(`/produtos/${produto.id}`, { campos_especificacao: lista }))) { produto.campos_especificacao = lista; depois(); } };
  const novo = { nome: h('input', { placeholder: 'ex.: Largura' }), tipo: h('select', null, TIPOS.map(([v, r]) => h('option', { value: v }, r))),
    unidade: h('input', { placeholder: 'cm, mm…', size: 6 }), opcoes: h('input', { placeholder: 'opções separadas por vírgula (ex.: 1 porta, 2 portas)' }),
    obr: h('input', { type: 'checkbox' }) };
  const ajusta = () => { novo.opcoes.style.display = novo.tipo.value === 'opcao' ? '' : 'none'; novo.unidade.style.display = novo.tipo.value === 'numero' ? '' : 'none'; };
  novo.tipo.addEventListener('change', ajusta);
  ajusta();
  const dica = (c) => (c.tipo === 'opcao' ? `Escolha: ${c.opcoes.join(', ')}` : c.tipo === 'numero' ? `Número${c.unidade ? ` em ${c.unidade}` : ''}` : 'Texto');
  return h('div', { class: 'card' }, h('h2', null, 'Campos do pedido'),
    h('p', { class: 'muted small' }, 'O que muda de um pedido para outro, como largura ou tipo. Os valores você informa em cada plano.'),
    campos.length ? campos.map((c, i) => h('div', { class: 'lig' }, h('span', null, h('strong', null, c.nome), ` · ${dica(c)}${c.obrigatorio ? ' · obrigatório' : ''}`),
      h('button', { class: 'sm dng', title: 'Remover campo', onclick: () => confirmar(`Remover o campo "${c.nome}"? Planos já criados mantêm o valor que guardaram.`, () => salvar(campos.filter((_, j) => j !== i)), 'Remover') }, '✕')))
      : h('p', { class: 'muted' }, 'Nenhum campo ainda. Sem campos, todos os pedidos deste produto são tratados como iguais no relatório.'),
    h('div', { class: 'row' }, novo.nome, novo.tipo, novo.unidade, novo.opcoes,
      h('label', { class: 'small' }, novo.obr, ' obrigatório'),
      h('button', { onclick: () => {
        const nome = novo.nome.value.trim();
        if (!nome) return toast('Dê um nome ao campo.', true);
        const c = { nome, tipo: novo.tipo.value, unidade: novo.tipo.value === 'numero' ? novo.unidade.value.trim() : '', obrigatorio: novo.obr.checked,
          opcoes: novo.tipo.value === 'opcao' ? novo.opcoes.value.split(',').map((x) => x.trim()).filter(Boolean) : [] };
        salvar([...campos, c]);
      } }, '+ Adicionar campo')));
}

// ---------------------------------------------------------------- valores do pedido (formulário no plano)
export function formEspecificacoes(campos, inicial = {}) {
  const ref = {};
  const ouvintes = [];
  const el = campos.length ? h('div', null, h('div', { class: 'row' }, campos.map((c) => {
    let inp;
    if (c.tipo === 'opcao') inp = h('select', null, h('option', { value: '' }, 'Escolha…'), c.opcoes.map((o) => h('option', { value: o, selected: inicial[c.nome] === o }, o)));
    else if (c.tipo === 'numero') inp = h('input', { type: 'number', min: '0', step: 'any', value: inicial[c.nome] ?? '', placeholder: c.unidade || '' });
    else inp = h('input', { type: 'text', value: inicial[c.nome] ?? '' });
    ref[c.nome] = inp;
    inp.addEventListener('change', () => ouvintes.forEach((fn) => fn()));
    return h('div', null, h('label', null, rotCampo(c)), inp);
  }))) : null;
  return { el, aoMudar: (fn) => ouvintes.push(fn), valores: () => Object.fromEntries(campos.map((c) => [c.nome, ref[c.nome].value.trim()]).filter(([, v]) => v !== '')
    .map(([k, v]) => [k, campos.find((c) => c.nome === k).tipo === 'numero' ? num(v) : v])) };
}

// ---------------------------------------------------------------- peças e parafusos deste pedido
// Parte do modelo base do produto (ou da estrutura já guardada no plano) e deixa ajustar só para este pedido.
export function editorEstrutura(inicial) {
  let est = JSON.parse(JSON.stringify(inicial));
  const area = h('div');
  const nomes = () => est.componentes.map((c) => c.nome);
  const campoNum = (obj, k, ajuda, ehInt = false) => {
    const formula = k === 'fixadores' ? obj.formula_fixadores : obj.formulas?.[k];
    const i = h('input', { type: 'number', class: formula ? 'n form' : 'n', min: '0', step: ehInt ? '1' : 'any', value: obj[k] ?? '', placeholder: ajuda,
      title: formula ? `Calculado pelas medidas do pedido: =${formula}. Se mudar à mão, fica registrado no plano.` : undefined });
    const POSITIVOS = ['comprimento_m', 'largura_m', 'espessura_m']; // a API exige > 0 (vazio = não informado)
    i.addEventListener('change', () => {
      let v = num(i.value);
      if (k === 'quantidade') v = v && v > 0 ? v : 1;
      else if (k === 'furos' || k === 'fixadores') v = Math.max(0, Math.round(v || 0));
      else if (POSITIVOS.includes(k) && !(v > 0)) v = null;
      obj[k] = v;
      i.value = v ?? '';
    });
    return i;
  };
  const desenhar = () => {
    const nova = { nome: h('input', { placeholder: 'ex.: Prateleira' }), qtd: h('input', { type: 'number', min: '0', step: 'any', value: '1' }) };
    const sel = (lista, vazio) => h('select', null, h('option', { value: '' }, vazio), lista.map((x) => h('option', { value: x }, x)));
    const [lc, la, lm, lf] = [sel(nomes(), 'Peça…'), sel(nomes(), 'ao conjunto'), h('select', null, METODOS.map(([v, r]) => h('option', { value: v }, r))), h('input', { type: 'number', min: '0', step: '1', value: '0' })];
    const linhas = est.componentes.map((c, i) => h('tr', null,
      h('td', null, h('strong', null, c.nome)), h('td', null, campoNum(c, 'quantidade')), h('td', null, c.material || '—'),
      h('td', null, h('div', { class: 'inline nw' }, campoNum(c, 'comprimento_m', 'comp. (m)'), campoNum(c, 'largura_m', 'larg. (m)'), campoNum(c, 'espessura_m', 'esp. (m)'))),
      h('td', null, campoNum(c, 'peso_kg', 'kg')), atributoDoPacote('furos') ? h('td', null, campoNum(c, 'furos', '', true)) : null,
      h('td', null, h('button', { class: 'sm dng', title: 'Tirar esta peça do pedido', onclick: () => {
        est.componentes.splice(i, 1);
        est.ligacoes = est.ligacoes.filter((l) => l.componente !== c.nome && l.ligado_a !== c.nome);
        desenhar();
      } }, '✕'))));
    const ligs = est.ligacoes.map((l, i) => h('div', { class: 'lig' }, h('span', null, `${l.componente} → ${l.ligado_a || 'o conjunto'} · ${rotMetodo(l.metodo)} · `),
      h('span', { class: 'inline' }, h('span', { class: 'small muted' }, 'quantidade'), campoNum(l, 'fixadores', '', true)),
      h('button', { class: 'sm dng', onclick: () => { est.ligacoes.splice(i, 1); desenhar(); } }, '✕')));
    montar(area,
      h('p', { class: 'muted small' }, 'Ajuste para este pedido: quantidade, medidas (em metros) e quantidade de fixadores. Isso não muda o produto, só este pedido.'),
      est.componentes.length ? h('div', { class: 'tw' }, h('table', null, h('thead', null, h('tr', null, ['Item', 'Qtd.', 'Material', 'Medidas (m)', 'Peso (kg)', atributoDoPacote('furos') ? 'Furos' : null, ''].filter((t) => t !== null).map((t) => h('th', null, t)))), h('tbody', null, linhas)))
        : h('p', { class: 'aviso' }, 'Sem itens: o plano não pode ser calculado.'),
      h('div', { class: 'row' }, nova.nome, nova.qtd, h('button', { onclick: () => {
        const nome = nova.nome.value.trim();
        if (!nome) return toast('Dê um nome à peça.', true);
        if (nomes().some((n) => n.toLowerCase() === nome.toLowerCase())) return toast('Já existe uma peça com esse nome neste pedido.', true);
        est.componentes.push({ nome, quantidade: Number(nova.qtd.value) || 1, material: '', grupo: 'Corpo', comprimento_m: null, largura_m: null, espessura_m: null, peso_kg: null, furos: 0, bordas_m: null });
        desenhar();
      } }, '+ Peça')),
      h('h4', null, 'Como as peças se juntam neste pedido'),
      ligs.length ? ligs : h('p', { class: 'muted small' }, 'Nenhuma ligação.'),
      est.componentes.length ? h('div', { class: 'row' }, lc, la, lm, lf, h('button', { onclick: () => {
        if (!lc.value) return toast('Escolha a peça.', true);
        if (lc.value === la.value) return toast('Uma peça não se liga a ela mesma.', true);
        est.ligacoes.push({ componente: lc.value, ligado_a: la.value || null, metodo: lm.value, fixadores: Number(lf.value) || 0 });
        desenhar();
      } }, '+ Ligação')) : null);
  };
  desenhar();
  return { el: area, valor: () => est, definir: (nova) => { est = JSON.parse(JSON.stringify(nova)); desenhar(); } };
}

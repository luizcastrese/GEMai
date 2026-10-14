import { api, del, get, patch, post, qs } from './api.js';
import { estado } from './estado.js';
import { abrirGerar } from './telas_plano.js';
import { avisoIA, badge, confirmar, detalhes, fmtNum, h, modal, montar, tabela, tentar, toast } from './ui.js';

// O item final (ex.: armário) numa tela só. A pessoa informa as peças, os agentes (pessoas e máquinas) e o ambiente
// (locais e distâncias). As atividades NÃO são perguntadas: a plataforma as deduz das peças, mostra o que falta em cada
// seção e monta o plano de trabalho com os tempos (regras em app/services/preparo.py e app/services/plano.py).

const num = (v) => (v === '' || v === null || v === undefined ? null : Number(v));
const entrada = (tipo, valor, extra = {}) => h('input', { type: tipo, value: valor ?? '', ...extra });
const METODOS = [['parafuso', 'Parafuso'], ['cavilha', 'Cavilha'], ['minifix', 'Minifix'], ['dobradica', 'Dobradiça'], ['corredica', 'Corrediça'],
  ['cola', 'Cola'], ['prego', 'Prego'], ['encaixe', 'Encaixe'], ['puxador', 'Puxador'], ['outro', 'Outro']];
const rotMetodo = (m) => (METODOS.find((x) => x[0] === m) || [m, m])[1];
const TIPOS_LOCAL = [['area', 'Área de trabalho'], ['estoque', 'Estoque (início)'], ['montagem', 'Montagem'], ['posto', 'Posto'], ['expedicao', 'Expedição']];
const REF_ROTULOS = { conferencia_final: 'Conferência final de cada unidade', 'fixador:parafuso': 'Colocar 1 parafuso', 'fixador:cavilha': 'Colocar 1 cavilha',
  'fixador:minifix': 'Colocar 1 minifix', 'fixador:dobradica': 'Instalar 1 dobradiça', 'fixador:corredica': 'Instalar 1 corrediça', 'fixador:cola': 'Colar 1 junção',
  'fixador:prego': 'Pregar 1 prego', 'fixador:encaixe': 'Fazer 1 encaixe', 'fixador:puxador': 'Instalar 1 puxador', 'fixador:outro': 'Outro tipo de fixação (1 un.)' };
const EXEMPLO_MAQUINA = { corte: 'Seccionadora', bordo: 'Coladeira de borda', furacao: 'Furadeira' };
const preparoDe = (id) => get(`/produtos/${id}/preparo${qs({ unidade_id: estado.unidadeId })}`);

const campoNum = (valor, aoMudar, extra = {}) => {
  const i = h('input', { type: 'number', min: '0', step: 'any', value: valor ?? '', ...extra });
  i.addEventListener('change', () => aoMudar(i.value === '' ? null : Number(i.value)));
  return i;
};
const secao = (id, titulo, ajuda, ...filhos) => h('div', { class: 'card', id: `sec-${id}` }, h('h2', null, titulo), ajuda ? h('p', { class: 'muted small' }, ajuda) : null, ...filhos);

// ---------------------------------------------------------------- lista de itens
export async function itens(el) {
  const lista = (await get('/produtos?ativo=true')).filter((p) => p.tipo === 'produto');
  const preparos = await Promise.all(lista.map((p) => tentar(() => preparoDe(p.id))));
  const nome = h('input', { placeholder: 'ex.: Armário de cozinha' });
  const criar = async () => {
    if (!nome.value.trim()) return toast('Digite o nome do item.', true);
    const r = await tentar(() => post('/produtos', { nome: nome.value.trim(), tipo: 'produto' }));
    if (r) location.hash = `#/itens/${r.id}`;
  };
  montar(el, h('h1', null, 'Itens e peças'),
    h('p', { class: 'pergunta' }, 'Qual item você fabrica? Informe o item final e as peças que o compõem; o resto a plataforma deduz e o plano de trabalho sai com os tempos.'),
    h('div', { class: 'card' }, h('h2', null, 'Novo item'), h('div', { class: 'row' }, nome, h('button', { class: 'pri big', onclick: criar }, 'Criar item e informar as peças'))),
    lista.length ? h('div', { class: 'card' }, h('h2', null, 'Seus itens'), lista.map((p, i) => {
      const pr = preparos[i];
      return h('div', { class: 'linha-prod' }, h('div', null, h('a', { href: `#/itens/${p.id}`, class: 'big-txt' }, p.nome),
        pr ? h('div', { class: 'small' }, pr.pendencias_total ? badge(`${pr.pendencias_total} informação(ões) faltando`, 'b-warn') : badge('Pronto para o plano', 'b-ok'),
          pr.atividades.length ? ` · ${pr.atividades.map((a) => a.titulo).join(', ')}` : '') : null),
        h('a', { class: 'btn', href: `#/itens/${p.id}` }, 'Abrir'));
    })) : null);
}

// ---------------------------------------------------------------- o item
export async function item(el, id) {
  const p = await get(`/produtos/${id}`);
  const [resumo, corpo, planoBox] = [h('div'), h('div'), h('div')];
  let prep;

  const irPara = (secaoId) => document.getElementById(`sec-${secaoId}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });

  // Situação do item: atividades deduzidas + o que falta em cada seção. Atualiza sem redesenhar as seções.
  const atualizar = async () => {
    prep = await preparoDe(id);
    montar(resumo, h('div', { class: 'card resumo' },
      h('div', null, h('strong', null, 'Atividades deduzidas das peças: '),
        prep.atividades.length ? prep.atividades.map((a) => h('span', { class: 'chip' }, a.titulo, a.pecas ? ` (${fmtNum(a.pecas, 0)} peça${a.pecas === 1 ? '' : 's'})` : '')) : h('span', { class: 'muted' }, 'informe as peças para ver')),
      h('div', { class: 'secoes-status' }, prep.secoes.map((s) => h('button', { class: `status ${s.completo ? 'ok' : 'falta'}`, onclick: () => irPara(s.codigo) },
        s.completo ? '✓ ' : '● ', s.titulo, s.completo ? '' : ` — falta ${s.pendencias.length}`)))));
    const faltas = prep.secoes.filter((s) => s.pendencias.length);
    montar(planoBox, secao('plano', 'Plano de trabalho', 'O sistema monta os passos a partir das atividades acima (transporte, usinagem, montagem, conferência) e calcula o tempo de cada um com as suas peças, máquinas, pessoas e distâncias.',
      faltas.length ? h('div', { class: 'aviso' }, h('strong', null, 'Para o tempo ficar completo, falta:'),
        faltas.map((s) => h('div', null, h('a', { href: '#', onclick: (e) => { e.preventDefault(); irPara(s.codigo); } }, s.titulo), h('ul', null, s.pendencias.map((t) => h('li', null, t))))),
        h('p', { class: 'muted small' }, 'Dá para gerar o plano agora: o que ainda não tem dado aparece como “sem tempo”, nunca como um valor inventado.'))
        : h('div', { class: 'ok-box card' }, h('strong', null, '✓ Tudo informado.'), ' O plano sairá completo.'),
      h('button', { class: 'pri big', disabled: !prep.pode_gerar, onclick: () => abrirGerar({ produtoId: id, produtoNome: p.nome }) }, 'Gerar plano de trabalho'),
      !prep.pode_gerar ? h('p', { class: 'muted small' }, 'Informe ao menos uma peça para gerar o plano.') : null,
      h('p', null, h('a', { href: '#/planos' }, 'Ver planos anteriores'))));
  };

  const recarregar = async () => {
    const y = window.scrollY;
    const [est, un, recursos, c, refs, perfis] = await Promise.all([get(`/produtos/${id}/estrutura`), get(`/unidades/${estado.unidadeId}`),
      get(`/recursos${qs({ unidade_id: estado.unidadeId })}`), get(`/contorno${qs({ unidade_id: estado.unidadeId })}`), get('/referencias-tempo'),
      get(`/perfis-mao-de-obra${qs({ unidade_id: estado.unidadeId })}`)]);
    await atualizar();
    const perfil = perfis.find((x) => x.id === un.perfil_equipe_id) ?? null;
    montar(corpo, secPecas(id, p, est, recarregar), secAgentes(prep, un, perfil, recursos.filter((r) => r.ativo), refs, { recarregar, atualizar }), secAmbiente(prep, c, perfil, { recarregar, atualizar }));
    window.scrollTo(0, y);
  };

  montar(el, h('p', null, h('a', { href: '#/itens' }, '← Itens e peças')), h('h1', null, p.nome),
    h('p', { class: 'pergunta' }, 'Informe as peças que compõem o item, quem e o que trabalha nele e onde acontece. O plano de trabalho com os tempos sai daqui.'),
    resumo, corpo, planoBox);
  await recarregar();
}

// ---------------------------------------------------------------- 1. item e peças
function secPecas(id, p, est, recarregar) {
  const comps = est.componentes;
  const nomeDe = (cid) => comps.find((c) => c.id === cid)?.nome ?? 'o conjunto';
  const salvar = async (c, campos) => { if (await tentar(() => patch(`/produtos/${id}/componentes/${c.id}`, campos))) recarregar(); };
  const celula = (c, k, tipo = 'number', ajuda) => {
    const i = entrada(tipo, c[k], { class: tipo === 'number' ? 'n' : '', step: 'any', min: '0', placeholder: ajuda });
    i.addEventListener('change', () => salvar(c, { [k]: tipo === 'number' ? num(i.value) : i.value.trim() }));
    return i;
  };
  const linhas = comps.map((c) => h('tr', null,
    h('td', null, celula(c, 'nome', 'text')), h('td', null, celula(c, 'quantidade')), h('td', null, celula(c, 'material', 'text', 'ex.: MDF')), h('td', null, celula(c, 'grupo', 'text')),
    h('td', null, h('div', { class: 'inline nw' }, celula(c, 'comprimento_m', 'number', 'comp.'), celula(c, 'largura_m', 'number', 'larg.'), celula(c, 'espessura_m', 'number', 'esp.'))),
    h('td', { class: 'pk' }, celula(c, 'peso_kg', 'number', c.peso_estimado_kg ? `~${fmtNum(c.peso_estimado_kg)} est.` : 'kg')),
    h('td', null, celula(c, 'furos')), h('td', null, celula(c, 'bordas_m')),
    h('td', null, h('button', { class: 'sm dng', title: 'Remover', onclick: () => confirmar(`Remover "${c.nome}" e suas ligações?`, async () => { if (await tentar(() => del(`/produtos/${id}/componentes/${c.id}`))) recarregar(); }, 'Remover') }, '✕'))));
  const novo = { nome: h('input', { placeholder: 'ex.: Lateral' }), qtd: h('input', { type: 'number', min: '0', step: 'any', value: '1' }), mat: h('input', { placeholder: 'material (ex.: MDF)' }) };
  const sel = (lista, vazio) => h('select', null, h('option', { value: '' }, vazio), lista.map(([v, r]) => h('option', { value: v }, r)));
  const [lc, la, lm, lf] = [sel(comps.map((c) => [c.id, c.nome]), 'Componente…'), sel(comps.map((c) => [c.id, c.nome]), 'ao conjunto'), sel(METODOS, ''), h('input', { type: 'number', min: '0', step: '1', value: '0' })];
  lm.value = 'parafuso';
  return secao('pecas', `1. ${p.nome}: peças`, 'Quantidade é por unidade do item. Medidas em metros. Se não souber o peso, informe material e medidas: o sistema estima e marca como “estimado”. Furos e borda definem se haverá furação e colagem de borda.',
    h('div', { class: 'inline' }, h('button', { class: 'ia', onclick: () => descreverComIA(p, recarregar) }, 'Descrever com a IA')),
    h('p', { class: 'muted small' }, 'Escreva em texto livre (ex.: “armário de MDF com 2 portas, 3 prateleiras e 4 dobradiças”). A IA propõe a lista; você confere antes de salvar.'),
    comps.length ? h('div', { class: 'tw' }, h('table', null, h('thead', null, h('tr', null, ['Peça', 'Qtd.', 'Material', 'Subconjunto', 'Medidas (m)', 'Peso (kg)', 'Furos', 'Borda (m)', ''].map((t) => h('th', null, t)))), h('tbody', null, linhas)))
      : h('p', { class: 'muted' }, 'Nenhuma peça ainda. Adicione abaixo ou use “Descrever com a IA”.'),
    h('div', { class: 'row' }, novo.nome, novo.qtd, novo.mat, h('button', { onclick: async () => {
      if (!novo.nome.value.trim()) return toast('Digite o nome da peça.', true);
      if (await tentar(() => post(`/produtos/${id}/componentes`, { nome: novo.nome.value.trim(), quantidade: Number(novo.qtd.value) || 1, material: novo.mat.value.trim() }))) recarregar();
    } }, '+ Adicionar peça')),
    h('h3', null, 'Como as peças se juntam'),
    h('p', { class: 'muted small' }, 'Diga como cada peça se liga a outra e quantos parafusos, cavilhas etc. são usados por unidade do item. Sem isso, o tempo de montagem fica como pendência.'),
    est.ligacoes.length ? est.ligacoes.map((l) => h('div', { class: 'lig' }, h('span', null, `${nomeDe(l.componente_id)} → ${nomeDe(l.ligado_a_id)} · ${rotMetodo(l.metodo)} · ${l.fixadores} un.`),
      h('button', { class: 'sm dng', onclick: async () => { if (await tentar(() => del(`/produtos/${id}/ligacoes/${l.id}`))) recarregar(); } }, '✕'))) : h('p', { class: 'muted' }, 'Nenhuma ligação informada.'),
    comps.length ? h('div', { class: 'row' }, lc, la, lm, lf, h('button', { onclick: async () => {
      if (!lc.value) return toast('Escolha a peça.', true);
      if (await tentar(() => post(`/produtos/${id}/ligacoes`, { componente_id: Number(lc.value), ligado_a_id: num(la.value), metodo: lm.value, fixadores: Number(lf.value) || 0 }))) recarregar();
    } }, '+ Adicionar ligação')) : null);
}

function descreverComIA(p, depois) {
  const txt = h('textarea', { placeholder: 'Armário de MDF com 2 portas, 3 prateleiras, 1 fundo, duas laterais, 4 dobradiças e 1 base' });
  modal(`Descrever — ${p.nome}`, h('div', null, h('label', null, 'Do que é feito e como se junta?'), txt), { acoes: (fechar) => [
    h('button', { onclick: fechar }, 'Cancelar'),
    h('button', { class: 'ia', onclick: async (e) => {
      if (txt.value.trim().length < 3) return toast('Descreva o item.', true);
      e.target.disabled = true;
      const r = await tentar(() => post(`/produtos/${p.id}/interpretar`, { descricao: txt.value.trim() }));
      e.target.disabled = false;
      if (!r) return;
      fechar(); conferirProposta(p, r, depois);
    } }, 'Gerar lista')] });
}

function conferirProposta(p, r, depois) {
  const existentes = h('input', { type: 'checkbox' });
  modal('Confira a lista sugerida', h('div', null, avisoIA('Medidas, pesos e fixadores que a IA não conhece ficam em branco: você completa depois. Nada foi salvo ainda.'),
    tabela([{ t: 'Peça', f: (c) => c.nome }, { t: 'Qtd.', f: (c) => fmtNum(c.quantidade, 2) }, { t: 'Material', f: (c) => c.material || '—' }, { t: 'Subconjunto', f: (c) => c.grupo }], r.componentes, 'A IA não encontrou peças no texto.'),
    r.ligacoes.length ? h('div', null, h('h3', null, 'Ligações'), r.ligacoes.map((l) => h('div', { class: 'lig' }, `${l.componente} → ${l.ligado_a || 'o conjunto'} · ${rotMetodo(l.metodo)} · ${l.fixadores} un.`))) : null,
    r.dados_faltantes.length ? h('div', { class: 'aviso' }, h('strong', null, 'A IA não soube: '), r.dados_faltantes.join('; ')) : null,
    r.aviso ? h('p', { class: 'muted small' }, r.aviso) : null,
    h('label', null, existentes, ' Substituir a lista atual do item (senão, só acrescenta o que ainda não existe)')),
  { larga: true, acoes: (fechar) => [h('button', { onclick: fechar }, 'Descartar'),
    h('button', { class: 'pri', disabled: !r.componentes.length, onclick: async () => {
      if (await tentar(() => post(`/produtos/${p.id}/estrutura`, { componentes: r.componentes, ligacoes: r.ligacoes, substituir: existentes.checked }), 'Lista salva.')) { fechar(); depois(); }
    } }, 'Usar esta lista')] });
}

// ---------------------------------------------------------------- 2. agentes
function secAgentes(prep, un, perfil, ativos, refs, { recarregar, atualizar }) {
  const bl = un.jornada?.blocos ?? [['08:00', '12:00'], ['13:00', '17:00']];
  const f = {
    pessoas: h('input', { type: 'number', min: '1', max: '50', step: '1', value: un.equipe_pessoas ?? 1 }),
    m1: h('input', { type: 'time', value: bl[0]?.[0] ?? '' }), m2: h('input', { type: 'time', value: bl[0]?.[1] ?? '' }),
    t1: h('input', { type: 'time', value: bl[1]?.[0] ?? '' }), t2: h('input', { type: 'time', value: bl[1]?.[1] ?? '' }),
    uteis: h('input', { type: 'checkbox', checked: un.jornada?.so_dias_uteis ?? true }),
  };
  const salvarEquipe = async () => {
    const blocos = [[f.m1.value, f.m2.value], [f.t1.value, f.t2.value]].filter((b) => b[0] && b[1]);
    if (!f.pessoas.value || Number(f.pessoas.value) < 1) return toast('Informe quantas pessoas trabalham.', true);
    if (!blocos.length) return toast('Informe ao menos um bloco de horário.', true);
    if (await tentar(() => patch(`/unidades/${estado.unidadeId}`, { equipe_pessoas: Number(f.pessoas.value), jornada: { blocos, so_dias_uteis: f.uteis.checked } }), 'Mão de obra salva.')) recarregar();
  };
  const maoDeObra = h('div', null, h('h3', null, 'Pessoas'),
    h('p', { class: 'muted small' }, un.equipe_pessoas ? 'O horário define quando cada passo do plano começa e termina.' : 'Ainda não confirmado: o plano usa 1 pessoa, das 08:00 às 12:00 e das 13:00 às 17:00.'),
    h('div', { class: 'row' }, h('div', null, h('label', null, 'Quantas pessoas trabalham juntas?'), f.pessoas)),
    h('div', { class: 'row' }, h('div', null, h('label', null, 'Manhã: das'), f.m1), h('div', null, h('label', null, 'até'), f.m2), h('div', null, h('label', null, 'Tarde: das'), f.t1), h('div', null, h('label', null, 'até'), f.t2)),
    h('label', { class: 'inline' }, f.uteis, ' Trabalhar só de segunda a sexta'),
    h('p', null, h('button', { class: un.equipe_pessoas ? '' : 'pri', onclick: salvarEquipe }, un.equipe_pessoas ? 'Salvar pessoas e horário' : 'Confirmar pessoas e horário')));

  // Perfil de referência da equipe: alimenta a ergonomia (bancada × cotovelo, limite de carga, gasto de energia), nunca a produtividade.
  const e = {
    sexo: h('select', { 'aria-label': 'Sexo' }, [['nao_informado', 'Escolha…'], ['feminino', 'Feminino'], ['masculino', 'Masculino'], ['misto', 'Equipe mista']].map(([v, r]) => h('option', { value: v }, r))),
    estatura: h('input', { type: 'number', min: '50', max: '250', step: 'any', value: perfil?.estatura_cm ?? '', placeholder: 'ex.: 168' }),
    peso: h('input', { type: 'number', min: '10', max: '400', step: 'any', value: perfil?.peso_corporal_kg ?? '', placeholder: 'ex.: 70' }),
    faixa: h('select', { 'aria-label': 'Faixa etária' }, [['adulto', 'Adulto'], ['menor_18', 'Menor de 18 anos']].map(([v, r]) => h('option', { value: v }, r))),
    limite: h('input', { type: 'number', min: '1.6', max: '30', step: 'any', value: perfil?.limite_energetico_kcal_min ?? '', placeholder: 'kcal/min (opcional)' }),
  };
  e.sexo.value = perfil?.sexo ?? 'nao_informado'; e.faixa.value = perfil?.faixa_etaria ?? 'adulto';
  const salvarPerfil = async () => {
    if (e.sexo.value === 'nao_informado') return toast('Escolha o sexo da equipe.', true);
    if (!e.estatura.value) return toast('Informe a altura (estatura) da equipe.', true);
    const corpo = { sexo: e.sexo.value, estatura_cm: Number(e.estatura.value), peso_corporal_kg: num(e.peso.value), faixa_etaria: e.faixa.value, limite_energetico_kcal_min: num(e.limite.value) };
    const r = await tentar(() => (perfil ? patch(`/perfis-mao-de-obra/${perfil.id}`, corpo) : post('/perfis-mao-de-obra', { unidade_id: estado.unidadeId, nome: 'Equipe', ...corpo })), 'Perfil da equipe salvo.');
    if (r && !perfil && !(await tentar(() => patch(`/unidades/${estado.unidadeId}`, { perfil_equipe_id: r.id })))) return;
    if (r) recarregar();
  };
  const ergonomia = h('div', null, h('h3', null, 'Ergonomia da equipe'),
    h('p', { class: 'muted small' }, 'Altura, sexo e peso mudam o tempo pela ergonomia, não pela produtividade: a altura é comparada com a bancada (postura e fadiga); o sexo e a idade definem o limite de carga (quantas pessoas e viagens); o peso estima o gasto de energia. O ritmo continua sendo medido, nunca deduzido. Equipe com pessoas diferentes: informe a mais restritiva (ex.: a de menor estatura) ou “Equipe mista”.'),
    h('div', { class: 'row' }, h('div', null, h('label', null, 'Sexo'), e.sexo), h('div', null, h('label', null, 'Altura (cm)'), e.estatura), h('div', null, h('label', null, 'Peso corporal (kg)'), e.peso), h('div', null, h('label', null, 'Faixa etária'), e.faixa)),
    estado.avancado ? detalhes('Opções de especialista', h('label', null, 'Limite de gasto energético adotado (kcal/min) — para o descanso de Murrell; as fontes divergem, por isso não há valor embutido'), e.limite) : null,
    h('p', null, h('button', { class: perfil ? '' : 'pri', onclick: salvarPerfil }, perfil ? 'Salvar perfil da equipe' : 'Confirmar perfil da equipe')));

  const blocoMaquina = (a) => {
    const lista = ativos.filter((r) => r.funcao === a.funcao);
    const nomeNovo = h('input', { placeholder: `ex.: ${EXEMPLO_MAQUINA[a.funcao] || 'Máquina'}` });
    const capNova = h('input', { type: 'number', min: '0', step: 'any', placeholder: 'peças por hora' });
    const adicionar = async () => {
      if (!nomeNovo.value.trim()) return toast('Digite o nome da máquina.', true);
      if (await tentar(() => post('/recursos', { unidade_id: estado.unidadeId, nome: nomeNovo.value.trim(), tipo: 'maquina', funcao: a.funcao,
        capacidade: num(capNova.value), capacidade_unidade: 'un/h' }), 'Máquina cadastrada.')) recarregar();
    };
    return h('div', { class: 'maquina' }, h('h4', null, a.titulo), h('p', { class: 'muted small' }, `Qual máquina faz ${a.titulo.toLowerCase()} e quantas peças por hora ela faz?`),
      lista.map((r) => h('div', { class: 'row' }, h('div', null, h('label', null, 'Máquina'), h('input', { value: r.nome, onchange: async (e) => { if (e.target.value.trim()) await tentar(() => patch(`/recursos/${r.id}`, { nome: e.target.value.trim() }), 'Salvo.'); } })),
        h('div', null, h('label', null, 'Peças por hora'), campoNum(r.capacidade, async (v) => { if (await tentar(() => patch(`/recursos/${r.id}`, { capacidade: v, capacidade_unidade: 'un/h' }), 'Salvo.') !== undefined) atualizar(); }, { placeholder: 'ex.: 60' })),
        h('button', { class: 'sm dng', title: 'Remover', onclick: async () => { if (await tentar(() => patch(`/recursos/${r.id}`, { ativo: false }))) recarregar(); } }, '✕'))),
      h('div', { class: 'row' }, nomeNovo, capNova, h('button', { onclick: adicionar }, lista.length ? '+ Outra máquina' : '+ Adicionar máquina')));
  };
  const precisam = prep.atividades.filter((a) => a.funcao);
  const maquinas = h('div', null, h('h3', null, 'Máquinas'),
    precisam.length ? [h('p', { class: 'muted small' }, 'Uma para cada atividade deste item que usa equipamento. A capacidade (peças por hora) permite calcular o tempo de máquina.'), precisam.map(blocoMaquina)]
      : h('p', { class: 'muted' }, 'Com as peças informadas, nenhuma atividade precisa de máquina (ou ainda não há peças com medidas).'));
  const tempos = detalhes('Opcional: tempos de montagem da sua oficina',
    h('div', { class: 'card' }, h('p', { class: 'muted small' }, 'Valores genéricos de partida. Troque pelos da sua oficina (em minutos): o plano passa a usá-los e avisa que são seus.'),
      refs.map((r) => h('div', { class: 'row ref' }, h('div', { class: 'l' }, REF_ROTULOS[r.chave] || r.chave, h('span', { class: 'muted small' }, r.informada ? ` (seu valor; padrão ${fmtNum(r.padrao_minutos, 2)} min)` : ' (valor genérico)')),
        campoNum(r.minutos, async (v) => { if (v !== null && await tentar(() => api('PUT', '/referencias-tempo', { chave: r.chave, minutos: v }), 'Salvo.')) recarregar(); }),
        r.informada ? h('button', { class: 'sm', onclick: async () => { if (await tentar(() => del(`/referencias-tempo/${encodeURIComponent(r.chave)}`))) recarregar(); } }, 'Voltar ao padrão') : h('span')))));
  return secao('agentes', '2. Agentes: pessoas e máquinas', 'Quem e o que transforma as peças em item pronto.', maoDeObra, ergonomia, maquinas, tempos);
}

// ---------------------------------------------------------------- 3. ambiente
function secAmbiente(prep, c, perfil, { recarregar, atualizar }) {
  const [locais, equip] = [c.locais, c.equipamentos];
  const cods = new Set(prep.atividades.map((a) => a.codigo));
  const funcoes = new Set(prep.atividades.filter((a) => a.funcao).map((a) => a.funcao));
  const maquinas = equip.filter((e) => funcoes.has(e.funcao));
  const criarLocal = async (nome, tipo = 'area') => { if (await tentar(() => post('/espacos', { unidade_id: estado.unidadeId, nome, tipo }))) recarregar(); };
  const tem = (tipo, palavra) => locais.some((l) => l.tipo === tipo || l.nome.toLowerCase().includes(palavra));
  const falta = [];
  if (cods.has('movimentacao') && !tem('estoque', 'estoque')) falta.push(['Estoque', 'estoque']);
  if ((cods.has('montagem') || cods.has('inspecao')) && !tem('montagem', 'montag')) falta.push(['Montagem', 'montagem']);

  const novo = h('input', { placeholder: 'ex.: Bancada de corte' });
  const tipoNovo = h('select', { 'aria-label': 'Tipo do local' }, TIPOS_LOCAL.map(([v, r]) => h('option', { value: v }, r)));
  const locaisBox = h('div', null, h('h3', null, 'Locais'), h('p', { class: 'muted small' }, `Os lugares por onde a peça passa. Estoque e montagem são necessários; o resto depende das máquinas. A altura da bancada${perfil?.estatura_cm ? ' (cm)' : ''} é comparada com o cotovelo da equipe para a ergonomia.`),
    falta.length ? h('div', { class: 'inline' }, falta.map(([n, t]) => h('button', { class: 'pri', onclick: () => criarLocal(n, t) }, `+ Criar “${n}”`))) : null,
    locais.map((l) => h('div', { class: 'row' }, h('input', { value: l.nome, 'aria-label': 'Nome do local', onchange: async (e) => { if (e.target.value.trim() && await tentar(() => patch(`/espacos/${l.id}`, { nome: e.target.value.trim() }), 'Salvo.')) atualizar(); } }),
      (() => { const t = h('select', { 'aria-label': 'Tipo do local', onchange: async (e) => { if (await tentar(() => patch(`/espacos/${l.id}`, { tipo: e.target.value }))) recarregar(); } }, TIPOS_LOCAL.map(([v, r]) => h('option', { value: v }, r))); t.value = l.tipo; return t; })(),
      campoNum(l.altura_trabalho_m ? Math.round(l.altura_trabalho_m * 1000) / 10 : null, async (v) => { if (await tentar(() => patch(`/espacos/${l.id}`, { altura_trabalho_m: v === null ? null : v / 100 }), 'Salvo.') !== undefined) atualizar(); }, { placeholder: 'bancada (cm)', 'aria-label': `Altura da bancada de ${l.nome}`, title: 'Altura da bancada ou posto de trabalho, em cm' }),
      h('button', { class: 'sm dng', title: 'Remover', onclick: async () => { if (await tentar(() => patch(`/espacos/${l.id}`, { ativo: false }))) recarregar(); } }, '✕'))),
    h('div', { class: 'row' }, novo, tipoNovo, h('button', { onclick: () => { if (!novo.value.trim()) return toast('Digite o nome do local.', true); criarLocal(novo.value.trim(), tipoNovo.value); } }, '+ Adicionar local')));

  const ondeBox = maquinas.length ? h('div', null, h('h3', null, 'Onde fica cada máquina'), maquinas.map((m) => h('div', { class: 'row' }, h('div', { class: 'l' }, h('strong', null, m.nome)),
    (() => { const s = h('select', { 'aria-label': `Local de ${m.nome}`, onchange: async (e) => { if (await tentar(() => patch(`/recursos/${m.id}`, { espaco_id: num(e.target.value) }), 'Salvo.') !== undefined) recarregar(); } },
      h('option', { value: '' }, 'Escolha o local…'), locais.map((l) => h('option', { value: l.id }, l.nome))); s.value = m.espaco_id ?? ''; return s; })()))) : null;

  const distBox = cods.has('movimentacao') ? h('div', null, h('h3', null, 'Distância entre os locais (em metros)'), h('p', { class: 'muted small' }, 'Só as distâncias que o transporte das peças realmente usa.'),
    c.distancias.length ? c.distancias.map((d) => h('div', { class: 'row' }, h('div', { class: 'l' }, `${d.origem} ↔ ${d.destino}`),
      campoNum(d.metros, async (v) => { if (v !== null && await tentar(() => api('PUT', '/distancias', { origem_id: d.origem_id, destino_id: d.destino_id, metros: v }), 'Salvo.') !== undefined) atualizar(); }, { placeholder: 'metros' })))
      : h('p', { class: 'muted' }, 'Aparecem aqui quando houver estoque, locais de máquina e montagem cadastrados.')) : null;

  const cond = detalhes('Opcional: condições do ambiente (calor, ruído) em cada local',
    h('div', { class: 'card' }, h('p', { class: 'muted small' }, 'Se informar, o plano alerta quando passar de limites de referência. A “folga extra” (%) aumenta o tempo dos passos feitos naquele local; só use se souber o valor.'),
      locais.length ? locais.map((l) => h('div', { class: 'row' }, h('div', { class: 'l' }, l.nome),
        [['temperatura_c', 'Temperatura (°C)', l.temperatura_c], ['ruido_db', 'Ruído (dB)', l.ruido_db], ['tolerancia_ambiente_pct', 'Folga extra (%)', l.tolerancia_ambiente_pct]].map(([k, rot, v]) =>
          h('div', null, h('label', null, rot), campoNum(v, async (n) => { await tentar(() => patch(`/espacos/${l.id}`, { [k]: n }), 'Salvo.'); })))))
        : h('p', { class: 'muted' }, 'Cadastre os locais primeiro.')));
  return secao('ambiente', '3. Ambiente', 'Onde isso acontece: locais, onde fica cada máquina e as distâncias.', locaisBox, ondeBox, distBox, cond);
}

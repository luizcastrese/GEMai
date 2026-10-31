import { api, baixar, del, get, patch, post, qs } from './api.js';
import { estado } from './estado.js';
import { avisoIA, badge, confirmar, detalhes, fmtData, fmtMin, fmtNum, h, kpi, modal, montar, statusBadge, tabela, tentar, toast } from './ui.js';

const num = (v) => (v === '' || v === null || v === undefined ? null : Number(v));
const METODOS = [['parafuso', 'Parafuso'], ['cavilha', 'Cavilha'], ['minifix', 'Minifix'], ['dobradica', 'Dobradiça'], ['corredica', 'Corrediça'],
  ['cola', 'Cola'], ['prego', 'Prego'], ['encaixe', 'Encaixe'], ['puxador', 'Puxador'], ['outro', 'Outro']];
const rotMetodo = (m) => (METODOS.find((x) => x[0] === m) || [m, m])[1];
const TIPO_PASSO = { movimentacao: 'Transporte', corte: 'Corte', furacao: 'Furação', bordo: 'Borda', montagem: 'Montagem', inspecao: 'Conferência', outro: 'Outro' };
const diaSem = (iso) => new Date(iso).toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: '2-digit' });
const hora = (iso) => new Date(iso).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
const dataChave = (iso) => new Date(iso).toLocaleDateString('pt-BR');

function entrada(tipo, valor, extra = {}) { return h('input', { type: tipo, value: valor ?? '', ...extra }); }

// ---------------------------------------------------------------- produtos
export async function produtos(el) {
  const lista = await get('/produtos?ativo=true');
  const nome = h('input', { placeholder: 'ex.: Armário de cozinha' });
  montar(el, h('h1', null, 'Produtos'),
    h('p', { class: 'muted' }, 'Informe do que o produto é feito (componentes) e como as peças se juntam. A partir disso o sistema monta o plano de trabalho com os tempos.'),
    h('div', { class: 'card' }, tabela([{ t: 'Produto', f: (p) => h('a', { href: `#/produtos/${p.id}` }, p.nome) }, { t: 'Descrição', f: (p) => p.descricao }],
      lista.filter((p) => p.tipo === 'produto'), 'Nenhum produto ainda. Crie o primeiro abaixo.')),
    h('div', { class: 'card' }, h('h3', null, 'Novo produto'), h('div', { class: 'row' }, nome, h('button', { class: 'pri', onclick: async () => {
      if (!nome.value.trim()) return toast('Digite o nome do produto.', true);
      const r = await tentar(() => post('/produtos', { nome: nome.value.trim(), tipo: 'produto' }));
      if (r) location.hash = `#/produtos/${r.id}`;
    } }, 'Criar produto'))));
}

export async function produtoDetalhe(el, id) {
  const p = await get(`/produtos/${id}`);
  const area = h('div');
  const desenhar = async () => {
    const est = await get(`/produtos/${id}/estrutura`);
    const comps = est.componentes;
    const nomeDe = (cid) => comps.find((c) => c.id === cid)?.nome ?? 'o conjunto';
    const salvar = async (c, campos) => { if (await tentar(() => patch(`/produtos/${id}/componentes/${c.id}`, campos))) { await desenhar(); } };
    const celula = (c, k, tipo = 'number', ajuda) => {
      const i = entrada(tipo, c[k], { class: tipo === 'number' ? 'n' : '', step: 'any', min: '0', placeholder: ajuda });
      i.addEventListener('change', () => salvar(c, { [k]: tipo === 'number' ? num(i.value) : i.value.trim() }));
      return i;
    };
    const linhas = comps.map((c) => h('tr', null,
      h('td', null, celula(c, 'nome', 'text')), h('td', null, celula(c, 'quantidade')), h('td', null, celula(c, 'material', 'text', 'ex.: MDF')),
      h('td', null, celula(c, 'grupo', 'text')),
      h('td', null, h('div', { class: 'inline nw' }, celula(c, 'comprimento_m', 'number', 'comp.'), celula(c, 'largura_m', 'number', 'larg.'), celula(c, 'espessura_m', 'number', 'esp.'))),
      h('td', { class: 'pk' }, celula(c, 'peso_kg', 'number', c.peso_estimado_kg ? `~${fmtNum(c.peso_estimado_kg)} est.` : 'kg')),
      h('td', null, celula(c, 'furos')), h('td', null, celula(c, 'bordas_m')),
      h('td', null, h('button', { class: 'sm dng', title: 'Remover', onclick: () => confirmar(`Remover "${c.nome}" e suas ligações?`, async () => { if (await tentar(() => del(`/produtos/${id}/componentes/${c.id}`))) desenhar(); }, 'Remover') }, '✕'))));
    const novo = { nome: h('input', { placeholder: 'ex.: Lateral' }), qtd: h('input', { type: 'number', min: '0', step: 'any', value: '1' }), mat: h('input', { placeholder: 'material (ex.: MDF)' }) };
    const sComps = h('div', { class: 'card' }, h('h2', null, '1. Componentes'),
      h('p', { class: 'muted small' }, 'Quantidade é por unidade do produto. Medidas em metros. Se não souber o peso, informe material e medidas: o sistema estima e marca como "estimado".'),
      comps.length ? h('div', { class: 'tw' }, h('table', null, h('thead', null, h('tr', null, ['Componente', 'Qtd.', 'Material', 'Subconjunto', 'Medidas (m)', 'Peso (kg)', 'Furos', 'Borda (m)', ''].map((t) => h('th', null, t)))),
        h('tbody', null, linhas))) : h('p', { class: 'muted' }, 'Nenhum componente ainda. Adicione abaixo ou use "Descrever com a IA".'),
      h('div', { class: 'row' }, novo.nome, novo.qtd, novo.mat, h('button', { onclick: async () => {
        if (!novo.nome.value.trim()) return toast('Digite o nome do componente.', true);
        if (await tentar(() => post(`/produtos/${id}/componentes`, { nome: novo.nome.value.trim(), quantidade: Number(novo.qtd.value) || 1, material: novo.mat.value.trim() }))) desenhar();
      } }, '+ Adicionar componente')));

    const sel = (lista, vazio) => h('select', null, h('option', { value: '' }, vazio), lista.map(([v, r]) => h('option', { value: v }, r)));
    const [lc, la, lm, lf] = [sel(comps.map((c) => [c.id, c.nome]), 'Componente…'), sel(comps.map((c) => [c.id, c.nome]), 'ao conjunto'), sel(METODOS, ''), h('input', { type: 'number', min: '0', step: '1', value: '0' })];
    lm.value = 'parafuso';
    const sLig = h('div', { class: 'card' }, h('h2', null, '2. Como as peças se juntam'),
      h('p', { class: 'muted small' }, 'Diga como cada componente se liga a outro e quantos parafusos, cavilhas etc. são usados por unidade do produto. Sem isso, o tempo de montagem fica como pendência.'),
      est.ligacoes.length ? est.ligacoes.map((l) => h('div', { class: 'lig' }, h('span', null, `${nomeDe(l.componente_id)} → ${nomeDe(l.ligado_a_id)} · ${rotMetodo(l.metodo)} · ${l.fixadores} un.`),
        h('button', { class: 'sm dng', onclick: async () => { if (await tentar(() => del(`/produtos/${id}/ligacoes/${l.id}`))) desenhar(); } }, '✕')))
        : h('p', { class: 'muted' }, 'Nenhuma ligação informada.'),
      comps.length ? h('div', { class: 'row' }, lc, la, lm, lf, h('button', { onclick: async () => {
        if (!lc.value) return toast('Escolha o componente.', true);
        if (await tentar(() => post(`/produtos/${id}/ligacoes`, { componente_id: Number(lc.value), ligado_a_id: num(la.value), metodo: lm.value, fixadores: Number(lf.value) || 0 }))) desenhar();
      } }, '+ Adicionar ligação')) : null);

    const sPlano = h('div', { class: 'card' }, h('h2', null, '3. Plano de trabalho'),
      h('p', { class: 'muted' }, 'O sistema considera movimentação, usinagem, montagem, conferência, carga, ambiente e a jornada, e entrega os passos com horários.'),
      h('div', { class: 'inline' }, h('button', { class: 'pri big', disabled: !comps.length, onclick: () => abrirGerar({ produtoId: id, produtoNome: p.nome }) }, 'Gerar plano de trabalho'),
        h('a', { class: 'btn', href: '#/planos' }, 'Ver planos anteriores')));
    montar(area, sComps, sLig, sPlano);
  };

  montar(el, h('p', null, h('a', { href: '#/produtos' }, '← Produtos')), h('h1', null, p.nome),
    h('div', { class: 'inline' }, h('button', { class: 'ia', onclick: () => descreverComIA(p, desenhar) }, 'Descrever com a IA')),
    h('p', { class: 'muted small' }, 'Escreva em texto livre (ex.: "armário de MDF com 2 portas, 3 prateleiras e 4 dobradiças"). A IA propõe a lista; você confere antes de salvar.'), area);
  await desenhar();
}

function descreverComIA(p, depois) {
  const txt = h('textarea', { placeholder: 'Armário de MDF com 2 portas, 3 prateleiras, 1 fundo, duas laterais, 4 dobradiças e 1 base' });
  const fechar0 = modal(`Descrever — ${p.nome}`, h('div', null, h('label', null, 'Do que é feito e como se junta?'), txt), { acoes: (fechar) => [
    h('button', { onclick: fechar }, 'Cancelar'),
    h('button', { class: 'ia', onclick: async (e) => {
      if (txt.value.trim().length < 3) return toast('Descreva o produto.', true);
      e.target.disabled = true;
      const r = await tentar(() => post(`/produtos/${p.id}/interpretar`, { descricao: txt.value.trim() }));
      e.target.disabled = false;
      if (!r) return;
      fechar(); conferirProposta(p, r, depois);
    } }, 'Gerar lista')] });
  return fechar0;
}

function conferirProposta(p, r, depois) {
  const existentes = h('input', { type: 'checkbox' });
  modal('Confira a lista sugerida', h('div', null, avisoIA('Medidas, pesos e fixadores que a IA não conhece ficam em branco: você completa depois. Nada foi salvo ainda.'),
    tabela([{ t: 'Componente', f: (c) => c.nome }, { t: 'Qtd.', f: (c) => fmtNum(c.quantidade, 2) }, { t: 'Material', f: (c) => c.material || '—' }, { t: 'Subconjunto', f: (c) => c.grupo }], r.componentes, 'A IA não encontrou componentes no texto.'),
    r.ligacoes.length ? h('div', null, h('h3', null, 'Ligações'), r.ligacoes.map((l) => h('div', { class: 'lig' }, `${l.componente} → ${l.ligado_a || 'o conjunto'} · ${rotMetodo(l.metodo)} · ${l.fixadores} un.`))) : null,
    r.dados_faltantes.length ? h('div', { class: 'aviso' }, h('strong', null, 'A IA não soube: '), r.dados_faltantes.join('; ')) : null,
    r.aviso ? h('p', { class: 'muted small' }, r.aviso) : null,
    h('label', null, existentes, ' Substituir a lista atual do produto (senão, só acrescenta o que ainda não existe)')),
  { larga: true, acoes: (fechar) => [h('button', { onclick: fechar }, 'Descartar'),
    h('button', { class: 'pri', disabled: !r.componentes.length, onclick: async () => {
      if (await tentar(() => post(`/produtos/${p.id}/estrutura`, { componentes: r.componentes, ligacoes: r.ligacoes, substituir: existentes.checked }), 'Lista salva.')) { fechar(); depois(); }
    } }, 'Usar esta lista')] });
}

// ---------------------------------------------------------------- gerar / recalcular
const isoLocal = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);

export async function abrirGerar({ produtoId, produtoNome, plano }) {
  const cfg = plano?.config || {};
  const bl = cfg.blocos || [['08:00', '12:00'], ['13:00', '17:00']];
  const perfis = await get(`/perfis-mao-de-obra${qs({ unidade_id: estado.unidadeId, ativo: true })}`);
  const f = {
    qtd: entrada('number', plano?.quantidade ?? 1, { min: '0', step: 'any' }),
    ini: entrada('datetime-local', cfg.inicio ? isoLocal(new Date(cfg.inicio)) : isoLocal(new Date())),
    pess: entrada('number', cfg.pessoas ?? 1, { min: '1', step: '1' }),
    m1: entrada('time', bl[0][0]), m2: entrada('time', bl[0][1]), t1: entrada('time', bl[1][0]), t2: entrada('time', bl[1][1]),
    uteis: h('input', { type: 'checkbox', checked: cfg.so_dias_uteis ?? true }),
    perfil: h('select', null, h('option', { value: '' }, 'Padrão'), perfis.map((x) => h('option', { value: x.id }, x.nome))),
    fadiga: entrada('number', cfg.fadiga_pct_hora ?? 0, { min: '0', max: '10', step: 'any' }),
  };
  if (cfg.perfil_id) f.perfil.value = cfg.perfil_id;
  const corpo = h('div', null,
    h('div', { class: 'row' }, h('div', null, h('label', null, 'Quantas unidades?'), f.qtd), h('div', null, h('label', null, 'Quando começa?'), f.ini), h('div', null, h('label', null, 'Quantas pessoas na equipe?'), f.pess)),
    h('h3', null, 'Jornada de trabalho'),
    h('div', { class: 'row' }, h('div', null, h('label', null, 'Manhã: das'), f.m1), h('div', null, h('label', null, 'até'), f.m2), h('div', null, h('label', null, 'Tarde: das'), f.t1), h('div', null, h('label', null, 'até'), f.t2)),
    h('label', null, f.uteis, ' Trabalhar só de segunda a sexta'),
    h('h3', null, 'Quem vai fazer'),
    perfis.length ? h('div', null, h('label', null, 'Perfil da pessoa (ritmo e limites de carga)'), f.perfil, h('div', { class: 'muted small' }, '"Padrão" usa ritmo normal. Perfis são cadastrados em Configurações › Cadastros avançados (com detalhes técnicos ligados).')) : h('p', { class: 'muted small' }, 'Sem perfil cadastrado: o sistema usa o ritmo normal (100%) e os limites de carga padrão.'),
    estado.avancado ? detalhes('Opções de especialista', h('label', null, 'Perda de rendimento por hora trabalhada no dia (%) — opcional, informe só se tiver medido'), f.fadiga) : null);
  modal(plano ? 'Recalcular plano' : `Plano de trabalho — ${produtoNome}`, corpo, { acoes: (fechar) => [h('button', { onclick: fechar }, 'Cancelar'),
    h('button', { class: 'pri', onclick: async (e) => {
      const m = [[f.m1.value, f.m2.value], [f.t1.value, f.t2.value]].filter((b) => b[0] && b[1]);
      if (!m.length) return toast('Informe ao menos um bloco de horário.', true);
      const corpoReq = { produto_id: produtoId, unidade_id: estado.unidadeId, quantidade: Number(f.qtd.value) || 1, inicio: f.ini.value ? new Date(f.ini.value).toISOString() : null,
        blocos: m, so_dias_uteis: f.uteis.checked, pessoas: Number(f.pess.value) || 1, perfil_id: num(f.perfil.value), fadiga_pct_hora: Number(f.fadiga.value) || 0 };
      e.target.disabled = true;
      const r = await tentar(() => (plano ? post(`/planos/${plano.id}/recalcular`, corpoReq) : post('/planos', corpoReq)));
      e.target.disabled = false;
      if (r) { fechar(); if (plano) window.dispatchEvent(new HashChangeEvent('hashchange')); else location.hash = `#/planos/${r.id}`; }
    } }, plano ? 'Recalcular' : 'Gerar plano')] });
}

// ---------------------------------------------------------------- planos
export async function planos(el) {
  const [ps, prods] = await Promise.all([get(`/planos${qs({ unidade_id: estado.unidadeId })}`), get('/produtos?ativo=true')]);
  const nome = (id) => prods.find((x) => x.id === id)?.nome ?? '—';
  const escolha = h('select', null, h('option', { value: '' }, 'Escolha o produto…'), prods.filter((x) => x.tipo === 'produto').map((x) => h('option', { value: x.id }, x.nome)));
  montar(el, h('h1', null, 'Planos de trabalho'),
    h('p', { class: 'muted' }, 'Cada plano é calculado a partir do produto, da oficina e de quem vai fazer. O número que importa é o tempo padrão por unidade. Só vale depois que você confirmar.'),
    h('div', { class: 'card' }, h('div', { class: 'row' }, escolha, h('button', { class: 'pri', onclick: () => {
      if (!escolha.value) return toast('Escolha o produto.', true);
      abrirGerar({ produtoId: Number(escolha.value), produtoNome: nome(Number(escolha.value)) });
    } }, 'Novo plano'))),
    h('div', { class: 'card' }, tabela([
      { t: 'Plano', f: (p) => h('a', { href: `#/planos/${p.id}` }, p.nome) },
      { t: 'Situação', f: (p) => (p.status === 'rascunho' ? badge('Rascunho', 'b-warn') : p.status === 'cancelado' ? badge('Cancelado', 'b-err') : statusBadge(p.status)) },
      { t: 'Tempo padrão por unidade', f: (p) => fmtMin(p.totais.tempo_padrao_min / (p.quantidade || 1)) }, { t: 'Termina', f: (p) => fmtData(p.totais.fim) },
      { t: 'Pendências', f: (p) => (p.totais.completo ? badge('Completo', 'b-ok') : badge('Incompleto', 'b-warn')) },
      { t: 'Ordem', f: (p) => (p.ordem_id ? h('a', { href: `#/ordens/${p.ordem_id}` }, 'Ver ordem') : '—') }], ps, 'Nenhum plano ainda. Escolha um produto acima.')));
}

export async function planoDetalhe(el, id) {
  const p = await get(`/planos/${id}`);
  const t = p.totais;
  const ops = p.passos;
  const recarregar = () => window.dispatchEvent(new HashChangeEvent('hashchange'));
  const alertas = [...p.alertas, ...ops.flatMap((s) => s.alertas.map((a) => ({ ...a, passo: s.nome })))];
  const vistos = new Set();
  const unicos = alertas.filter((a) => { const k = a.msg; if (vistos.has(k)) return false; vistos.add(k); return true; });

  let dia = null;
  const linhas = [];
  ops.forEach((s) => {
    if (s.inicio_prev) {
      const d = dataChave(s.inicio_prev);
      if (d !== dia) { dia = d; linhas.push(h('tr', { class: 'dia' }, h('td', { colspan: '6' }, diaSem(s.inicio_prev)))); }
    }
    const quem = [`${s.pessoas} pessoa${s.pessoas > 1 ? 's' : ''}`, s.recurso_nome, s.origem_nome && s.destino_nome && s.origem_nome !== s.destino_nome ? `${s.origem_nome} → ${s.destino_nome}` : (s.destino_nome || s.origem_nome)].filter(Boolean).join(' · ');
    linhas.push(h('tr', { class: s.tempo_padrao_min === null ? 'semtempo' : '' },
      h('td', null, s.sequencia),
      h('td', null, h('strong', null, s.nome), h('div', { class: 'muted small' }, `${TIPO_PASSO[s.tipo] || s.tipo} · ${quem}`),
        s.faltantes.length ? h('div', { class: 'warn-l small' }, `Falta: ${s.faltantes.join('; ')}`) : null,
        s.alertas.map((a) => h('div', { class: `small ${a.categoria === 'seguranca' ? 'seg-l' : 'warn-l'}` }, a.msg)),
        estado.avancado ? detalhes('Como o tempo foi calculado', s.composicao.map((c) => h('div', { class: 'small' }, `${c.nome}: ${c.minutos === null ? c.motivo : `${fmtNum(c.minutos, 2)} min`}`)),
          s.elementos.map((e) => (e.justificativa ? h('div', { class: 'muted small' }, `• ${e.nome}: ${e.justificativa}`) : null))) : null),
      h('td', null, s.inicio_prev ? hora(s.inicio_prev) : '—'), h('td', null, s.fim_prev ? hora(s.fim_prev) : '—'),
      h('td', null, s.tempo_padrao_min === null ? badge('Sem tempo', 'b-warn') : fmtMin(s.tempo_padrao_min)),
      h('td', { class: 'noprint' }, s.tempo_prep_min ? h('span', { class: 'muted small' }, `preparo ${fmtMin(s.tempo_prep_min)}`) : '')));
  });

  const acoes = h('div', { class: 'inline noprint' },
    p.status === 'rascunho' ? h('button', { class: 'pri big', onclick: () => confirmar(t.completo
      ? 'Confirmar este plano? Os tempos passam a valer como plano de referência.'
      : 'Este plano tem pendências (passos sem tempo). Confirmar mesmo assim? Esses passos ficarão "sem base" na ordem.', async () => {
      if (await tentar(() => post(`/planos/${id}/confirmar`), 'Plano confirmado.')) recarregar();
    }, 'Confirmar plano') }, 'Confirmar plano') : null,
    estado.avancado && p.status === 'confirmado' && !p.ordem_id ? h('button', { class: 'pri big', onclick: () => gerarOrdem(p) }, 'Gerar ordem de produção') : null,
    p.ordem_id ? h('a', { class: 'btn big', href: `#/ordens/${p.ordem_id}` }, 'Abrir a ordem') : null,
    p.status === 'rascunho' ? h('button', { onclick: () => abrirGerar({ produtoId: p.produto_id, produtoNome: p.produto_nome, plano: p }) }, 'Recalcular') : null,
    h('button', { onclick: () => window.print() }, 'Imprimir'),
    h('button', { onclick: () => tentar(() => baixar(`/planos/${id}/exportar.csv`, `plano-${id}.csv`)) }, 'Baixar planilha'),
    p.status !== 'cancelado' && !p.ordem_id ? h('button', { class: 'dng', onclick: () => confirmar('Cancelar este plano?', async () => { if (await tentar(() => post(`/planos/${id}/cancelar`))) recarregar(); }, 'Cancelar plano') }, 'Cancelar plano') : null);

  montar(el, h('p', { class: 'noprint' }, h('a', { href: '#/planos' }, '← Planos de trabalho')),
    h('h1', null, p.nome), h('div', { class: 'inline' }, p.status === 'rascunho' ? badge('Rascunho: falta você conferir e confirmar', 'b-warn') : statusBadge(p.status),
      badge(`Confiança: ${{ baixa: 'baixa', media: 'média', alta: 'alta' }[p.confianca]}`, p.confianca === 'baixa' ? 'b-warn' : ''), badge(p.provedor.startsWith('claude') ? 'Montado pela IA' : 'Montado por regras locais', 'b-ia')),
    (p.provedor.startsWith('claude') ? avisoIA : (txt) => h('div', { class: 'aviso-ia' }, h('strong', null, 'Sugestão automática. '), txt))('Este plano é uma estimativa. Tempos de montagem e conferência partem de referências genéricas até você informar os seus (Contorno físico) ou medir a produção. Quando houver apontamentos reais, compare com o previsto.'),
    h('div', { class: 'hero' },
      h('div', { class: 'sub' }, t.completo ? 'Tempo padrão por unidade' : 'Tempo padrão por unidade (parcial: faltam dados)'),
      h('div', { class: 'big' }, t.tempo_padrao_min ? fmtMin(t.tempo_padrao_min / (p.quantidade || 1)) : '—'),
      h('div', { class: 'sub' }, `${fmtNum(p.quantidade, 2)} unidade(s) = ${fmtMin(t.tempo_padrao_min)} de trabalho · termina ${t.fim ? fmtData(t.fim) : '—'} (${t.dias || '—'} dia(s) de trabalho)`),
      t.completo ? null : h('div', { class: 'small warn-l' }, 'Passos sem tempo não entram na conta: o prazo real será maior. Complete o que falta abaixo e recalcule.')),
    h('div', { class: 'grid g4' }, kpi('Tempo de trabalho', fmtMin(t.tempo_padrao_min)), kpi('Pessoas-hora', `${fmtNum(t.horas_homem, 1)} h`),
      kpi('Começa', t.inicio ? fmtData(t.inicio) : '—', 'peq'), kpi('Termina', t.fim ? fmtData(t.fim) : '—', 'peq'), kpi('Dias de trabalho', t.dias || '—')),
    p.faltantes.length ? h('div', { class: 'aviso' }, h('strong', null, 'Para o plano ficar completo, faltam: '), h('ul', null, p.faltantes.map((f) => h('li', null, f))),
      h('div', { class: 'inline noprint' }, h('a', { class: 'btn', href: '#/contorno' }, 'Preencher a Oficina'), h('a', { class: 'btn', href: `#/produtos/${p.produto_id}` }, 'Completar o produto'),
        p.status === 'rascunho' ? h('span', { class: 'muted small' }, 'Depois, use "Recalcular".') : null)) : null,
    unicos.length ? h('div', { class: 'card' }, h('h3', null, 'Atenção'), h('ul', null, unicos.map((a) => h('li', { class: a.categoria === 'seguranca' ? 'seg-l' : '' }, a.msg)))) : null,
    h('div', { class: 'card' }, h('div', { class: 'tw' }, h('table', null, h('thead', null, h('tr', null, ['#', 'Passo', 'Começa', 'Termina', 'Tempo', ''].map((x) => h('th', null, x)))), h('tbody', null, linhas)))),
    acoes,
    detalhes('Premissas do plano', h('ul', null, p.premissas.map((x) => h('li', { class: 'small' }, x)))));
}

function gerarOrdem(p) {
  const cliente = h('input', { placeholder: 'opcional' }); const prazo = h('input', { type: 'date' });
  modal('Gerar ordem de produção', h('div', null, h('p', { class: 'muted' }, 'A ordem usa os passos e tempos deste plano. Depois é só liberar e acompanhar na fila.'), h('label', null, 'Cliente'), cliente, h('label', null, 'Prazo'), prazo),
    { acoes: (fechar) => [h('button', { onclick: fechar }, 'Cancelar'), h('button', { class: 'pri', onclick: async () => {
      const r = await tentar(() => post(`/planos/${p.id}/gerar-ordem`, { cliente: cliente.value.trim() || null, prazo: prazo.value || null }), 'Ordem criada.');
      if (r) { fechar(); location.hash = `#/ordens/${r.id}`; }
    } }, 'Gerar ordem')] });
}

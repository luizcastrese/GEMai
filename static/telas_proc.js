import { api, get, patch, post, qs } from './api.js';
import { estado } from './estado.js';
import { formulario, h, modal, montar, tabela, tentar, toast, badge, fmtNum } from './ui.js';

// Cadastros avançados (modo especialista): perfis de mão de obra, equipe, materiais e produtos em tabelas.
// O caminho normal é a tela do item (peças, agentes e ambiente); aqui ficam só os ajustes finos.
const ENT = {
  recursos: { rot: 'Recursos', un: true, campos: [
    { k: 'nome', rotulo: 'Nome (ex.: Máquina 01)' }, { k: 'tipo', rotulo: 'Tipo', tipo: 'select', opcoes: [['maquina', 'Máquina'], ['posto', 'Posto'], ['ferramenta', 'Ferramenta'], ['instalacao', 'Instalação']] },
    { k: 'processos_relacionados', rotulo: 'Processos relacionados', tipo: 'lista' }, { k: 'capacidade', rotulo: 'Capacidade', tipo: 'number', nulo: true },
    { k: 'capacidade_unidade', rotulo: 'Unidade da capacidade (use un/h ou un/min para o gêmeo digital)', padrao: 'un/h' }, { k: 'equipes_habilitadas', rotulo: 'Equipes habilitadas', tipo: 'lista' },
    { k: 'local_posto', rotulo: 'Local / posto' }, { k: 'horas_disponiveis_dia', rotulo: 'Horas disponíveis por dia útil', tipo: 'number', padrao: 8 },
    { k: 'ultima_manutencao', rotulo: 'Última manutenção', tipo: 'date', nulo: true }, { k: 'proxima_manutencao', rotulo: 'Próxima manutenção', tipo: 'date', nulo: true }],
    cols: [{ t: 'Nome', f: (r) => r.nome }, { t: 'Tipo', f: (r) => r.tipo }, { t: 'Capacidade', f: (r) => (r.capacidade ? `${r.capacidade} ${r.capacidade_unidade}` : '—') },
      { t: 'Tempo médio (calculado)', f: (r) => (r.tempo_medio_min ? `${fmtNum(r.tempo_medio_min, 2)} min/un` : '—') },
      { t: 'Preparação média', f: (r) => (r.tempo_preparacao_medio_min ? `${fmtNum(r.tempo_preparacao_medio_min)} min` : '—') }, { t: 'Próx. manutenção', f: (r) => r.proxima_manutencao || '—' }] },
  espacos: { rot: 'Espaços (contorno físico)', un: true, campos: [
    { k: 'nome', rotulo: 'Nome (ex.: Estoque de chapas)' }, { k: 'tipo', rotulo: 'Tipo', tipo: 'select', opcoes: [['area', 'Área'], ['posto', 'Posto'], ['estoque', 'Estoque'], ['expedicao', 'Expedição']] },
    { k: 'comprimento_m', rotulo: 'Comprimento (m)', tipo: 'number', nulo: true }, { k: 'largura_m', rotulo: 'Largura (m)', tipo: 'number', nulo: true },
    { k: 'pe_direito_m', rotulo: 'Pé-direito (m)', tipo: 'number', nulo: true }, { k: 'piso', rotulo: 'Piso' },
    { k: 'temperatura_c', rotulo: 'Temperatura média (°C)', tipo: 'number', nulo: true }, { k: 'umidade_pct', rotulo: 'Umidade relativa (%)', tipo: 'number', nulo: true },
    { k: 'ruido_db', rotulo: 'Ruído (dB(A))', tipo: 'number', nulo: true }, { k: 'iluminancia_lux', rotulo: 'Iluminância (lux)', tipo: 'number', nulo: true }, { k: 'observacoes', rotulo: 'Observações', tipo: 'textarea' }],
    cols: [{ t: 'Nome', f: (r) => r.nome }, { t: 'Tipo', f: (r) => r.tipo }, { t: 'Dimensões', f: (r) => (r.comprimento_m && r.largura_m ? `${r.comprimento_m} × ${r.largura_m} m` : '—') },
      { t: 'Temperatura', f: (r) => (r.temperatura_c === null ? '—' : `${r.temperatura_c} °C`) }, { t: 'Origem', f: (r) => (r.origem === 'ia' ? badge('Sugerido pela IA', 'b-ia') : 'Manual') }] },
  'perfis-mao-de-obra': { rot: 'Perfis de mão de obra', un: true, aviso: 'Perfis de REFERÊNCIA (não são pessoas). Sexo, estatura e peso corporal servem apenas a limites de carga e conferências ergonômicas; NÃO alteram o tempo nem medem produtividade. O ritmo deve ser calibrado por medição. Não use estes dados para decisões de contratação ou alocação de pessoas.',
    campos: [{ k: 'nome', rotulo: 'Nome do perfil (ex.: Auxiliar de corte)' },
      { k: 'sexo', rotulo: 'Sexo de referência (para limites de carga)', tipo: 'select', opcoes: [['nao_informado', 'Não informado'], ['feminino', 'Feminino'], ['masculino', 'Masculino'], ['misto', 'Misto']] },
      { k: 'faixa_etaria', rotulo: 'Faixa etária', tipo: 'select', opcoes: [['adulto', 'Adulto'], ['menor_18', 'Menor de 18 anos']] },
      { k: 'estatura_cm', rotulo: 'Estatura (cm)', tipo: 'number', nulo: true }, { k: 'peso_corporal_kg', rotulo: 'Peso corporal (kg)', tipo: 'number', nulo: true },
      { k: 'altura_cotovelo_cm', rotulo: 'Altura do cotovelo (cm) — para comparar com a altura de trabalho', tipo: 'number', nulo: true },
      { k: 'experiencia', rotulo: 'Experiência', tipo: 'select', opcoes: [['iniciante', 'Iniciante'], ['intermediario', 'Intermediário'], ['experiente', 'Experiente']] },
      { k: 'ritmo_pct', rotulo: 'Ritmo (100 = normal; calibre por medição)', tipo: 'number', padrao: 100 },
      { k: 'limite_energetico_kcal_min', rotulo: 'Limite de gasto energético adotado (kcal/min) — para o descanso de Murrell; opcional, as fontes divergem', tipo: 'number', nulo: true },
      { k: 'observacoes', rotulo: 'Observações', tipo: 'textarea' }],
    cols: [{ t: 'Perfil', f: (r) => r.nome }, { t: 'Sexo ref.', f: (r) => r.sexo }, { t: 'Estatura', f: (r) => (r.estatura_cm ? `${r.estatura_cm} cm` : '—') },
      { t: 'Peso corporal', f: (r) => (r.peso_corporal_kg ? `${r.peso_corporal_kg} kg` : '—') }, { t: 'Experiência', f: (r) => r.experiencia }, { t: 'Ritmo', f: (r) => `${r.ritmo_pct}%` }] },
  pessoas: { rot: 'Pessoas', un: true, campos: [{ k: 'nome', rotulo: 'Nome' }, { k: 'funcao', rotulo: 'Função' }, { k: 'equipe', rotulo: 'Equipe' }, { k: 'habilitacoes', rotulo: 'Habilitações', tipo: 'lista' }],
    cols: [{ t: 'Nome', f: (r) => r.nome }, { t: 'Função', f: (r) => r.funcao }, { t: 'Equipe', f: (r) => r.equipe }, { t: 'Habilitações', f: (r) => r.habilitacoes.join(', ') }] },
  materiais: { rot: 'Materiais', campos: [{ k: 'nome', rotulo: 'Nome' }, { k: 'tipo', rotulo: 'Tipo' }, { k: 'unidade_medida', rotulo: 'Unidade de medida' }],
    cols: [{ t: 'Nome', f: (r) => r.nome }, { t: 'Tipo', f: (r) => r.tipo }, { t: 'Unidade', f: (r) => r.unidade_medida }] },
  produtos: { rot: 'Produtos / serviços', campos: [{ k: 'nome', rotulo: 'Nome' }, { k: 'tipo', rotulo: 'Tipo', tipo: 'select', opcoes: [['produto', 'Produto'], ['servico', 'Serviço']] }, { k: 'descricao', rotulo: 'Descrição', tipo: 'textarea' },
    { k: 'peso_kg', rotulo: 'Peso (kg)', tipo: 'number', nulo: true }, { k: 'comprimento_m', rotulo: 'Comprimento (m)', tipo: 'number', nulo: true }, { k: 'largura_m', rotulo: 'Largura (m)', tipo: 'number', nulo: true }, { k: 'altura_m', rotulo: 'Altura (m)', tipo: 'number', nulo: true }],
    cols: [{ t: 'Nome', f: (r) => r.nome }, { t: 'Tipo', f: (r) => r.tipo }, { t: 'Peso', f: (r) => (r.peso_kg === null ? '—' : `${r.peso_kg} kg`) }, { t: 'Descrição', f: (r) => r.descricao }] },
};

// Campos e colunas que só aparecem no modo especialista.
const AVANCADO = {
  recursos: ['processos_relacionados', 'equipes_habilitadas', 'local_posto', 'horas_disponiveis_dia', 'ultima_manutencao', 'proxima_manutencao', 'capacidade_unidade'],
  espacos: ['pe_direito_m', 'piso', 'temperatura_c', 'umidade_pct', 'ruido_db', 'iluminancia_lux', 'observacoes'],
  pessoas: ['habilitacoes'], produtos: ['comprimento_m', 'largura_m', 'altura_m'],
};
const COLS_SIMPLES = { recursos: 3, espacos: 3, pessoas: 3, 'perfis-mao-de-obra': 6 };
const ROTULOS = { recursos: 'Equipamentos', espacos: 'Locais', pessoas: 'Equipe', materiais: 'Materiais', produtos: 'Produtos e serviços', 'perfis-mao-de-obra': 'Perfis de mão de obra' };
const AJUSTES = { recursos: { capacidade: 'Quantas peças por hora faz? (opcional, ajuda a IA a prever o tempo)' }, espacos: { nome: 'Nome do local (ex.: Estoque de chapas)' } };

export async function cadastros(el) {
  let aba = 'recursos';
  const area = h('div'); const abas = h('div', { class: 'tabs' });
  const desenhar = async () => {
    montar(abas, Object.entries(ENT).filter(([k]) => estado.avancado || k !== 'perfis-mao-de-obra').map(([k, e]) => h('button', { class: aba === k ? 'on' : '', onclick: () => { aba = k; desenhar(); } }, ROTULOS[k] || e.rot)));
    const e = ENT[aba];
    const itens = await get(`/${aba}${qs({ unidade_id: e.un ? estado.unidadeId : '' })}`);
    const espacos = aba === 'recursos' ? await get(`/espacos${qs({ unidade_id: estado.unidadeId, ativo: true })}`) : [];
    const abrir = (item) => {
      let campos = aba === 'recursos' ? [...e.campos, { k: 'espaco_id', rotulo: 'Em que local fica?', tipo: 'select', num: true, opcoes: [['', '—'], ...espacos.map((x) => [x.id, x.nome])] }] : e.campos;
      campos = campos.filter((c) => estado.avancado || !(AVANCADO[aba] || []).includes(c.k)).map((c) => ((AJUSTES[aba] || {})[c.k] ? { ...c, rotulo: AJUSTES[aba][c.k] } : c));
      const f = formulario(campos, item || {});
      modal(item ? `Editar — ${item.nome}` : `Novo — ${e.rot}`, f.el, { acoes: (fechar) => [h('button', { onclick: fechar }, 'Cancelar'),
        h('button', { class: 'pri', onclick: async () => {
          const v = f.valores(); if (!item && e.un) v.unidade_id = estado.unidadeId;
          if (await tentar(() => (item ? patch(`/${aba}/${item.id}`, v) : post(`/${aba}`, v)), 'Salvo.')) { fechar(); desenhar(); }
        } }, 'Salvar')] });
    };
    montar(area, e.aviso ? h('div', { class: 'aviso' }, e.aviso) : null, h('p', null, h('button', { class: 'pri', onclick: () => abrir() }, '+ Adicionar')),
      h('div', { class: 'card' }, tabela([...(estado.avancado ? e.cols : e.cols.slice(0, COLS_SIMPLES[aba] || 99)), { t: 'Situação', f: (r) => (r.ativo ? badge('Ativo', 'b-ok') : badge('Inativo')) },
        { t: '', f: (r) => h('div', { class: 'inline' }, h('button', { class: 'sm', onclick: () => abrir(r) }, 'Editar'),
          h('button', { class: 'sm', onclick: async () => { if (await tentar(() => patch(`/${aba}/${r.id}`, { ativo: !r.ativo }))) desenhar(); } }, r.ativo ? 'Desativar' : 'Reativar')) }], itens)),
      aba === 'espacos' ? await painelDistancias(itens, desenhar) : null,
      h('p', { class: 'muted small' }, 'Itens não são excluídos para preservar o histórico; desative o que não for mais usado.'));
  };
  montar(el, h('h1', null, 'Equipamentos e locais'), h('p', { class: 'muted' }, 'Cadastre o que existe na sua operação. Quanto mais a IA souber (capacidades, locais, distâncias, pesos), melhor ela prevê o tempo.'), abas, area);
  await desenhar();
}

async function painelDistancias(espacos, refazer) {
  const ativos = espacos.filter((x) => x.ativo);
  const ds = await get(`/distancias${qs({ unidade_id: estado.unidadeId })}`);
  const nome = (id) => espacos.find((x) => x.id === id)?.nome || id;
  const f = formulario([{ k: 'origem_id', rotulo: 'Entre', tipo: 'select', num: true, opcoes: ativos.map((x) => [x.id, x.nome]) },
    { k: 'destino_id', rotulo: 'e', tipo: 'select', num: true, opcoes: ativos.map((x) => [x.id, x.nome]) }, { k: 'metros', rotulo: 'Distância (m)', tipo: 'number' }]);
  return h('div', { class: 'card' }, h('h3', null, 'Distâncias entre espaços'),
    h('p', { class: 'muted small' }, 'Valem nos dois sentidos e alimentam o cálculo de deslocamento do tempo planejado.'),
    tabela([{ t: 'Espaços', f: (d) => `${nome(d.origem_id)} ↔ ${nome(d.destino_id)}` }, { t: 'Metros', f: (d) => fmtNum(d.metros, 1) }], ds, 'Nenhuma distância cadastrada.'),
    f.el, h('p', null, h('button', { class: 'pri', onclick: async () => {
      const v = f.valores();
      if (!v.origem_id || !v.destino_id || v.metros === null) return toast('Escolha os dois espaços e informe a distância.', true);
      if (await tentar(() => api('PUT', '/distancias', v), 'Distância salva.')) refazer();
    } }, 'Salvar distância')));
}

import { get, patch, post, qs } from './api.js';
import { estado, carregarBase } from './estado.js';
import { badge, confirmar, fmtData, formulario, h, modal, montar, statusBadge, tabela, tentar, toast, avisoIA } from './ui.js';
import { rotuloTipo, verRecomendacao } from './ia_view.js';

// ---------------------------------------------------------------- sugestões da IA
export async function recomendacoes(el) {
  const filtro = { status: 'pendente' };
  const area = h('div');
  const carregar = async () => {
    const rs = await get(`/recomendacoes${qs({ unidade_id: estado.unidadeId, status: filtro.status })}`);
    montar(area, h('div', { class: 'card' }, tabela([
      { t: 'Quando', f: (r) => fmtData(r.criada_em) }, { t: 'Tipo', f: (r) => rotuloTipo(r.tipo) }, { t: 'Título', f: (r) => r.titulo },
      { t: 'Fonte', f: (r) => badge(r.provedor, 'b-ia') }, { t: 'Situação', f: (r) => statusBadge(r.status) },
      { t: '', f: (r) => h('button', { class: 'sm', onclick: () => verRecomendacao(r, carregar) }, 'Ver') }], rs, 'Nenhuma sugestão neste filtro.')));
  };
  montar(el, h('h1', null, 'Sugestões da IA'), avisoIA('Toda saída da IA fica aqui como sugestão. Nada vira dado do ERP sem a decisão de um responsável.'),
    h('div', { class: 'card row' }, h('div', null, h('label', null, 'Situação'), h('select', { onchange: (e) => { filtro.status = e.target.value; carregar(); } },
      [['pendente', 'Pendentes'], ['aprovada', 'Validadas'], ['aplicada', 'Aplicadas'], ['rejeitada', 'Rejeitadas'], ['', 'Todas']].map(([v, r]) => h('option', { value: v }, r)))),
      h('button', { class: 'ia', onclick: async () => {
        const mk = (tipo) => async () => { const r = await tentar(() => post('/ia/analises', { tipo, unidade_id: estado.unidadeId })); if (r) { carregar(); verRecomendacao(r, carregar); } };
        modal('Nova análise', h('div', { class: 'inline' }, h('button', { class: 'ia', onclick: mk('indicadores_sugeridos') }, 'Indicadores sugeridos'), h('button', { class: 'ia', onclick: mk('processos_semelhantes') }, 'Operações semelhantes')), { acoes: (f) => [h('button', { onclick: f }, 'Fechar')] });
      } }, 'Nova análise…')), area);
  await carregar();
}

// ---------------------------------------------------------------- usuários
export async function usuarios(el) {
  const us = await get('/usuarios');
  const abrir = (u) => {
    const f = formulario([{ k: 'nome', rotulo: 'Nome' }, ...(u ? [] : [{ k: 'email', rotulo: 'E-mail', tipo: 'email' }, { k: 'senha', rotulo: 'Senha inicial (mín. 10, maiúscula, minúscula e número)', tipo: 'password' }]),
      { k: 'perfil', rotulo: 'Perfil', tipo: 'select', opcoes: [['operador', 'Operador (interface simplificada)'], ['gestor', 'Gestor (edita processos, aprova)'], ['admin', 'Administrador (tudo)']] },
      ...(u ? [{ k: 'ativo', rotulo: 'Ativo', tipo: 'bool' }] : [])], u || { perfil: 'operador' });
    const marcas = estado.unidades.map((x) => ({ x, c: h('input', { type: 'checkbox', checked: u ? u.unidade_ids.includes(x.id) : false }) }));
    modal(u ? `Editar — ${u.nome}` : 'Novo usuário', h('div', null, f.el, h('label', null, 'Unidades com acesso (administradores veem todas)'),
      marcas.map(({ x, c }) => h('label', { class: 'inline' }, c, x.nome))), { acoes: (fechar) => [h('button', { onclick: fechar }, 'Cancelar'), h('button', { class: 'pri', onclick: async () => {
        const v = f.valores(); v.unidade_ids = marcas.filter((m) => m.c.checked).map((m) => m.x.id);
        if (await tentar(() => (u ? patch(`/usuarios/${u.id}`, v) : post('/usuarios', v)), 'Salvo.')) { fechar(); usuarios(el); }
      } }, 'Salvar')] });
  };
  const senha = (u) => {
    const f = formulario([{ k: 'nova_senha', rotulo: 'Nova senha', tipo: 'password' }]);
    modal(`Redefinir senha — ${u.nome}`, h('div', null, f.el, h('p', { class: 'muted small' }, 'As sessões abertas do usuário são encerradas.')), { acoes: (fechar) => [h('button', { onclick: fechar }, 'Cancelar'),
      h('button', { class: 'pri', onclick: async () => { if (await tentar(() => post(`/usuarios/${u.id}/redefinir-senha`, f.valores()), 'Senha redefinida.')) fechar(); } }, 'Redefinir')] });
  };
  montar(el, h('div', { class: 'top' }, h('h1', null, 'Usuários'), h('button', { class: 'pri', onclick: () => abrir() }, '+ Novo usuário')),
    h('div', { class: 'card' }, tabela([{ t: 'Nome', f: (u) => u.nome }, { t: 'E-mail', f: (u) => u.email }, { t: 'Perfil', f: (u) => u.perfil },
      { t: 'Unidades', f: (u) => u.unidade_ids.map((i) => estado.unidades.find((x) => x.id === i)?.nome || i).join(', ') }, { t: 'Situação', f: (u) => (u.ativo ? badge('Ativo', 'b-ok') : badge('Inativo', 'b-err')) },
      { t: '', f: (u) => h('div', { class: 'inline' }, h('button', { class: 'sm', onclick: () => abrir(u) }, 'Editar'), h('button', { class: 'sm', onclick: () => senha(u) }, 'Senha')) }], us)));
}

// ---------------------------------------------------------------- empresa e unidades
export async function empresa(el) {
  const e = estado.empresa;
  const f = formulario([{ k: 'nome', rotulo: 'Nome da empresa' }, { k: 'segmento', rotulo: 'Segmento' }, { k: 'fuso', rotulo: 'Fuso horário (ex.: America/Sao_Paulo)' },
    { k: 'permite_ia_externa', rotulo: 'Permitir envio de dados desta empresa a um provedor externo de IA (Claude/Anthropic)', tipo: 'bool',
      ajuda: e.ia_disponivel ? 'Se desmarcado, a IA usa apenas regras locais e nenhum dado sai do sistema. Dados enviados: descrição da operação, respostas do diagnóstico e indicadores agregados (nunca senhas, e-mails ou documentos).' : 'Este servidor não tem chave de IA externa configurada; a IA usa regras locais.' }], e);
  const uni = await get('/unidades');
  const fu = formulario([{ k: 'nome', rotulo: 'Nome da nova unidade' }]);
  montar(el, h('h1', null, 'Empresa e unidades'),
    h('div', { class: 'card' }, f.el, h('p', { class: 'small muted' }, `Provedor de IA ativo: ${e.ia_provedor_ativo}`), h('p', null, h('button', { class: 'pri', onclick: async () => {
      if (await tentar(() => patch('/empresa', f.valores()), 'Empresa atualizada.')) { await carregarBase(); empresa(el); }
    } }, 'Salvar'))),
    h('div', { class: 'card' }, h('h2', null, 'Unidades'), tabela([{ t: 'Nome', f: (u) => u.nome }, { t: 'Situação', f: (u) => (u.ativa ? badge('Ativa', 'b-ok') : badge('Inativa')) },
      { t: '', f: (u) => h('button', { class: 'sm', onclick: async () => { if (await tentar(() => patch(`/unidades/${u.id}`, { ativa: !u.ativa }))) { await carregarBase(); empresa(el); } } }, u.ativa ? 'Desativar' : 'Reativar') }], uni),
      fu.el, h('button', { onclick: async () => { if (await tentar(() => post('/unidades', fu.valores()), 'Unidade criada.')) { await carregarBase(); empresa(el); } } }, 'Criar unidade')));
}

// ---------------------------------------------------------------- auditoria
export async function auditoria(el) {
  const filtro = { entidade: '', acao: '' };
  const area = h('div');
  const carregar = async () => {
    const ev = await get(`/auditoria${qs({ entidade: filtro.entidade, acao: filtro.acao, limite: 200 })}`);
    montar(area, h('div', { class: 'card' }, tabela([{ t: 'Quando', f: (x) => fmtData(x.em) }, { t: 'Usuário', f: (x) => x.usuario_id ?? '—' }, { t: 'Ação', f: (x) => x.acao },
      { t: 'Entidade', f: (x) => `${x.entidade} #${x.entidade_id ?? ''}` }, { t: 'IP', f: (x) => x.ip },
      { t: 'Detalhe', f: (x) => h('details', null, h('summary', { class: 'small' }, 'ver'), h('pre', { class: 'small' }, JSON.stringify({ antes: x.antes, depois: x.depois }, null, 1).slice(0, 2500))) }], ev)));
  };
  montar(el, h('h1', null, 'Auditoria'), h('p', { class: 'muted' }, 'Trilha imutável de alterações, aprovações e origem dos dados.'),
    h('div', { class: 'card row' }, h('div', null, h('label', null, 'Entidade'), h('input', { placeholder: 'ordem, parametro, apontamento…', onchange: (e) => { filtro.entidade = e.target.value; carregar(); } })),
      h('div', null, h('label', null, 'Ação (prefixo)'), h('input', { placeholder: 'parametro., auth., ia.', onchange: (e) => { filtro.acao = e.target.value; carregar(); } }))), area);
  await carregar();
}

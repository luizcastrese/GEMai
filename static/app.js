import { get, post, quandoExpirar, setToken, temToken } from './api.js';
import { estado, carregarBase, escolherUnidade, ehAdmin, ehGestor } from './estado.js';
import { h, montar, tentar, toast } from './ui.js';
import * as gestao from './telas_gestao.js';
import * as proc from './telas_proc.js';
import * as prod from './telas_prod.js';
import * as admin from './telas_admin.js';

const raiz = document.getElementById('app');
let limparTela = null; // permite telas encerrarem timers

const ROTAS = [
  // [padrão, função, perfis, menu]
  [/^#\/painel$/, gestao.painel, 'g', ['Gestão', 'Painel', '#/painel']],
  [/^#\/implantacao$/, gestao.implantacao, 'g', ['Gestão', 'Implantação com IA', '#/implantacao']],
  [/^#\/processos$/, proc.lista, 'g', ['Gestão', 'Processos', '#/processos']],
  [/^#\/processos\/(\d+)$/, proc.detalhe, 'g'],
  [/^#\/cadastros$/, proc.cadastros, 'g', ['Gestão', 'Recursos e cadastros', '#/cadastros']],
  [/^#\/ordens$/, prod.ordens, 'g', ['Produção', 'Ordens', '#/ordens']],
  [/^#\/ordens\/(\d+)$/, prod.ordemDetalhe, 'a'],
  [/^#\/aprovacoes$/, prod.aprovacoes, 'g', ['Produção', 'Apontamentos a aprovar', '#/aprovacoes']],
  [/^#\/fila$/, prod.fila, 'a', ['Produção', 'Minha fila (chão de fábrica)', '#/fila']],
  [/^#\/ia$/, admin.recomendacoes, 'g', ['Inteligência', 'Sugestões da IA', '#/ia']],
  [/^#\/usuarios$/, admin.usuarios, 'admin', ['Administração', 'Usuários', '#/usuarios']],
  [/^#\/empresa$/, admin.empresa, 'admin', ['Administração', 'Empresa e unidades', '#/empresa']],
  [/^#\/auditoria$/, admin.auditoria, 'admin', ['Administração', 'Auditoria', '#/auditoria']],
];
const permitido = (p) => p === 'a' || (p === 'g' && ehGestor()) || (p === 'admin' && ehAdmin());

function inicial() { return ehGestor() ? '#/painel' : '#/fila'; }

async function rotear() {
  if (!temToken()) return telaAuth();
  if (!estado.usuario) { const ok = await tentar(carregarBase); if (!ok && !estado.usuario) return telaAuth(); }
  if (limparTela) { limparTela(); limparTela = null; }
  const hash = location.hash || inicial();
  for (const [re, fn, perfil] of ROTAS) {
    const m = hash.match(re);
    if (!m) continue;
    if (!permitido(perfil)) { location.hash = inicial(); return; }
    const conteudo = h('div', null, h('p', { class: 'muted' }, 'Carregando…'));
    montar(raiz, casca(conteudo, hash));
    try { limparTela = (await fn(conteudo, ...m.slice(1))) || null; } catch (e) { montar(conteudo, h('div', { class: 'aviso' }, e.message)); }
    return;
  }
  location.hash = inicial();
}

function casca(conteudo, hash) {
  const grupos = {};
  ROTAS.filter((r) => r[3] && permitido(r[2])).forEach((r) => {
    const [grupo, rotulo, href] = r[3];
    const ativo = hash === href || (hash.startsWith(`${href}/`));
    (grupos[grupo] ||= []).push(h('a', { href, class: ativo ? 'on' : '' }, rotulo));
  });
  const nav = h('nav', { class: 'side' }, h('div', { class: 'brand' }, 'ERP de Produção'),
    Object.entries(grupos).map(([g, links]) => [h('div', { class: 'grp' }, g), ...links]));
  const sel = h('select', { 'aria-label': 'Unidade', onchange: (e) => { escolherUnidade(e.target.value); rotear(); } },
    estado.unidades.map((u) => h('option', { value: u.id, selected: u.id === estado.unidadeId }, u.nome)));
  const topo = h('div', { class: 'top' }, h('div', { class: 'who' }, 'Unidade:', sel),
    h('div', { class: 'who' }, `${estado.usuario.nome} · ${estado.usuario.perfil}`,
      h('button', { class: 'sm', onclick: sair }, 'Sair')));
  return h('div', { class: 'shell' }, nav, h('main', null, topo, conteudo));
}

function sair() { setToken(null); estado.usuario = null; location.hash = ''; rotear(); }
quandoExpirar(() => { estado.usuario = null; toast('Sessão expirada. Entre novamente.', true); rotear(); });

function telaAuth() {
  let modo = 'login';
  const desenhar = () => {
    const f = {};
    const campo = (k, rot, tipo = 'text', ac) => { f[k] = h('input', { type: tipo, autocomplete: ac, required: true }); return [h('label', null, rot), f[k]]; };
    const form = h('form', { onsubmit: async (e) => {
      e.preventDefault();
      const v = Object.fromEntries(Object.entries(f).map(([k, i]) => [k, i.value.trim()]));
      const corpo = modo === 'login' ? { email: v.email, senha: f.senha.value }
        : { empresa_nome: v.empresa_nome, segmento: v.segmento || '', unidade_nome: v.unidade_nome, nome: v.nome, email: v.email, senha: f.senha.value };
      const r = await tentar(() => post(modo === 'login' ? '/auth/login' : '/auth/registrar', corpo));
      if (r) { setToken(r.access_token); estado.usuario = null; location.hash = ''; rotear(); }
    } },
    modo === 'cadastro' ? [campo('empresa_nome', 'Nome da empresa', 'text', 'organization'), campo('segmento', 'Segmento (ex.: marcenaria, alimentação)'), campo('unidade_nome', 'Primeira unidade/operação'), campo('nome', 'Seu nome', 'text', 'name')] : null,
    campo('email', 'E-mail', 'email', 'username'),
    campo('senha', modo === 'login' ? 'Senha' : 'Senha (mín. 10 caracteres, com maiúsculas, minúsculas e número)', 'password', modo === 'login' ? 'current-password' : 'new-password'),
    h('p', null, h('button', { class: 'pri', type: 'submit' }, modo === 'login' ? 'Entrar' : 'Criar empresa e entrar')));
    f.segmento && (f.segmento.required = false);
    montar(raiz, h('div', { class: 'auth' }, h('h1', null, 'ERP de Produção com IA'),
      h('p', { class: 'muted' }, 'A IA sugere; o sistema valida.'),
      h('div', { class: 'card' }, form,
        h('p', { class: 'small' }, modo === 'login' ? 'Primeiro acesso? ' : 'Já tem conta? ',
          h('a', { href: '#', onclick: (e) => { e.preventDefault(); modo = modo === 'login' ? 'cadastro' : 'login'; desenhar(); } },
            modo === 'login' ? 'Cadastre sua empresa' : 'Entrar')))));
  };
  desenhar();
}

window.addEventListener('hashchange', rotear);
rotear();

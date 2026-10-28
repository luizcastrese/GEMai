// Meios (máquinas, ferramentas, meios de movimentação): identificação assistida e ficha técnica.
// A IA identifica e busca; a PESSOA confirma o modelo e valida cada parâmetro. Nada vira tempo digitado.
import { api, get, patch, post, qs } from './api.js';
import { badge, detalhes, fmtNum, h, modal, montar, tabela, tentar, toast } from './ui.js';

const FUNCOES = { corte: 'Corte', bordo: 'Colagem de borda', furacao: 'Furação', movimentacao: 'Movimentação', acabamento: 'Acabamento', montagem: 'Montagem', outro: 'Outro', '': 'Não informado' };
const num = (v) => (v === '' || v === null || v === undefined ? null : Number(v));
const urlSegura = (u) => (typeof u === 'string' && /^https?:\/\/[^\s]+$/.test(u) ? u : null);
const CONF = { baixa: ['b-warn', 'confiança baixa'], media: ['', 'confiança média'], alta: ['b-ok', 'confiança alta'] };

function origemTxt(p) {
  return { informado: 'informado por você', medido: 'medido', ia_web: 'achado na web' }[p.origem] || p.origem;
}

function fonteLink(p) {
  const u = urlSegura(p.fonte_url);
  return u ? h('a', { href: u, target: '_blank', rel: 'noopener noreferrer' }, 'fonte') : null;
}

// ---------------------------------------------------------------- ficha técnica de um meio
async function abrirFicha(r, depois) {
  const area = h('div');
  const desenhar = async () => {
    const f = await get(`/recursos/${r.id}/ficha-tecnica`);
    const campos = f.parametros.map((p) => {
      const entrada = h('input', { type: 'number', step: 'any', min: String(p.minimo), 'aria-label': `${p.descricao} (${p.unidade})`, placeholder: `${p.unidade}` });
      const sug = p.sugestao_pendente;
      return { p, entrada, sug };
    });
    montar(area,
      h('p', { class: 'muted small' }, 'A ficha técnica traz as características do equipamento (avanço, velocidade, capacidade…). Elas entram no cálculo do tempo só depois de validadas por você. O tempo nunca é digitado.'),
      f.pendencias.length ? h('div', { class: 'aviso' }, h('ul', null, f.pendencias.map((x) => h('li', null, x)))) : h('div', { class: 'ok-box card' }, '✓ Ficha técnica completa e validada.'),
      tabela([
        { t: 'Parâmetro', f: ({ p }) => h('span', null, p.descricao, h('div', { class: 'muted small' }, `${p.nome} · faixa plausível ${fmtNum(p.minimo, 2)}–${fmtNum(p.maximo, 2)} ${p.unidade}`)) },
        { t: 'Valor validado', f: ({ p }) => (p.vigente ? h('span', null, `${fmtNum(p.vigente.valor_num, 3)} ${p.unidade}`, h('div', { class: 'muted small' }, origemTxt(p.vigente), ' ', fonteLink(p.vigente))) : h('span', { class: 'muted' }, '— pendente')) },
        { t: 'Sugestão a validar', f: ({ sug }) => (sug ? h('div', null, `${fmtNum(sug.valor_num, 3)} ${sug.unidade} `, badge((CONF[sug.confianca] || CONF.baixa)[1], (CONF[sug.confianca] || CONF.baixa)[0]),
          h('div', { class: 'muted small' }, `${origemTxt(sug)} em ${sug.fonte_data || '—'} `, fonteLink(sug)),
          h('div', { class: 'inline' }, h('button', { class: 'sm pri', onclick: async () => { if (await tentar(() => post(`/parametros/${sug.id}/validar`, {}), 'Parâmetro validado.')) desenhar(); } }, 'Conferi: validar'),
            h('button', { class: 'sm', onclick: async () => { if (await tentar(() => post(`/parametros/${sug.id}/rejeitar`, {}), 'Sugestão rejeitada.')) desenhar(); } }, 'Rejeitar'))) : '—') },
        { t: 'Informar manualmente', f: ({ p, entrada }) => h('div', { class: 'inline' }, entrada,
          h('button', { class: 'sm', onclick: async () => {
            if (entrada.value === '') return toast('Digite o valor da ficha técnica.', true);
            if (await tentar(() => post('/parametros', { escopo_tipo: 'recurso', escopo_id: r.id, nome: p.nome, valor_num: num(entrada.value), unidade: p.unidade, origem: 'informado' }), 'Salvo (informado por você).')) desenhar();
          } }, 'Salvar')) }], campos, 'Escolha a função do meio para ver os parâmetros.'),
      h('div', { class: 'inline' },
        f.modelo_confirmado && f.busca_disponivel ? h('button', { class: 'ia', onclick: async () => {
          const b = await tentar(() => post(`/recursos/${r.id}/ficha-tecnica/buscar`, {}));
          if (!b) return;
          toast(b.encontrada ? `${b.sugeridos.length} sugestão(ões) da ficha técnica para você validar.` : 'A busca não trouxe parâmetros utilizáveis.', !b.encontrada);
          desenhar();
        } }, 'Buscar ficha técnica na web') : null,
        !f.modelo_confirmado ? h('span', { class: 'muted small' }, 'Confirme marca e modelo para buscar a ficha na web.') : null,
        f.modelo_confirmado && !f.busca_disponivel ? h('span', { class: 'muted small' }, 'Busca na web indisponível (exige IA externa habilitada na empresa): preencha manualmente.') : null));
  };
  modal(`Ficha técnica — ${r.nome}${r.marca || r.modelo ? ` (${[r.marca, r.modelo].filter(Boolean).join(' ')})` : ''}`, area, { larga: true, acoes: (fechar) => [h('button', { onclick: () => { fechar(); depois(); } }, 'Fechar')] });
  await desenhar();
}

// ---------------------------------------------------------------- identificar e cadastrar um meio
function lerFoto(arquivo) {
  return new Promise((ok, erro) => {
    if (!arquivo) return ok(null);
    if (!/^image\/(jpeg|png)$/.test(arquivo.type)) return erro(new Error('A foto deve ser JPEG ou PNG.'));
    if (arquivo.size > 4_000_000) return erro(new Error('A foto passa de 4 MB.'));
    const leitor = new FileReader();
    leitor.onload = () => ok(String(leitor.result).split(',')[1] || null);
    leitor.onerror = () => erro(new Error('Não foi possível ler a foto.'));
    leitor.readAsDataURL(arquivo);
  });
}

function cadastrarMeio(uid, depois) {
  const texto = h('input', { placeholder: 'ex.: Seccionadora Giben Optima ou "carrinho de plataforma"', maxlength: '500' });
  const foto = h('input', { type: 'file', accept: 'image/jpeg,image/png' });
  const resultado = h('div');
  const criar = async (c) => {
    const corpo = { unidade_id: uid, nome: [c.marca, c.modelo].filter(Boolean).join(' ') || texto.value.trim(), tipo: c.tipo, funcao: c.funcao, marca: c.marca, modelo: c.modelo, modelo_confirmado: true };
    const novo = await tentar(() => post('/recursos', corpo), 'Meio cadastrado. Agora complete a ficha técnica.');
    if (novo) { document.querySelector('.modal-bg')?.remove(); depois(); abrirFicha(novo, depois); }
  };
  const identificar = async () => {
    if (texto.value.trim().length < 2) return toast('Descreva o meio (nome, modelo ou uma frase).', true);
    let b64 = null;
    try { b64 = await lerFoto(foto.files[0]); } catch (e) { return toast(e.message, true); }
    const r = await tentar(() => post('/meios/identificar', { unidade_id: uid, texto: texto.value.trim(), foto_base64: b64 }));
    if (!r) return;
    montar(resultado,
      r.aviso ? h('p', { class: 'muted small' }, r.aviso) : null,
      r.pergunta ? h('div', { class: 'aviso' }, h('strong', null, 'Para ter certeza: '), r.pergunta, h('div', { class: 'muted small' }, 'Complemente a descrição acima e identifique de novo.')) : null,
      r.candidatos.length ? h('div', null, h('h3', null, 'É este? Confirme o modelo'), r.candidatos.map((c) => h('div', { class: 'card fila-card' },
        h('div', null, h('strong', null, [c.marca, c.modelo].filter(Boolean).join(' ') || '(sem nome)'), ' ', badge((CONF[c.confianca] || CONF.baixa)[1], (CONF[c.confianca] || CONF.baixa)[0]),
          h('div', { class: 'muted small' }, `${FUNCOES[c.funcao] || c.funcao} · ${c.tipo}${c.observacao ? ` · ${c.observacao}` : ''}`)),
        h('button', { class: 'pri', onclick: () => criar(c) }, 'Confirmar este modelo'))))
        : h('p', { class: 'muted' }, 'Não consegui identificar com segurança. Cadastre manualmente abaixo e preencha a ficha técnica.'),
      h('button', { onclick: () => criar({ marca: '', modelo: texto.value.trim(), tipo: 'maquina', funcao: '' }) }, 'Nenhum destes: cadastrar com o que digitei'));
  };
  modal('Cadastrar meio (identificação assistida)', h('div', null,
    h('p', { class: 'muted small' }, 'Descreva o equipamento, ferramenta ou meio de movimentação. A IA sugere marca e modelo; você confirma. A foto é opcional, só é analisada com IA externa habilitada, tem os metadados (EXIF/GPS) removidos e não é guardada.'),
    h('label', null, 'Nome, modelo ou descrição'), texto, h('label', null, 'Foto (opcional, JPEG ou PNG até 4 MB)'), foto, resultado),
  { larga: true, acoes: (fechar) => [h('button', { onclick: fechar }, 'Cancelar'), h('button', { class: 'pri', onclick: identificar }, 'Identificar')] });
}

// ---------------------------------------------------------------- seção da tela de Contorno físico
export async function secaoMeios(uid, recarregar) {
  const meios = await get(`/recursos${qs({ unidade_id: uid, ativo: true })}`);
  const fichas = await Promise.all(meios.map((r) => get(`/recursos/${r.id}/ficha-tecnica`)));
  const linhas = meios.map((r, i) => ({ r, f: fichas[i] }));
  return h('div', { class: 'card' }, h('h2', null, '3b. Meios e ficha técnica'),
    h('p', { class: 'muted small' }, 'O tempo de máquina é calculado pela ficha técnica (avanço, velocidade, capacidade…), nunca digitado. Identifique o meio, confirme o modelo e valide os parâmetros.'),
    tabela([
      { t: 'Meio', f: ({ r }) => h('span', null, h('strong', null, r.nome), h('div', { class: 'muted small' }, [r.marca, r.modelo].filter(Boolean).join(' ') || 'sem marca/modelo', r.modelo_confirmado ? ' ✓ confirmado' : '')) },
      { t: 'Para que serve', f: ({ r }) => FUNCOES[r.funcao] ?? r.funcao },
      { t: 'Ficha técnica', f: ({ f }) => { const ok = f.parametros.filter((p) => p.vigente).length; return f.parametros.length ? (ok === f.parametros.length ? badge('Completa', 'b-ok') : badge(`${ok}/${f.parametros.length} validados`, 'b-warn')) : badge('Defina a função', 'b-warn'); } },
      { t: '', f: ({ r }) => h('button', { class: 'sm', onclick: () => abrirFicha(r, recarregar) }, 'Ficha técnica') }], linhas, 'Nenhum meio cadastrado.'),
    h('p', null, h('button', { class: 'pri', onclick: () => cadastrarMeio(uid, recarregar) }, '+ Cadastrar meio (identificação assistida)')));
}

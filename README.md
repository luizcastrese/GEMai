# ERP de Produção com IA

ERP genérico orientado à produção, multiempresa, baseado no *Script Conceitual do Sistema ERP de Produção*
(PUC-Campinas – Engenharia de Produção), construído como um **gêmeo digital da operação**.

- A empresa descreve a operação com as próprias palavras; a IA sugere perguntas e uma estrutura de processo.
- O processo é uma **reunião de blocos** (mão de obra + atividade + equipamento + espaço físico + item).
- A IA **estima o tempo planejado** a partir desses blocos e do contorno físico; o sistema faz a conta.
- Quando a ordem termina, o tempo **real é contrastado com o planejado**, e o histórico aprovado passa a substituir a estimativa.
- **A IA sugere, o sistema valida** — o dado medido ou validado por pessoa sempre prevalece, e tudo fica na trilha de auditoria.

## Fluxo principal (foco do TCC): do produto ao tempo padrão

O problema atacado: o profissional faz o produto de forma heurística, não tem **tempo padrão** e acaba aceitando prazos sem saber quanto o trabalho leva.
O caminho principal da interface tem só três passos (menu: *Início · 1. Produtos · 2. Oficina · 3. Planos de trabalho · Configurações*):

1. **Produto:** o que será feito (texto livre interpretado pela IA, ou lista de peças e ligações).
2. **Oficina:** locais, distância entre eles e máquinas. **Quem não sabe quantas peças a máquina faz por hora** clica em *"Não sei: a IA estima"*,
   descreve o equipamento (marca, modelo, potência) e/ou envia uma **foto**; a IA **propõe** um valor com faixa, premissas e confiança (nunca "alta"),
   e o usuário confere antes de gravar. Quem consegue **cronometrar** digita o valor, que fica rotulado como *medido*. Valor da IA fica rotulado
   *estimado pela IA* e entra nas premissas do plano. Sem IA externa habilitada, o sistema só aproveita um número escrito pelo usuário (não inventa).
3. **Plano de trabalho:** a IA monta o roteiro a partir do produto, da oficina e de quem vai fazer (nº de pessoas e perfil); o sistema calcula e mostra,
   em destaque, o **tempo padrão por unidade** e o prazo realista. Passos sem dado aparecem como pendência, nunca como zero.

Ordens, fila, conferência de registros, processos e análises continuam no sistema, mas só aparecem no menu com **"Mostrar detalhes técnicos"** ligado (fase 2: medir o real para melhorar o padrão).

## Experiência do usuário: um só tipo de usuário, simples por padrão

Não há papéis (admin/gestor/operador): **todos da empresa veem as mesmas telas e podem fazer tudo**. A interface fala a língua da operação e esconde a engenharia.

- **Início:** "o que precisa da sua atenção" (ordens atrasadas, paradas, registros e previsões para confirmar, contorno físico incompleto), atalhos e poucos números.
- **Configurar com a IA:** a pessoa descreve a operação, responde às perguntas e a IA monta o processo.
- **Contorno físico:** uma única tela com o **mínimo** que a IA precisa para prever o tempo, salva ao preencher e com barra de progresso:
  1. **locais** por onde a peça passa; 2. **distância** entre eles; 3. **peças por hora** de cada equipamento; 4. por tarefa: equipamento, de onde sai, para onde vai e **peso da peça**.
  A IA já pergunta isso no diagnóstico e cria os locais citados. Dados opcionais (dimensões, ruído, temperatura…) ficam fora do mínimo. O contorno pode ser corrigido a qualquer momento, inclusive em processo publicado.
- **Processo:** checklist "Está tudo pronto?" em português comum e um **único Publicar** (a IA prevê o tempo das tarefas na publicação). **A confirmação das previsões é manual**: botão "Confirmar previsões". "Já sei o tempo" substitui a estimativa da IA por um tempo informado.
- **Minha fila:** ▶ Iniciar → ■ Concluir (quantas peças ficaram boas) e "Algo deu errado? Avisar".
- **Configurações:** empresa, equipe, histórico de alterações e a preferência **"Mostrar detalhes técnicos"** (tolerâncias, composição do tempo, normas, análises completas). Desligada por padrão.

Regras que substituem os papéis:
- **Dois olhos nos registros de produção:** quem registrou um apontamento não o aprova sozinho, a menos que a equipe tenha uma só pessoa. Só histórico conferido por outra pessoa melhora as estimativas.
- **A equipe precisa de ao menos uma pessoa ativa;** ninguém desativa a si mesmo.
- **Unidades:** por padrão todos acessam todas as unidades; opcionalmente uma pessoa pode ser restrita a algumas (redes com várias unidades).
- Alertas de segurança (carga, ruído, esforço) aparecem para todos, em linguagem simples; a referência normativa fica nos detalhes técnicos.

## Gêmeo digital: como o tempo planejado nasce

```
blocos (lego)                         IA propõe                    sistema calcula             contraste
mão de obra (função, nº pessoas) ┐
equipamento (capacidade un/h)    ├─►  modelo de tempo      ─►    minutos por elemento   ─►   planejado × real
espaços + distâncias (m)         │    (elementos + premissas      (fórmulas de vocabulário    por fonte de estimativa
item físico (peso, dimensões)    ┘     + dados faltantes)          FECHADO, sem eval)         (painel de acurácia)
```

1. **Contorno físico estruturado:** *Espaços* (dimensões, piso, temperatura), *distâncias* entre espaços, *equipamentos* com capacidade, *item típico* da operação (peso/dimensões) que o *produto* da ordem sobrepõe.
2. **Operação = composição de blocos:** função e nº de pessoas, equipamento, espaço de origem e destino, item e **marcos de início/fim do apontamento** (para o tempo medido ser comparável ao planejado).
3. **Modelo de tempo (IA propõe):** decompõe a operação em elementos (`preparacao`, `deslocamento`, `manuseio`, `processamento`…) usando 4 métodos fechados — `fixo`, `linear_driver` (peso, área, comprimento, volume, distância), `deslocamento` e `capacidade_recurso`. Traz **premissas**, **confiança** e **dados faltantes**. Nada que a IA escreva é executado: o sistema calcula.
4. **Sem dado, sem chute:** se falta distância, peso ou capacidade, o elemento **não vira zero**; o modelo fica incompleto e o sistema lista o que falta.
5. **Prioridade do tempo planejado:** `histórico aprovado` > `parâmetro validado por pessoa` > `modelo da IA` (rotulado *validado* ou *não validado*) > `sem base`.
6. **Prontidão do processo:** checagem determinística (e revisão narrativa por IA) apontando como o processo deve ser descrito e medido para os parâmetros ficarem consistentes.
7. **Contraste e acurácia:** o painel mostra, por fonte (modelo IA, parâmetro, histórico), o desvio médio e o erro médio do planejado contra o real.

### Fatores humanos e normas (engenharia de métodos e ergonomia)

O tempo planejado segue a estrutura clássica do estudo de tempos: **tempo normal → ritmo → tolerâncias → tempo padrão**.

| Fator | Como entra | Base |
|---|---|---|
| **Tipo de movimento** | Elemento `indices_most`: Σ índices × 10 TMU (1 TMU = 0,036 s), sequência *General Move* (A B G A B P A). Tipos pré-definidos usam índices **ilustrativos** | Inspirado no BasicMOST (Maynard). Conferir com o cartão certificado |
| **Peso / tamanho do item** | Peso e dimensões do item típico (o do produto da ordem prevalece); alimentam manuseio, deslocamento (itens por viagem) e NIOSH | — |
| **Carga manual** | Triagem **NIOSH** (RWL, índice de levantamento) com os multiplicadores HM/VM/DM/AM/FM/CM; LI > 1 gera alerta e uma tolerância de fadiga | NIOSH Pub. 94-110; tabelas FM/CM conferidas em fontes secundárias |
| **Limites legais de carga** | Alertas: > 60 kg individual (CLT art. 198); referência de 20/25 kg para perfil feminino ou menor de 18 (CLT arts. 390/405 §5º) | **Verificar vigência/interpretação com SESMT/jurídico**; NR-17 exige peso compatível com saúde e segurança |
| **Ritmo** | `ritmo_pct` do perfil (100 = normal) multiplica só o que depende do operador; máquina não muda | Avaliação de ritmo (OIT/Barnes). **Calibre por medição** |
| **Tolerâncias** | FT = 1/(1 − Σp), p ≤ 50 %. Padrão: necessidades pessoais 5 % + fadiga básica 4 % + em pé 2 % | OIT (*Introduction to Work Study*): valores únicos, sem distinção por sexo |
| **Gasto energético** | Descanso de Murrell R = T·(W − S)/(W − 1,5), com S = limite **informado no perfil** | Murrell. Limites por sexo/jornada divergem entre fontes: **não há valor embutido** |
| **Ambiente** | Temperatura, umidade, ruído, iluminância por espaço; ruído > 85 dB(A) gera alerta; temperatura extrema pede avaliação específica | NR-15 (ruído, 8 h). Sem percentual inventado para calor/iluminação |
| **Postura / altura de trabalho** | Postura entra nas tolerâncias; altura de trabalho é comparada à altura do cotovelo do perfil, **sem julgar** (as faixas recomendadas divergem entre fontes) | — |

**Sexo, estatura e peso corporal:** ficam no **perfil de mão de obra** (referência, não é uma pessoa) e são usados **apenas** para limites de carga e conferências ergonômicas.
Eles **não alteram o tempo nem medem produtividade** (há teste automatizado garantindo isso). O ritmo é calibrado por medição. Não use esses dados
para decisões de contratação ou alocação de pessoas; se vincular perfis a pessoas reais, trate como dado pessoal (LGPD: finalidade, minimização e consentimento).

**Ainda não coberto** (próximos passos): curva de aprendizagem/experiência como multiplicador, tabelas MTM-1 completas, RULA/REBA/OWAS, Snook & Ciriello
(empurrar/puxar), exposição a calor (IBUTG), iluminação por tarefa, fadiga cumulativa por turno e calibração automática dos coeficientes por bloco.
O sistema é uma **triagem de apoio à decisão**; não substitui a Análise Ergonômica do Trabalho (NR-17) nem um estudo de tempos feito por profissional.

`ERP_USAR_MODELO_IA_NAO_VALIDADO=false` exige que um gestor valide o modelo antes de ele valer como tempo planejado.
O provedor local usa referências genéricas (caminhada 75 m/min, carga manual 20 kg/pessoa, manuseio 0,15 min + 0,012 min/kg,
preparação 5/2 min) **sempre declaradas nas premissas e com confiança baixa**; com a chave do Claude, o modelo é derivado do contexto da empresa.

## Do produto ao plano de trabalho

Fluxo pensado para o dia a dia: **Produtos → (Contorno físico) → Planos de trabalho → Ordem de produção**.

1. **Produto:** o usuário informa os **componentes** (nome, quantidade, material, medidas, peso, furos, borda) e **como se ligam** (método e nº de fixadores:
   parafuso, cavilha, minifix, dobradiça, corrediça, cola, prego, encaixe, puxador). Também pode **descrever em texto livre** ("armário de MDF com 2 portas,
   3 prateleiras…"): a IA **propõe** a lista, o usuário confere e só então ela é gravada (`POST /produtos/{id}/interpretar` não grava nada).
2. **Contorno físico:** locais (com tipo: estoque, montagem…), distâncias, equipamentos (*para que serve* + peças/h) e, se quiser, tempos de montagem da própria
   oficina e condições do ambiente. O que não for informado vira **pendência**, nunca um valor inventado.
3. **Plano de trabalho** (`POST /planos`): a IA (ou o provedor local, por regras) **propõe os passos** — transporte do estoque, usinagem (corte, borda, furação),
   montagem por subconjunto, montagem final e conferência — com elementos de tempo do **vocabulário fechado**. O **sistema calcula** cada tempo e considera:
   movimentação (distância e carga por viagem; mais pessoas quando a peça passa de 20 kg/pessoa), capacidade dos equipamentos, ligações/fixadores,
   tolerâncias (pessoal 5 % + fadiga 4 %, OIT, + a folga do ambiente **se o usuário informar**), ritmo do perfil (só no que depende do operador),
   alertas de carga (CLT), ruído (NR-15) e temperatura extrema, e **agenda os passos na jornada** (blocos de horário, intervalos, só dias úteis), com avisos
   de jornada/intervalo (CLT arts. 58/59/71 — conferir com jurídico/SESMT). Fadiga acumulada por hora trabalhada só entra se o usuário informar o percentual.
4. **Saída:** passos com início/fim previstos, tempo de trabalho, pessoas-hora, término e dias; **imprimir** e **planilha CSV** (protegida contra injeção de fórmulas).
   O plano nasce como **rascunho**; a **confirmação é manual**. Plano confirmado → **ordem de produção** (`POST /planos/{id}/gerar-ordem`), cujos passos
   ficam com fonte `plano`; passos sem tempo entram como "sem base". Depois os apontamentos reais permitem o planejado × realizado.

Limites assumidos (declarados na tela e nas premissas do plano): sequência única de passos (sem trabalho em paralelo entre passos); tempos de montagem e
conferência partem de **referências genéricas** até serem substituídos pelos da empresa; a confiança do plano **nunca passa de "média"** (a de "alta" que a IA
declare é descartada) porque ainda não há histórico medido de passos de plano — o aprendizado por histórico continua ligado às operações de processo.
Peso sem informação é **estimado** por densidade de referência × medidas e aparece rotulado como estimado.

## Rodando

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload          # http://localhost:8000  (API em /docs, só fora de produção)
python -m pytest -q                    # suíte de testes
```

Em desenvolvimento as tabelas são criadas automaticamente (SQLite). Em produção use migrações:
`alembic upgrade head`. Configuração por variáveis `ERP_*` (veja `.env.example`).

Produção com Docker: `cp .env.example .env`, preencha `ERP_SECRET_KEY` e `POSTGRES_PASSWORD`, `docker compose up -d`
e ponha um proxy reverso com HTTPS na frente.

## O que cada seção do documento virou

| Documento | Implementação |
|---|---|
| Tela 1 – Cadastro e descrição | Unidade com descrição, objetivo, problemas, fontes (`/unidades`) |
| Tela 2 – Diagnóstico inteligente | Perguntas adaptativas por grupo (11 grupos), respostas gravadas (`/unidades/{id}/diagnostico`) |
| Tela 3 – Estrutura automática | Proposta da IA (processo › etapas › operações, recursos, materiais, indicadores, etapas possivelmente omitidas), **editável** antes de aprovar; cria **rascunho** |
| Tela 4 – Recursos | Ficha do recurso (capacidade, espaço onde está); tempo médio e de preparação **calculados do histórico aprovado** |
| (novo) Produto → plano | Componentes, ligações, plano de trabalho com horários, ordem a partir do plano — ver seção acima |
| (novo) Gêmeo digital | Espaços, distâncias, modelo de tempo por operação, simulação (what-if), prontidão e acurácia — ver seção acima |
| Tela 5 – Ordem | Roteiro copiado do processo ativo, estimativa por operação, status planejada → liberada → em produção ⇄ parada → concluída/cancelada |
| §10 Tempo e cálculo | `app/services/timecalc.py` — fórmulas configuráveis por operação (`linear`, `lote`, `fixo`) |
| §11 IA em uso | Perguntas, estrutura, indicadores, operações semelhantes, explicação de desvios, gargalos, relatório (sempre como sugestão com evidências) |
| §12 Ergonomia | Fatores por operação + **sinalização** (não é avaliação ergonômica formal) |
| §13 Dashboard | Ordens abertas/atrasadas, planejado × realizado, gargalos, paradas, retrabalho, produtividade, utilização, qualidade, tendência semanal |
| §14 Entidades | `app/models.py` |
| §17 IA sugere, sistema valida | Ver abaixo |
| §18 Segurança e permissões | Ver abaixo |

### Regras de negócio que merecem atenção

- **Origem do dado.** Todo parâmetro tem origem (`informado`, `medido`, `calculado`, `ia_sugerido`), status de validação e versão. Só parâmetro **vigente e validado** entra nas estimativas; sugestão da IA nunca entra sozinha.
- **Tempo da IA é rotulado, nunca disfarçado.** A estimativa da IA vem do modelo de tempo, com fonte `modelo_ia`, flag de validação e composição por elemento. Sem modelo, parâmetro nem histórico (ou com dado físico faltando), a operação fica `sem_base`.
- **Estimativa.** Histórico (mediana de apontamentos **aprovados**, mín. `ERP_MIN_AMOSTRAS_HISTORICO`) > parâmetro validado > modelo da IA > sem base. A fonte é exibida em cada operação. "Atualizar pelo histórico" grava nova versão do parâmetro, rastreável.
- **Referências genéricas do provedor local** (velocidade de caminhada, carga manual, manuseio) são aproximações e não substituem estudo de tempos; valide ou substitua por medições. Para um modelo calibrado à sua empresa, use o provedor Claude e/ou um modelo manual.
- **Convenções de tempo.** Realizado = preparação + execução + retrabalho (soma dos apontamentos, ou seja, tempo de trabalho). Total = realizado + espera. Desvio = realizado − estimado. Eficiência = estimado ÷ realizado. Fila entre operações é calculada (fim da anterior → início da próxima). Se a sua empresa usa outra convenção, ajuste `timecalc.py`/`metricas.py`.
- **Versionamento de processo.** Cada versão é uma linha; só rascunho edita estrutura; ordens ficam presas à versão em que nasceram.
- **Apontamentos nunca são apagados**, só anulados com motivo; operador só vê os próprios.

## Segurança (uso por terceiros)

- **Isolamento multiempresa:** toda tabela de negócio tem `empresa_id`; todo acesso passa por `Ctx` (`app/deps.py`) que filtra por empresa e, para gestor/operador, pelas **unidades atribuídas**. Recurso de outro tenant responde 404. Há testes dedicados (`tests/test_tenancy.py`).
- **Um único tipo de usuário** por empresa (sem papéis). O isolamento entre empresas continua rígido; veja a regra dos "dois olhos" e a restrição opcional por unidade acima. Qualquer pessoa da equipe gerencia usuários e vê o histórico — trate o acesso como de confiança dentro da empresa.
- Senhas com Argon2id; política mínima; bloqueio temporário após falhas; mensagens/tempos iguais para usuário inexistente; JWT curto com `token_versao` (trocar senha, desativar ou mudar perfil derruba sessões).
- Entradas validadas (`extra="forbid"` impede injetar `empresa_id`), limite de corpo de 1 MB, CSP estrita, `X-Frame-Options`, HSTS em produção, `/docs` desligado em produção, e a UI nunca usa `innerHTML`.
- Em produção a aplicação **não inicia** sem `ERP_SECRET_KEY` forte.
- **IA externa só com consentimento:** a empresa precisa habilitar "IA externa" na empresa **e** o servidor precisa ter `ERP_ANTHROPIC_API_KEY`. Textos da empresa vão ao modelo como *dados* (não instruções), a saída é validada por schema e saneada, e falha do provedor cai para o provedor local.
- Auditoria append-only (`/auditoria`, visível a toda a equipe) com antes/depois, usuário e IP.

### Limitações conhecidas / antes de abrir a terceiros em produção

- O limitador de tentativas é **em memória** (por processo). Com várias instâncias, use também o limitador do proxy/WAF ou troque por Redis.
- Token JWT fica em `sessionStorage` (mitigado pela CSP estrita). Não há 2FA, recuperação de senha por e-mail nem convite por e-mail: qualquer pessoa da equipe define/redefine senhas. Se for relevante, são os próximos passos naturais.
- Sem papéis, **qualquer usuário pode redefinir a senha de outro e alterar o consentimento de IA externa** (tudo auditado). Se isso não servir ao seu cenário, reintroduza um nível de permissão antes de abrir a terceiros.
- Defina `ERP_PERMITIR_CADASTRO_PUBLICO=false` em implantações fechadas.
- Backups e retenção de dados (LGPD) são responsabilidade de quem opera a implantação.
- **Validação feita:** 107 testes automatizados (SQLite) + percursos completos no navegador (implantação, gêmeo digital, fatores humanos e produto → plano → ordem). Tabelas FM/CM do NIOSH, fórmula de Murrell, estrutura do MOST, limites da CLT e tolerâncias da OIT foram conferidas em fontes públicas (não nas publicações originais). **Não validado aqui:** execução contra PostgreSQL real e chamadas reais à API da Anthropic (o provedor Claude foi testado com resposta simulada; confirme com sua chave).

## Estrutura

```
app/            API (routers/), regras (services/), IA (services/ia/), modelos e esquemas
static/         interface web (JS puro, sem build)
migrations/     Alembic
tests/          pytest
```

## Fora do MVP (seção 20 do documento)

Estoque/compras, vendas/CRM, integrações, importação de listas de materiais, IoT/CNC, modelos preditivos,
app móvel, manutenção, módulo de qualidade, programação da produção e simulação de capacidade.

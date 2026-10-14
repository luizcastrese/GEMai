# ERP de Produção com IA

ERP de produção multiempresa, baseado no *Script Conceitual do Sistema ERP de Produção* (PUC-Campinas – Engenharia de Produção).
Pensado para quem fabrica **itens compostos por peças** (ex.: móveis): a pessoa informa o item, as peças, os agentes e o ambiente, e a plataforma
**monta o plano de trabalho com o tempo de cada passo**.

- A pessoa informa o **item final** e as **peças** que o compõem; as **atividades** (corte, borda, furação, montagem…) são deduzidas das peças.
- A pessoa informa os **agentes** (pessoas, com sexo e altura para a ergonomia, e máquinas) e o **ambiente** (locais, bancada, distâncias).
- A IA (ou o provedor local, por regras) **propõe os passos**; o **sistema calcula** o tempo de cada um (vocabulário fechado, sem `eval`) e agenda na jornada.
- Quando a ordem termina, o tempo **real é contrastado com o planejado**.
- **A IA sugere, o sistema valida** — o que falta vira pendência, nunca um valor inventado, e tudo fica na trilha de auditoria.

## Experiência do usuário: um só tipo de usuário, simples por padrão

Não há papéis (admin/gestor/operador): **todos da empresa veem as mesmas telas e podem fazer tudo**. A interface fala a língua da operação e esconde a engenharia.

- **Item e peças (tela única):** a pessoa informa o **item final** (ex.: armário) e as **peças** que o compõem (material, medidas, peso, furos, borda, como se ligam) —
  ou descreve em texto e a IA propõe a lista. Na mesma página informa os **agentes** (quantas pessoas, horário, **sexo, altura e peso da equipe para a ergonomia**, a máquina de cada atividade e quantas peças por hora faz)
  e o **ambiente** (locais, **altura da bancada**, onde fica cada máquina, distâncias; calor e ruído são opcionais).
- **As atividades não são perguntadas:** saem das peças (furos → furação; borda → colagem de borda; várias peças → montagem…). No topo da página a plataforma mostra as
  atividades deduzidas e, em cada seção, o que falta (ex.: "Cadastre a máquina que faz furação"), cobrando só o que as atividades deduzidas exigem.
- **Plano de trabalho:** botão na própria página do item. O sistema monta os passos e **calcula o tempo de cada um** com as peças, máquinas, pessoas e distâncias; o que
  ainda não tem dado aparece como "sem tempo", nunca como valor inventado. A equipe e o horário vêm da seção Agentes. **A confirmação é manual.**
  Plano confirmado → **ordem de produção** (as ordens nascem de planos; não há criação avulsa).
- **Início:** o primeiro item é sempre o **próximo passo** (informar o item; gerar o plano; conferir o plano; gerar a ordem; liberá-la), seguido de alertas
  (ordens atrasadas, paradas, registros para aprovar) e poucos números.
- **Minha fila:** ▶ Iniciar → ■ Concluir (quantas peças ficaram boas) e "Algo deu errado? Avisar".
- **Configurações:** empresa, equipe, histórico de alterações e a preferência **"Mostrar detalhes técnicos"** (tolerâncias, composição do tempo, normas, análises completas). Desligada por padrão.

Regras que substituem os papéis:
- **Dois olhos nos registros de produção:** quem registrou um apontamento não o aprova sozinho, a menos que a equipe tenha uma só pessoa. (Hoje a aprovação só valida o registro; o histórico aprovado ainda **não** recalibra os tempos dos planos.)
- **A equipe precisa de ao menos uma pessoa ativa;** ninguém desativa a si mesmo.
- **Unidades:** por padrão todos acessam todas as unidades; opcionalmente uma pessoa pode ser restrita a algumas (redes com várias unidades).
- Alertas de segurança (carga, ruído, esforço) aparecem para todos, em linguagem simples; a referência normativa fica nos detalhes técnicos.

## Como o tempo planejado nasce

```
peças + ligações ─┐
agentes (pessoas,  ├─►  atividades deduzidas ─►  IA/regras propõem os passos ─►  sistema calcula ─►  agenda na jornada ─►  planejado × real
 máquinas)         │                              (elementos de tempo)            (vocabulário fechado)
ambiente (locais,  ┘
 distâncias)
```

1. **Elementos de tempo (vocabulário fechado):** cada passo é decomposto em `preparacao`, `deslocamento`, `manuseio`, `processamento`… com 4 métodos — `fixo`, `linear_driver` (peso, área, comprimento, volume, distância), `deslocamento` e `capacidade_recurso` — mais `indices_most` para tipos de movimento. Nada que a IA escreva é executado: o sistema calcula e sanitiza os limites.
2. **Sem dado, sem chute:** se falta distância, peso ou capacidade, o passo **não vira zero**: fica "sem tempo" e o plano lista o que falta.
3. **Tempo padrão:** tempo normal → ritmo → tolerâncias → tempo padrão (`FT = 1/(1 − Σp)`, p ≤ 50 %).
4. **Contraste e acurácia:** a ordem e o painel comparam o planejado com o real (desvio, retrabalho, esperas, gargalos).

### Fatores humanos e normas (engenharia de métodos e ergonomia)

| Fator | Como entra | Base |
|---|---|---|
| **Tipo de movimento** | Elemento `indices_most`: Σ índices × 10 TMU (1 TMU = 0,036 s), sequência *General Move* (A B G A B P A). Tipos pré-definidos usam índices **ilustrativos** | Inspirado no BasicMOST (Maynard). Conferir com o cartão certificado |
| **Peso / tamanho das peças** | Peso informado (ou estimado por material × medidas, rotulado) alimenta manuseio, deslocamento (peças por viagem) e o número de pessoas | — |
| **Limites legais de carga** | Alertas: > 60 kg individual (CLT art. 198); referência de 20/25 kg para perfil feminino ou menor de 18 (CLT arts. 390/405 §5º) | **Verificar vigência/interpretação com SESMT/jurídico**; NR-17 exige peso compatível com saúde e segurança |
| **Ritmo** | `ritmo_pct` do perfil (100 = normal) multiplica só o que depende do operador; máquina não muda | Avaliação de ritmo (OIT/Barnes). **Calibre por medição** |
| **Tolerâncias** | FT = 1/(1 − Σp), p ≤ 50 %. Padrão: necessidades pessoais 5 % + fadiga básica 4 % + em pé 2 % | OIT (*Introduction to Work Study*): valores únicos, sem distinção por sexo |
| **Gasto energético** | Descanso de Murrell R = T·(W − S)/(W − 1,5), com S = limite **informado no perfil** | Murrell. Limites por sexo/jornada divergem entre fontes: **não há valor embutido** (no plano, W é estimado por MET × peso corporal) |
| **Ambiente** | Temperatura e ruído por local; ruído > 85 dB(A) gera alerta; temperatura extrema pede avaliação específica; a folga extra (%) só entra se informada | NR-15 (ruído, 8 h). Sem percentual inventado para calor |

**Sexo, estatura e peso corporal** ficam no **perfil da equipe** (referência, não é uma pessoa; informado na seção Agentes do item) e **entram no tempo só pela ergonomia**,
nunca como multiplicador de produtividade (o ritmo continua calibrado por medição). Três mecanismos, todos declarados nas premissas de cada plano:

| Mecanismo | O que usa | Efeito no tempo | Base |
|---|---|---|---|
| **Altura da bancada × cotovelo** | estatura (cotovelo ≈ 63 % da estatura, ou informado) × altura da bancada do local de montagem | fora da faixa recomendada (montagem: de 15 cm abaixo a 0; conferência: de 5 cm abaixo a 10 cm acima), +0,4 % de fadiga por cm, até 8 % | premissa do sistema; calibrar |
| **Limite de carga por pessoa** | sexo e faixa etária | 20 kg (CLT arts. 390/405: mulher, menor, equipe mista ou não informado) ou 23 kg (NIOSH LC: adulto masculino) define quantas pessoas e peças por viagem | CLT; NIOSH Pub. 94-110 |
| **Gasto de energia** | peso corporal × MET do passo, contra o limite energético **informado** | descanso de Murrell quando o gasto passa do limite | Murrell; MET genéricos, calibrar |

Sem perfil, o plano avisa que a ergonomia **não foi considerada**; sem a altura da bancada, a altura não entra no tempo (e o plano diz isso). Equipe com pessoas diferentes:
informe a mais restritiva ou "equipe mista". **Não use esses dados para decisões de contratação ou alocação de pessoas**; se vincular perfis a pessoas reais, trate como dado pessoal
(LGPD: finalidade, minimização e consentimento).

**Ainda não coberto** (próximos passos): curva de aprendizagem/experiência como multiplicador, tabelas MTM-1 completas, RULA/REBA/OWAS, Snook & Ciriello
(empurrar/puxar), exposição a calor (IBUTG), iluminação por tarefa, fadiga cumulativa por turno e calibração automática dos coeficientes por bloco.
O sistema é uma **triagem de apoio à decisão**; não substitui a Análise Ergonômica do Trabalho (NR-17) nem um estudo de tempos feito por profissional.

O provedor local usa referências genéricas (caminhada 75 m/min, carga manual 20 kg/pessoa, manuseio 0,15 min + 0,012 min/kg,
preparação 5/2 min) **sempre declaradas nas premissas e com confiança baixa**; com a chave do Claude, a proposta de passos é derivada do contexto da empresa (e o sistema continua fazendo as contas).

## Do produto ao plano de trabalho

Fluxo único da plataforma: **Item e peças + Agentes + Ambiente → (atividades deduzidas) → Plano de trabalho com tempos → Ordem de produção**.

1. **Item e peças:** o usuário informa os **componentes** (nome, quantidade, material, medidas, peso, furos, borda) e **como se ligam** (método e nº de fixadores:
   parafuso, cavilha, minifix, dobradiça, corrediça, cola, prego, encaixe, puxador). Também pode **descrever em texto livre** ("armário de MDF com 2 portas,
   3 prateleiras…"): a IA **propõe** a lista, o usuário confere e só então ela é gravada (`POST /produtos/{id}/interpretar` não grava nada).
2. **Agentes e ambiente:** equipe e horário, equipamentos (*para que serve* + peças/h), locais (com tipo: estoque, montagem…), distâncias e, se quiser, tempos de montagem
   da própria oficina e condições do ambiente. O que não for informado vira **pendência**, nunca um valor inventado.
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
declare é descartada) porque ainda não há histórico medido de passos de plano. **Os apontamentos aprovados ainda não recalibram os tempos**: hoje servem ao planejado × realizado; usar esse histórico para ajustar os próximos planos é o passo natural seguinte.
Peso sem informação é **estimado** por densidade de referência × medidas e aparece rotulado como estimado.

`GET /produtos/{id}/preparo?unidade_id=` devolve as atividades deduzidas e o que falta em cada seção; `POST /planos` nunca bloqueia: lista as pendências no próprio plano.

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

## O que existe

| Parte | Implementação |
|---|---|
| Item, peças e ligações | `/produtos`, `/produtos/{id}/componentes`, `/ligacoes`, interpretação por IA que **propõe** e só grava após conferência |
| Agentes e ambiente | `/recursos`, `/espacos`, `/distancias`, `/perfis-mao-de-obra`, equipe e horário na unidade, `/referencias-tempo` |
| Prontidão do item | `app/services/preparo.py`: atividades deduzidas e pendências por seção |
| Plano de trabalho | `app/services/plano.py`, `/planos` (gerar, recalcular, confirmar, cancelar, CSV, gerar ordem) |
| Ordem e produção | `/ordens` (nascem de planos), `/apontamentos`, `/ocorrencias`, fila do operador |
| Cálculo de tempo e ergonomia | `app/services/modelo_tempo.py`, `ergonomia.py`, `timecalc.py` |
| IA em uso | interpretar item, propor passos, explicar desvios, gargalos e relatório (sempre como sugestão com evidências) |
| Dashboard | ordens abertas/atrasadas, planejado × realizado, gargalos, paradas, retrabalho, produtividade, utilização, qualidade, tendência semanal |

### Regras de negócio que merecem atenção

- **Tempo da IA é rotulado, nunca disfarçado.** Passos vêm de IA ou de regras locais (indicado no plano); o sistema calcula. Sem dado físico, o passo fica `sem_base`.
- **Referências genéricas do provedor local** (velocidade de caminhada, carga manual, manuseio, montagem) são aproximações e não substituem estudo de tempos; substitua por medições da sua oficina (`/referencias-tempo`).
- **Convenções de tempo.** Realizado = preparação + execução + retrabalho (soma dos apontamentos, ou seja, tempo de trabalho). Total = realizado + espera. Desvio = realizado − estimado. Eficiência = estimado ÷ realizado. Se a sua empresa usa outra convenção, ajuste `timecalc.py`/`metricas.py`.
- **Apontamentos nunca são apagados**, só anulados com motivo.

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
- **Validação feita:** 78 testes automatizados (SQLite) + percurso completo no navegador (armário → peças → agentes → ambiente → plano com tempo). Tabelas FM/CM do NIOSH, fórmula de Murrell, estrutura do MOST, limites da CLT e tolerâncias da OIT foram conferidas em fontes públicas (não nas publicações originais). **Não validado aqui:** execução contra PostgreSQL real e chamadas reais à API da Anthropic (o provedor Claude foi testado com resposta simulada; confirme com sua chave).

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

## Migração do fluxo antigo

A migração `0009` **remove** as tabelas e colunas do fluxo antigo (diagnóstico, processos, etapas, operações, parâmetros, modelo de tempo por operação, ordem a partir de
processo, descrição da unidade). Ela é **destrutiva e sem volta**: faça backup antes de `alembic upgrade head`. Ordens, apontamentos, planos, itens e cadastros são preservados.

# GEMai — ERP de Produção com IA

> **Documento-fonte do projeto e do TCC.** Descreve, com precisão, o que o sistema faz, em que literatura cada parte do
> **tempo padrão** se apoia, o que ainda **não** está embasado e como corrigir. Foi escrito para ser lido por quem
> (pessoa ou IA) vai redigir o Trabalho de Conclusão de Curso (Engenharia de Produção, PUC-Campinas).
> Estado medido em **2026-11-17** (branch `main`).

---

## 0. Como usar este documento para redigir o TCC

**Regras de redação (obrigatórias):**

1. **Não afirme além do que está aqui.** Cada capacidade do sistema vem marcada com um destes rótulos:
   `[IMPLEMENTADO]`, `[PARCIAL]`, `[NÃO IMPLEMENTADO]`, `[NÃO VALIDADO EM CAMPO]`, `[PROPOSTA]` (desenho futuro). Reproduza o rótulo na linguagem do texto
   ("o sistema implementa…", "está prevista…", "ainda não foi validado em campo…").
2. **Não invente resultados.** Não há dados de piloto neste documento. A seção 10.4 define o que medir; os resultados serão do autor.
3. **Cite apenas a literatura da seção 15.** Os dados bibliográficos foram escritos de memória por quem montou este documento e
   **precisam ser conferidos** (edição, ano, páginas) antes da entrega. Itens com `[VERIFICAR]` exigem conferência na fonte original.
4. **Separe "o método da literatura" de "a escolha do projeto".** Quando o sistema usa uma premissa própria (ex.: converter índice
   de levantamento em % de fadiga), o texto deve dizê-lo explicitamente. O código já exige isso: percentual de tolerância sem fonte não existe.
5. **O tempo padrão hoje NÃO está integralmente embasado na literatura.** A estrutura do cálculo está; vários coeficientes de base
   são referências genéricas do projeto (seção 5.9 e 11). O TCC deve apresentar isso como limitação e o roadmap (seção 12) como proposta.
6. **O sistema é genérico por desenho, validado em marcenaria.** O catálogo de módulos atual é de marcenaria (seção 6.6 e 12.2).
7. **Idioma e norma:** português, ABNT (NBR 6023 referências, NBR 10520 citações, NBR 14724 estrutura).

**Mapa sugerido: capítulo do TCC ← seção deste documento**

| Capítulo do TCC | Fonte neste documento |
|---|---|
| Resumo / Abstract | 1 |
| Introdução (contexto, problema, justificativa, objetivos) | 2, 3 |
| Metodologia | 4, 10.4 |
| Fundamentação teórica | 5 |
| Desenvolvimento: requisitos, arquitetura, modelo de dados | 6 |
| Desenvolvimento: motor de tempo padrão | 7 (núcleo do trabalho) |
| Desenvolvimento: uso de IA | 8 |
| Segurança, privacidade e LGPD | 9 |
| Verificação, validação e resultados | 10 |
| Limitações e discussão | 11 |
| Conclusão e trabalhos futuros | 12 |
| Apêndices | 14 |
| Referências | 15 |

**Perguntas que só o autor responde (não presumir):** objetivos formais aprovados pelo orientador; método de pesquisa adotado
(a seção 4 é uma proposta); empresa e período do piloto; resultados do piloto; normas e edições de livros efetivamente consultadas.

---

## 1. Resumo (rascunho)

Profissionais que fabricam sob encomenda costumam estimar prazos de forma heurística, sem **tempo padrão**, e aceitam datas sem saber
quanto o trabalho leva. Este trabalho apresenta o **GEMai**, um ERP de produção multiempresa, concebido como **gêmeo digital** da
operação, em que o **tempo padrão é uma saída calculada** das condições do trabalho (estrutura do produto, meios cadastrados com ficha
técnica, distâncias, jornada e perfil de mão de obra) e não um número digitado. O cálculo segue a estrutura clássica do estudo de
tempos (tempo normal, tolerâncias, tempo padrão), com tempos de máquina derivados de parâmetros técnicos, elementos manuais
compostos por vocabulário fechado e tolerâncias por fontes plugáveis (constantes da OIT, NIOSH, Murrell). Uma **inteligência
artificial generativa apenas sugere** (escolhe módulos de um catálogo fechado e interpreta descrições); **o sistema valida e calcula**,
e o dado medido e aprovado por pessoa sempre prevalece. Os tempos reais apontados na execução são contrastados com os planejados e
alimentam uma **calibração por módulo e por produto**, validada por uma pessoa e testada com dados reservados. O sistema conta com
322 testes automatizados e foi desenhado para validação em uma marcenaria. Discutem-se as limitações: coeficientes de base ainda
genéricos, ergonomia parcialmente integrada ao fluxo principal e ausência de validação de campo.

**Palavras-chave:** tempo padrão; estudo de tempos; ERP; gêmeo digital; inteligência artificial; ergonomia; calibração.

---

## 2. Contexto, problema e justificativa

- **Problema.** O profissional faz o produto de forma heurística, não tem tempo padrão e acaba aceitando prazos sem saber quanto o
  trabalho leva. Sem tempo padrão não há preço, prazo, capacidade nem melhoria baseada em dados.
- **Barreiras clássicas.** O estudo de tempos tradicional exige cronometragem, analista treinado e tempo; pequenas empresas raramente o fazem.
  ERPs convencionais pedem que o usuário **digite** tempos e taxas, ou seja, mudam o problema de lugar.
- **Proposta.** Inverter a lógica: o usuário descreve **produto**, **oficina** e **jornada**; o sistema deriva o tempo padrão e declara o grau
  de incerteza; a execução real melhora o padrão ao longo do tempo (ciclo *estimar → medir → melhorar*).
- **Natureza do trabalho.** O desenho é geral: toda operação produtiva combina **mão de obra + atividade + equipamento + espaço físico
  + item**. A validação inicial é em marcenaria (seção 6.6).
- **Origem conceitual.** *Script Conceitual do Sistema ERP de Produção* (PUC-Campinas, Engenharia de Produção); o mapeamento por seção
  está no Apêndice A.

---

## 3. Objetivos e questões de pesquisa  `[PROPOSTA — confirmar com o orientador]`

**Objetivo geral.** Desenvolver e documentar um ERP de produção genérico, com IA como apoio, que calcule o tempo padrão como saída a
partir das condições do trabalho, fundamentado nos métodos da Engenharia de Produção, e que aprenda com o tempo real medido.

**Objetivos específicos.**
1. Modelar o tempo padrão como composição de elementos de vocabulário fechado (tempo normal, ritmo, tolerâncias).
2. Embasar cada componente do cálculo em literatura de estudo de tempos, métodos predeterminados e ergonomia, declarando o que é premissa do projeto.
3. Delimitar o papel da IA: sugerir e explicar, nunca produzir tempo ou coeficiente.
4. Contrastar o tempo real com o planejado e calibrar o modelo com validação por pessoa e prova com dados reservados.
5. Verificar o sistema com testes automatizados e planejar a validação de campo em uma marcenaria.

**Questões de pesquisa.**
- QP1. É possível obter um tempo padrão utilizável a partir de condições (e não de tempos digitados)?
- QP2. Em que medida a calibração com histórico aprovado reduz o desvio entre previsto e realizado? `[A RESPONDER NO PILOTO]`
- QP3. Um usuário sem formação em engenharia de métodos consegue ir do produto ao plano sem ajuda? `[A RESPONDER NO PILOTO]`

---

## 4. Metodologia  `[PROPOSTA — confirmar com o orientador]`

Pesquisa **aplicada**, com desenvolvimento de **artefato** (sistema) segundo a lógica de *Design Science Research* (Hevner et al., 2004):
identificação do problema, desenho do artefato, construção, avaliação (testes automatizados e piloto) e comunicação.
O histórico de construção está no repositório: 60 *commits*, primeiro em 2026-10-08, com 14 migrações de banco que documentam a evolução do modelo de dados.
A avaliação combina (i) verificação por testes automatizados, (ii) revisão de aderência à literatura (seção 5.9) e (iii) piloto em marcenaria (seção 10.4).

---

## 5. Fundamentação teórica

### 5.1 Estudo de tempos e métodos
Origem em Taylor (1911) e nos estudos de movimentos de Gilbreth. A formulação usada pelo sistema segue Barnes (1980), Niebel e Freivalds (2003)
e a OIT (Kanawaty, 1992):

```
tempo observado (TO) ──► × avaliação de ritmo (R/100) ──► TEMPO NORMAL (TN)
TN ──► × fator de tolerâncias (FT) ──► TEMPO PADRÃO (TP)

FT = 1 / (1 − p),    p = fração de tolerâncias sobre o tempo total       (tolerância aplicada sobre o tempo total, forma clássica)
```

- **Avaliação de ritmo:** o analista compara o desempenho observado ao "ritmo normal"; 100 = normal (Westinghouse, OIT).
- **Tolerâncias:** necessidades pessoais, fadiga básica e variáveis (postura, carga, ambiente, monotonia), segundo tabelas da OIT.
- **Tamanho da amostra:** nº de ciclos a cronometrar para confiança e erro dados; forma clássica
  `N' = [ 40·√(N·Σx² − (Σx)²) / Σx ]²` (95 % de confiança, ±5 %) `[VERIFICAR em Niebel e Freivalds]`.

### 5.2 Sistemas de tempos predeterminados
MTM (Maynard, Stegemerten e Schwab, 1948) e MOST (Zandin, 2003). No BasicMOST, a *Sequência de Movimento Geral* é **A B G A B P A**
(deslocar, curvar, pegar, deslocar, curvar, posicionar, deslocar), com índices de valor 0, 1, 3, 6, 10 ou 16, e

```
tempo (TMU) = Σ índices × 10        1 TMU = 0,00001 h = 0,0006 min = 0,036 s
```

Os índices dependem de cartões **certificados** (licenciados); o sistema **não os reproduz** (ver 5.9, item 7).

### 5.3 Dados padrão e tempos de máquina
Para operações com máquina, o tempo vem de **parâmetros técnicos do processo**, p. ex. corte `t = comprimento ÷ avanço` (Groover, 2010, `[VERIFICAR edição]`).
O sistema adota essa lógica, com os parâmetros vindos da **ficha técnica do equipamento**, validada por uma pessoa.

### 5.4 Ergonomia e fadiga
- **NIOSH** (Waters et al., 1993; Waters, Putz-Anderson e Garg, 1994): `RWL = 23 kg · HM · VM · DM · AM · FM · CM`; `LI = carga ÷ RWL`.
  LI > 1 indica risco aumentado. A norma **não** converte LI em minutos de descanso.
- **Murrell** (1965): descanso por gasto energético `R = T · (W − S) / (W − 1,5)`, com `W` = gasto no trabalho (kcal/min) e `S` = limite adotado.
  Os limites `S` por sexo e jornada **divergem entre fontes**; o sistema não embute valor.
- **RULA** (McAtamney e Corlett, 1993): avaliação postural de membros superiores, pontuação de 1 a 7 com níveis de ação. **Não produz tempo nem percentual de descanso**;
  qualquer conversão em tolerância seria premissa. `[NÃO IMPLEMENTADO]`
- **Normas brasileiras:** NR-17 (ergonomia), NR-15 (ruído, calor), CLT arts. 58, 59, 71 (jornada e intervalos) e 198, 390, 405 (carga). Usadas como **alertas**; a vigência deve ser conferida `[VERIFICAR]`.
- O sistema é **triagem de apoio à decisão**; não substitui a Análise Ergonômica do Trabalho (NR-17) nem um estudo de tempos feito por profissional.

### 5.5 ERP e sistemas de apoio à produção
ERP integra informação de produção, estoque, vendas e finanças. O GEMai trata o recorte **planejamento e controle da produção** (PCP): roteiros,
tempos, ordens, apontamentos, desvios. Escopo excluído: seção 12.3.

### 5.6 Gêmeo digital
Representação virtual de um sistema físico, alimentada por dados do real (Grieves, 2014; Grieves e Vickers, 2017). No GEMai, o "gêmeo" é o modelo
**blocos → elementos de tempo → minutos**, contrastado com o apontado e recalibrado.

### 5.7 IA generativa com fronteira de confiança
Modelos de linguagem produzem texto plausível, não necessariamente correto. A arquitetura adotada separa **sugestão** (IA) de **cálculo e validação** (sistema):
catálogo fechado, esquemas validados, dado faltante vira pendência, sugestão nunca grava sozinha (seção 8).

### 5.8 Estatística da calibração
Mediana (robusta a *outliers*); regressão robusta de **Theil–Sen** (Theil, 1950; Sen, 1968) para aprender como o erro escala com o porte do pedido;
**validação cruzada *leave-one-out*** (Stone, 1974) como prova com dados reservados.

### 5.9 Matriz de rastreabilidade: cada componente do tempo padrão × literatura  *(núcleo do TCC)*

| # | Componente | Como o sistema calcula | Base na literatura | Status | Lacuna e ação |
|---|---|---|---|---|---|
| 1 | Estrutura TN → TP | `TP = TN · FT`, `FT = 1/(1−p)`, `p ≤ 50 %` | Barnes; Niebel e Freivalds; OIT | `[IMPLEMENTADO]` | O teto de 50 % é escolha do projeto |
| 2 | Ritmo (TN a partir do observado) | `TN = TO · R/100`; ritmo da pessoa > do perfil > 100; só no que depende do operador | Barnes; OIT (avaliação de ritmo) | `[PARCIAL]` | O ritmo calibrado é **relativo à equipe** (mediana = 100), **não** avaliação por observação. Ação: modo cronoanálise (12.1) |
| 3 | Tolerâncias constantes | necessidades pessoais 5 % + fadiga básica 4 % (valor único, sem distinção por sexo) | OIT, *Introduction to Work Study* | `[IMPLEMENTADO]` | Valores conferidos em fonte secundária `[VERIFICAR na publicação original]`. A literatura clássica apresenta valores diferentes por sexo para necessidades pessoais; o valor único é **decisão de projeto** (não discriminar), e deve ser declarada |
| 4 | Tolerância por carga | `LI` pela equação NIOSH; `LI → %` por tabela do projeto (≤1: 0 %; ≤2: 5 %; ≤3: 10 %; >3: 15 %) | Waters et al. (1993) para o LI; **conversão é premissa** | `[PARCIAL]` | **No fluxo principal (Produto → Oficina → Plano) os dados de levantamento nunca são fornecidos**, logo não entra no plano. Só no fluxo legado de processos |
| 5 | Tolerância por gasto energético | Murrell, com `S` do perfil | Murrell (1965) | `[PARCIAL]` | Mesma lacuna do item 4 (gasto energético não alimentado no plano) |
| 6 | Postura | ponto de extensão | RULA, REBA, OWAS | `[NÃO IMPLEMENTADO]` | Implementar só com as tabelas originais conferidas |
| 7 | Ambiente (ruído, temperatura) | **alerta**, sem percentual | NR-15 | `[PARCIAL]` | Calor (IBUTG) e iluminação não calculados: texto oficial não verificado |
| 8 | Tempo de máquina | corte: `m ÷ avanço`; borda: `m ÷ velocidade`; furação: `ciclos · curso ÷ avanço` | Dados de processo de usinagem (Groover) | `[IMPLEMENTADO]` | Não inclui **alimentação e retirada manual**; o avanço da ficha vale para todos os materiais e espessuras |
| 9 | Deslocamento | `viagens = ⌈qtd ÷ itens por viagem⌉`; `t = viagens · distância ÷ velocidade · 2` | Princípio de movimentação de materiais | `[PARCIAL]` | Caminhada 75 m/min e 20 kg/pessoa são **referências genéricas sem fonte** |
| 10 | Pegar e posicionar | `(levantamento curvado + posicionamento preciso)` em MOST ⇒ 29 índices × 10 × 0,0006 = **0,174 min/peça** | BasicMOST (Zandin) | `[PARCIAL]` | Índices **ilustrativos**, não conferidos com cartão certificado |
| 11 | Fixação (parafuso, dobradiça…) | `n × coeficiente` (ex.: 0,30 min/parafuso; 1,5 min/dobradiça) | Dados padrão/tempos sintetizados (Barnes) | `[NÃO EMBASADO]` | **Referências genéricas do projeto, sem fonte.** Ação: cronoanálise ou MOST certificado |
| 12 | Preparação | máquina 5 min; posto 2 min | — | `[NÃO EMBASADO]` | Genérico. Ação: medição |
| 13 | Conferência final | 5 min por unidade | — | `[NÃO EMBASADO]` | Genérico. Ação: medição |
| 14 | Divisão do trabalho entre pessoas | trabalho manual `÷ n` (caso ideal) | — | `[PARCIAL]` | Sem curva de aprendizagem nem perda de coordenação; é premissa declarada |
| 15 | Calibração por módulo | `fator = mediana(TN observado ÷ TN previsto)`, limitado a 0,5–2,0, ≥ 10 amostras, validação por pessoa | Estatística robusta | `[IMPLEMENTADO]` | **Problema conhecido com equipes (11.2, item 4)** |
| 16 | Calibração por família | Theil–Sen sobre ln(razão) × ln(porte); *leave-one-out*; ganho ≥ 10 % para valer | Theil; Sen; Stone | `[IMPLEMENTADO]` | Mesmos pré-requisitos de dados do item 15 |
| 17 | Nº mínimo de amostras | fixo (3 histórico; 5 ritmo; 10 módulo; 8 família) | Tamanho de amostra (Niebel) | `[PARCIAL]` | Limites **heurísticos**, não calculados por confiança e erro |
| 18 | Fadiga ao longo do turno | fora do cálculo | — | `[NÃO IMPLEMENTADO]` | Só entra quando aprendida de dados |
| 19 | Jornada e agenda | blocos de horário, intervalos, só dias úteis | CLT arts. 58, 59, 71 (alertas) | `[IMPLEMENTADO]` | Sem feriados. Sequência única, sem paralelismo (exceto no arranjo recomendado) |

**Consequência para a redação:** o TCC pode afirmar que a **estrutura** do tempo padrão segue a literatura (itens 1, 3, 8, 15, 16, 19) e que há
**pontos explicitamente não embasados** (itens 11 a 13) e **não integrados ao fluxo** (4 a 7), com plano de correção (seção 12.1).
Na prática, hoje, o fator de tolerância do plano é quase sempre `1/(1−0,09) ≈ 1,099`, pois só as constantes da OIT entram.

---

## 6. O sistema

### 6.1 Princípios
1. **O tempo padrão é saída.** Entradas válidas são *condições* (produto, meios, ambiente, jornada, perfil), nunca o tempo. Ninguém digita tempo, taxa ou % de tolerância.
2. **A IA sugere, o sistema valida.** A IA escolhe módulos de um catálogo fechado e explica; nunca escreve tempo nem coeficiente.
3. **Sem dado, sem chute.** Dado faltante vira pendência e o passo fica "sem tempo", nunca zero.
4. **O medido prevalece.** Dado medido ou validado por pessoa vence a estimativa; tudo fica na trilha de auditoria.
5. **Confiança honesta.** A confiança do plano nunca é "alta"; só chega a "média" se o plano é completo, a IA não declarou "baixa" e nada no cálculo é coeficiente genérico ou capacidade estimada pela IA. Os motivos aparecem nas premissas.

### 6.2 Requisitos (resumo)
**Funcionais:** cadastro de produto (peças e ligações) com descrição por IA; contorno físico (locais, distâncias, meios com ficha técnica, peso); plano de trabalho com tempo
padrão por unidade, agenda e verificação de prazo; arranjo recomendado (equipe, lotes, meio); ordem de produção, fila, apontamento com aprovação por segunda pessoa; calibração com validação;
relatório previsto × realizado por variante; auditoria.
**Não funcionais:** multiempresa com isolamento rígido; reprodutibilidade (todo coeficiente com valor, unidade, fonte, status e versão); rastreabilidade; LGPD; execução em Docker e Render; PostgreSQL em produção.

### 6.3 Arquitetura e tecnologias
- **Back-end:** Python 3.13; FastAPI; SQLAlchemy 2; Alembic (14 migrações); Pydantic 2; Argon2id; JWT; SQLite (desenvolvimento) e PostgreSQL (produção, driver `psycopg`).
- **Front-end:** JavaScript puro (módulos ES), sem *build*; rotas por `hash`; sem `innerHTML`.
- **IA:** provedor externo opcional (Anthropic, modelo configurável, padrão `claude-opus-5-5`) e **provedor local por regras** como padrão e contingência.
- **Implantação:** `Dockerfile`, `docker-compose.yml`, `render.yaml` (aplicação + PostgreSQL), `start.sh` (migra e sobe a API).
- **Dimensão (2026-11-17):** ~12 mil linhas de Python na aplicação, ~4,6 mil de testes, ~2,5 mil de JavaScript, 29 entidades, 123 *endpoints*, 322 testes.

```
 navegador (JS puro)  ──HTTPS──►  FastAPI (routers)  ──►  services (regras, motor de tempo)  ──►  SQLAlchemy ──► SQLite/PostgreSQL
                                        │                         │
                                        │                         └──►  IA (provedor local | Claude)  ──► validação por esquema
                                        └──►  Ctx (empresa, unidades)  ·  auditoria append-only
```

```
app/            API (routers/), regras (services/), IA (services/ia/), modelos e esquemas
  services/modulos/      catálogo de módulos de tempo
  services/tolerancias/  fontes plugáveis de tolerância
  services/arranjo/      recomendação de arranjo
static/         interface web
migrations/     Alembic
tests/          pytest (322 testes)
```

### 6.4 Modelo de dados (principais entidades, `app/models.py`)
| Grupo | Entidades |
|---|---|
| Organização | `Empresa`, `Unidade`, `Usuario`, `UsuarioUnidade` |
| Processo (fluxo legado/avançado) | `Processo`, `Etapa`, `Operacao`, `Material`, `Parametro`, `ModeloTempo`, `DiagnosticoPergunta` |
| Contorno físico | `Espaco`, `Distancia`, `Recurso` (com ficha técnica via `Parametro`), `Pessoa`, `PerfilMaoDeObra` |
| Produto e plano | `Produto`, `Componente`, `Ligacao`, `PlanoTrabalho`, `PlanoPasso`, `ReferenciaTempo` |
| Execução | `Ordem`, `OrdemOperacao`, `Apontamento`, `Ocorrencia` |
| Calibração | `CalibracaoModulo` (geral e por família) |
| Transversais | `RecomendacaoIA`, `AuditLog` |

Todo dado de negócio tem `empresa_id`. Todo parâmetro tem **origem** (`informado`, `medido`, `calculado`, `ia_sugerido`), status de validação e versão. Apontamentos nunca são apagados, só anulados com motivo.

### 6.5 Fluxo do usuário
Um **único tipo de usuário** (sem papéis). O caminho principal tem três passos, mais o relatório:

```
Entrar → Início → 1. Produto → 2. Oficina → 3. Plano de trabalho → 4. Relatório
                                                   │  (com "Mostrar detalhes técnicos" ligado)
                                                   ▼
                  Gerar ordem → Liberar → Fila (iniciar/concluir) → Aprovar registros → Calibração → validar → próximo plano
```

- **Entrada.** Primeiro acesso cria empresa, unidade e usuário (senha de 10+ caracteres com maiúscula, minúscula e número). Sessão por JWT; expira com aviso.
- **Início.** Três cartões (um por passo, com ✓ quando concluído e o que falta) e os planos recentes.
- **1. Produto.** Nome geral ("Armário", não "Armário 2 portas 80 cm"). Estrutura por **descrição em texto livre** (a IA propõe a lista; o usuário confere antes de gravar; nada é salvo antes)
  ou **à mão** (peças com medidas em metros, peso, furos, borda; ligações com método e nº de fixadores). Campos de variante (largura, tipo…) ligam-se às peças por **fórmulas** que começam com `=`
  (`={Altura}`, `=teto({Largura} * 10)`); o sistema avisa quando uma medida não afeta nenhuma peça. Sem peso, estima por densidade × medidas e rotula "estimado".
- **2. Oficina.** Assistente de 5 passos, salvo ao preencher: **locais** → **máquinas** (função e local) → **ritmo** (opcional; peças/h medidas ou estimadas pela IA, que **não alimenta o cálculo**) →
  **distâncias** (opções rápidas ou metros) → **pronto** (lista do que falta). A tela avançada acrescenta **ficha técnica** (avanço, velocidade, cabeçotes, capacidade de carga), peso por tarefa, ambiente e o
  **cadastro assistido de meios** (nome ou foto → candidatos de modelo → pessoa confirma → busca da ficha → **pessoa valida cada valor**).
- **3. Plano.** Antes de gerar, o sistema **confere a oficina** e lista pendências com atalho ao bloco certo ("Gerar mesmo assim" é possível). O pedido informa quantidade, início, equipe, jornada e perfil.
  A tela mostra o **tempo padrão por unidade**, o preparo do lote à parte, o término, alertas, pendências, os passos com horário e as premissas.
  **"Posso prometer esta data?"** responde cabe / não cabe / não dá para garantir, com o **último dia para começar**. Ações: confirmar, recalcular, imprimir, CSV, cancelar, **recomendar arranjo**.
- **4. Relatório.** Previsto × realizado por produto e variante, com desvio e planilha.
- **Fase 2 (detalhes técnicos).** Gerar ordem (plano confirmado) → liberar → **fila** (▶ iniciar, ■ concluir, quem executa) → **conferir registros** (a segunda pessoa aprova; quem registrou não aprova, salvo equipe de uma pessoa) → **calibração** → validar.

### 6.6 Generalidade e o pacote de marcenaria
O **motor** (vocabulário de elementos, tolerâncias plugáveis, calibração, agenda, multiempresa, auditoria) é genérico. O **catálogo de módulos e o modelo de produto** são, hoje, de marcenaria:

| Forma de cálculo | Módulos atuais | Fórmula |
|---|---|---|
| Processamento por meio | corte, bordo, furação | quantidade de um *driver* ÷ taxa da ficha técnica + preparo |
| Deslocamento | movimentação | viagens × distância ÷ velocidade |
| Trabalho manual por contagem | montagem | n × tempo por ação ÷ pessoas |
| Verificação | conferência | tempo fixo por unidade |

Estado: o catálogo é fixo no código (`Literal` com seis chaves) e igual para toda empresa; a montagem das condições de cada passo é um `if` por chave de módulo; o produto é lista de peças
com colunas fixas (comprimento, largura, espessura, furos, borda); o planejador local fixa a sequência corte → borda → furação → montagem. O campo `segmento` da empresa só vai como contexto para a IA.
Desenho-alvo (**`[PROPOSTA]`**) na seção 12.2.

---

## 7. Motor de tempo padrão

### 7.1 Pipeline
```
produto (peças, ligações) + oficina (meios, ficha técnica, distâncias) + pedido (quantidade, medidas, equipe, jornada, perfil)
        │
        ▼  IA/regras ESCOLHEM módulos e mapeiam peças, máquinas, locais       (nunca tempos)
        ▼  sistema deriva condições (medidas, pesos, distâncias, ficha validada)
        ▼  módulo → ELEMENTOS de vocabulário fechado → minutos
        ▼  ritmo (só no que depende do operador) → TEMPO NORMAL
        ▼  × fator de calibração validado (padrão 1)  → × FT (tolerâncias) → TEMPO PADRÃO
        ▼  agenda na jornada → plano (horários, pessoas-hora, término) → "posso prometer?"
```

### 7.2 Vocabulário fechado de elementos (`modelo_tempo.py`)
| Método | Fórmula |
|---|---|
| `fixo` | `t = a · (qtd se por unidade)` |
| `linear_driver` | `t = (a + b · driver) · (qtd se por unidade)`; driver ∈ peso, área, comprimento, volume, distância |
| `deslocamento` | `t = ⌈qtd / itens por viagem⌉ · distância / velocidade · (2 se ida e volta)` |
| `indices_most` | `t = Σ índices · 10 · 0,0006 min` |
| `capacidade_recurso` | `t = qtd / capacidade · 60` — **obsoleto**: só calcula se um chamador fornecer a capacidade (testes do motor); a capacidade digitada na oficina **não** alimenta o cálculo |

Tipos: preparação, deslocamento, manuseio, processamento, inspeção, espera fixa, outro. Elementos `paralelizavel` são divididos pelo nº de pessoas. Nada que a IA escreva é executado (não há `eval`).
Se falta dado físico (distância, peso, ficha), o elemento **não vira zero**: o resultado é marcado incompleto e a pendência é listada.

### 7.3 Camadas e fórmulas (`modelo_tempo.calcular`, `modulos/motor.py`)
1. **Tempo-base** de cada elemento, vezes o fator de ambiente (limitado a 0,5–3, padrão 1).
2. **Ritmo:** elementos que dependem do operador × `100 / ritmo_pct` (ritmo limitado a 50–150). Tempo de máquina (`depende_operador = false`) **não** recebe ritmo nem tolerância.
3. **Tempo normal** = preparação + execução, antes das tolerâncias.
4. **Fator de calibração** do módulo `k ∈ [0,5; 2,0]`, só se validado por pessoa, multiplicando tudo.
5. **Tolerâncias:** `FT = 1/(1 − p)`, `p = Σ percentuais/100 ≤ 50 %`, aplicadas **só ao tempo do operador**. Cada tolerância aparece como linha da composição:
   `minutos_i = base_operador · (FT − 1) · p_i / Σp`.
6. **Tempo padrão** = tempo normal × calibração + tolerâncias; **preparação** separada da execução. **Tempo padrão por unidade = execução ÷ quantidade**; o preparo do lote é uma vez só e aparece à parte.
7. **Fração dependente do operador** `f` = minutos dos elementos que dependem do operador ÷ total (usada para normalizar o histórico pelo ritmo).

### 7.4 Catálogo de módulos (`app/services/modulos/`)
| Módulo | O que calcula | Entradas (de onde vêm) | Pendência quando… |
|---|---|---|---|
| `movimentacao` | levar peças entre dois locais | distância (ambiente), peso máx. e médio (produto), meio (ficha: velocidade, capacidade de carga) | falta distância, peso, velocidade ou capacidade; peça mais pesada acima da capacidade do meio |
| `corte` | preparação + `metros de corte ÷ avanço` (perímetro de cada peça; conservador) | comp., larg. (produto); `avanco_corte_m_min` (ficha) | falta medida, equipamento ou avanço |
| `bordo` | preparação + `metros de borda ÷ velocidade` | `bordas_m` (produto); `velocidade_bordo_m_min` (ficha) | idem |
| `furacao` | preparação + `ciclos · curso ÷ avanço`, com `ciclos = ⌈furos ÷ cabeçotes⌉ · qtd` | `furos` (produto); cabeçotes, curso, avanço (ficha) | idem |
| `montagem` | pegar/posicionar (MOST ilustrativo) + fixação por método (`n · coeficiente`), dividido pelas pessoas; peso define o mínimo de pessoas (`⌈peso ÷ 20 kg⌉`) | ligações e fixadores (produto); equipe (pedido) | faltam ligações e fixadores |
| `conferencia` | tempo fixo por unidade do produto | quantidade | — |

**Movimentação sem meio:** pessoa carregando a 75 m/min e até 20 kg por pessoa (**referência genérica, declarada**). `itens por viagem = ⌊(20 · pessoas) ÷ peso médio⌋`. **Com meio:** `⌊capacidade ÷ peso médio⌋`.
**Registrados mas sem efeito no tempo** (não há coeficiente com fonte): altura de trabalho, precisão, tipo de piso.

### 7.5 Tolerâncias por fontes plugáveis (`services/tolerancias/`)
Cada fonte devolve itens `{categoria, percentual, fonte, premissa?}`. O código **impede percentual sem fonte**; conversão que não é da norma vai em `premissa`; dado faltante vira pendência.
| Fonte | Faz | Status |
|---|---|---|
| `oit_constantes` | 5 % necessidades pessoais + 4 % fadiga básica | `[IMPLEMENTADO]` e **única que entra no plano hoje** |
| `niosh` | LI → alerta; LI → % de fadiga por tabela do projeto | `[PARCIAL]`: sem dados de levantamento no fluxo principal |
| `murrell` | `R = T(W−S)/(W−1,5)` convertido em percentual do tempo total, `S` do perfil | `[PARCIAL]`: sem gasto energético no fluxo principal |
| `ambiente` | alerta de ruído (> 85 dB(A)) e temperatura extrema; **sem percentual** | `[PARCIAL]` |
| `postura` | ponto de extensão (RULA/REBA/OWAS) | `[NÃO IMPLEMENTADO]` |

A **fadiga de turno** não tem campo e está fora do cálculo até ser aprendida de dados reais. Sexo, estatura e peso corporal **não alteram o tempo** (há teste automatizado); só entram em limites de carga.

### 7.6 Ritmo
Precedência: `pessoa.ritmo_pct` > `perfil.ritmo_pct` > 100 (sinalizado como "padrão"). O ritmo individual é dado de desempenho (LGPD): não há ranking, e a calibração apenas **sugere**; uma pessoa confirma e o ritmo `informado` nunca é sobrescrito.
**Calibração do ritmo pela equipe:** por operação com amostras suficientes e 2+ pessoas, referência = mediana dos tempos por unidade; por pessoa, razão = referência ÷ mediana da pessoa; ritmo = mediana das razões × 100, limitado a 50–150.
> É um ritmo **relativo à equipe** (mediana = 100), **não** a avaliação de ritmo da OIT por observação. Uma equipe toda lenta ainda dá ritmos próximos de 100.

### 7.7 Histórico normalizado (fluxo de processos)
Por apontamento aprovado e não anulado: `normal = duração · (f · ritmo/100 + 1 − f)`; mediana das amostras; `× FT` do modelo; sem modelo, **não se inventa tolerância** (resultado é tempo normal, avisado).
**Prioridade do tempo planejado:** histórico aprovado > módulo (com calibração validada) > modelo da IA (legado, rotulado) > sem base. Parâmetro de tempo digitado **não é mais fonte**.

### 7.8 Calibração por módulo e por família (`calibracao_modulos.py`)
- **Amostra:** uma operação concluída (ordem não cancelada) com módulo e previsão. Observado = apontamentos **aprovados** e não anulados (preparação + execução), normalizados **por apontamento** pelo ritmo de quem executou (só na fração `f`).
  Previsto = tempo normal em ritmo 100 **sem** fator de calibração (para não calibrar sobre a calibração).
- **Fator geral do módulo:** mediana das razões, ≥ 10 amostras por (unidade, módulo), limitado a 0,5–2,0.
- **Família (produto × módulo):** `fator(porte) = fator_ref · (porte ÷ porte_ref)^b`, com **porte** = tempo normal previsto por unidade do pedido; `b` por Theil–Sen sobre ln(razão) × ln(porte), limitado a −0,5…1,0.
  Exige ≥ 8 amostras do produto, ≥ 3 tamanhos distintos e dispersão de porte ≥ 1,25×. Fora do intervalo observado (±50 %) o porte é travado na borda e o passo é rotulado **extrapolado**.
- **Prova com dados reservados (*leave-one-out*):** cada pedido é previsto pelos **outros**; a escala só é proposta se reduzir o erro típico em ≥ 10 % frente a um fator constante; senão fica o constante, e a proposta diz isso.
  Se um fator geral não melhora o erro, a proposta avisa.
- **Governança:** a prévia não grava; registrar cria **proposta pendente**; só uma pessoa a **valida** (validado + vigente, versionado). Precedência no cálculo: família validada > fator geral validado > coeficientes genéricos.

### 7.9 Agenda e prazo (`plano.py`)
- **Agendamento sequencial:** cada passo começa no primeiro instante de trabalho após o anterior (13:00 depois do almoço; 08:00 do dia útil seguinte), respeitando blocos de horário (padrão 08–12 e 13–17) e só dias úteis; não há feriados.
- **"Posso prometer esta data?"** (`POST /planos/{id}/prazo`, sem IA, sem gravar): reaproveita tempos e jornada do plano; com outra quantidade, escala **só a execução** (preparo fixo) e declara "estimativa proporcional".
  `cabe` se o fim ≤ fim do último bloco do prazo e o plano é completo; plano incompleto nunca recebe "cabe" (no máximo "não dá para garantir"). Calcula o **último dia para começar** olhando para trás.
- **Arranjo recomendado** (`services/arranjo/`): gera candidatos de equipe (1–8), lotes (1/2/4), regra de prioridade e meio de movimentação; escalona com **recursos limitados** (equipe; cada máquina faz uma coisa por vez)
  respeitando dependências derivadas da estrutura do produto; devolve a **fronteira de Pareto** (prazo, pessoas-hora, gargalo, carga ergonômica). O usuário escolhe; o plano é recalculado pelo motor. A IA só **explica**.

### 7.10 Fórmulas das peças (`formulas.py`)
Interpretador **próprio e fechado** (sem `eval`), com limites de tamanho e profundidade; campos entre chaves, decimal com ponto, argumentos separados por `;`.
Funções: `se`, `min`, `max`, `abs`, `arred`, `teto`, `piso`; operadores `+ − * /` e comparações. Liga medidas do pedido a medidas, quantidades, pesos, furos, bordas e fixadores. Proteções contra mascarar o tempo real:
medida que nenhuma peça usa gera aviso e premissa; peso fixo de peça cuja medida varia é desconsiderado; ao recalcular, as peças são **recalculadas**, nunca reaproveitadas; ajuste manual sobre valor com fórmula fica registrado.

---

## 8. Inteligência artificial no sistema

| Uso | O que a IA faz | O que o sistema faz |
|---|---|---|
| Interpretar produto | propõe componentes e ligações a partir de texto | mostra para conferência; **não grava** antes da confirmação |
| Planejar | escolhe módulos do catálogo e mapeia peças, máquinas, locais | recebe só nomes, medidas e pesos (nenhum tempo ou coeficiente); calcula todo tempo |
| Identificar meio e ficha | propõe marca/modelo (por texto ou foto); busca ficha na web | só parâmetros do catálogo, com faixa plausível e URL de fonte entram, como `ia_sugerido`; **pessoa valida** |
| Estimar capacidade | propõe peças/h com faixa, premissas e confiança (nunca "alta") | rotula "estimado pela IA"; **não alimenta o motor** |
| Explicar arranjos | explica diferenças e sugere alternativas | **recalcula** qualquer alternativa |
| Diagnóstico e estrutura (fluxo avançado) | perguntas adaptativas e proposta de processo, etapas, recursos, indicadores | cria **rascunho** editável |

**Salvaguardas:** (i) textos da empresa entram como **dados**, não instruções; (ii) toda saída é validada contra esquema (Pydantic) e saneada (limites de tamanho e de valores);
(iii) módulo fora do catálogo é recusado (tipo `Literal`); (iv) falha ou saída inválida do provedor cai para o **provedor local por regras**; (v) IA externa exige consentimento da empresa **e** chave no servidor;
(vi) fotos têm metadados/GPS removidos e **nunca são gravadas**; (vii) tempos e coeficientes **não** estão ao alcance da IA.
**Provedor local:** regras determinísticas; sem IA externa, só aproveita números escritos pelo usuário (não inventa).

---

## 9. Segurança, privacidade e auditoria
- **Isolamento multiempresa:** `empresa_id` em toda tabela de negócio; acesso por `Ctx` filtra por empresa e unidades; recurso de outro *tenant* responde 404 (`tests/test_tenancy.py`).
- **Autenticação:** Argon2id; política mínima; bloqueio temporário após falhas; mensagens e tempos iguais para usuário inexistente; JWT curto com `token_versao` (trocar senha, desativar ou mudar perfil derruba sessões).
- **Entrada e navegador:** `extra="forbid"` impede injetar `empresa_id`; corpo ≤ 1 MB; CSP estrita; `X-Frame-Options`; HSTS em produção; `/docs` desligado em produção; a interface nunca usa `innerHTML`; CSV protegido contra injeção de fórmulas.
- **Produção:** a aplicação não inicia sem `ERP_SECRET_KEY` de 32+ caracteres.
- **Auditoria *append-only*** com antes/depois, usuário e IP.
- **Dois olhos:** quem registrou o apontamento não o aprova (salvo equipe de uma pessoa); só histórico aprovado melhora estimativas.
- **LGPD (Lei 13.709/2018):** ritmo individual é dado de desempenho (finalidade, minimização, consentimento; sem ranking); perfil de mão de obra é referência, não pessoa; foto de meio não é armazenada. `GET /analise/comparacao` mostra tempo mediano por pessoa — avaliar se deve ficar disponível.
- **Limitações assumidas:** sem papéis, **qualquer usuário pode redefinir senha de outro e alterar o consentimento de IA externa** (tudo auditado); sem 2FA nem recuperação por e-mail; limitador de tentativas em memória (por processo); backups e retenção são de quem opera.

---

## 10. Verificação e validação

### 10.1 Testes automatizados `[IMPLEMENTADO]`
**322 testes** passam (SQLite), `pytest`. A integração contínua roda os testes e `alembic upgrade head` + `alembic check` (sem migração pendente). Áreas cobertas:

| Arquivo(s) | O que verifica |
|---|---|
| `test_timecalc`, `test_formulas`, `test_modulos`, `test_tolerancias` | fórmulas, elementos, módulos, FT |
| `test_plano`, `test_fluxo`, `test_arranjo` | plano, agenda, prazo, arranjos, ordem |
| `test_calibracao_modulos`, `test_ritmo_historico` | calibração, normalização pelo ritmo, validação por pessoa |
| `test_fatores_humanos`, `test_contorno`, `test_meios` | ergonomia, oficina, fichas técnicas |
| `test_auth`, `test_tenancy`, `test_equipe` | segurança, isolamento, equipe |
| `test_capacidade_ia`, `test_simples`, `test_variantes_relatorio` | IA com resposta simulada, fluxo simples, relatório |
| `test_infra_deploy` | configuração de produção e migrações |

Invariantes com teste: dado faltante não vira zero; plano incompleto nunca recebe "cabe"; confiança nunca é "alta"; sexo, estatura e peso não alteram o tempo; 60 peças a 60 peças/h voltam a ser 60 min (tolerância não multiplica tempo de máquina).

### 10.2 Conferência de fontes
Tabelas FM/CM do NIOSH, fórmula de Murrell, estrutura do MOST, limites da CLT e tolerâncias da OIT foram conferidas em **fontes públicas secundárias**, não nas publicações originais `[VERIFICAR]`.

### 10.3 O que **não** foi validado
- Execução contra **PostgreSQL real** (testes em SQLite); os últimos *commits* corrigiram implantação no Render.
- Chamadas reais à API da Anthropic (o provedor foi testado com resposta simulada).
- **Qualquer validação de campo**: não há dados de uso real.
- Usabilidade com o público-alvo.

### 10.4 Protocolo de validação de campo (marcenaria) `[PROPOSTA]`
1. **Preparação:** cadastrar locais, máquinas e **fichas técnicas validadas**; produtos reais (3 a 5) com peças, ligações e pesos. Cadastro público de empresa desligado.
2. **Execução:** gerar planos, abrir ordens, apontar pela fila (com pessoa executora) e aprovar por segunda pessoa. Definir de antemão a duração e o volume mínimo (a calibração pede ≥ 10 amostras por módulo e ≥ 8 por produto; uma ordem gera uma amostra por passo).
3. **Medidas de sucesso:** (a) desvio previsto × realizado por variante (antes e depois da calibração); (b) erro típico na prova com dados reservados; (c) fração de planos completos sem pendência; (d) usuário vai de Produto a Plano **sem ajuda** (teste de uso, separado do cálculo).
4. **Ameaças:** equipe de 1 ou 2 pessoas (aprovação por segunda pessoa); viés da calibração com equipe (11.2, item 4); coeficientes genéricos dominando o erro; amostras insuficientes.
5. **Congelar** o motor durante o piloto: mudar o cálculo no meio impede atribuir melhorias ao uso real.

---

## 11. Limitações conhecidas e problemas abertos

### 11.1 Limitações do cálculo (declaradas ao usuário)
1. Ordens geradas por plano só alimentam a **calibração por módulo** (fator validado), não o histórico por operação.
2. Coeficientes de montagem, preparação e conferência são **referências genéricas**; os índices MOST são **ilustrativos**. O tempo padrão é uma estimativa de **ordem de grandeza** até haver medição ou calibração.
3. **Sequência única de passos**, sem trabalho em paralelo entre eles; pessoas-hora assumem toda a equipe ocupada em todos os passos (prazo tende a ser superestimado com equipe).
4. **Divisão ideal do trabalho** entre pessoas, sem curva de aprendizagem nem perda de coordenação (prazo pode ser otimista com equipes grandes).
5. Sem feriados; sem fadiga de turno; piso, altura de trabalho e precisão não alteram o tempo.

### 11.2 Problemas identificados na revisão (2026-11-17)
| # | Problema | Evidência | Impacto | Correção proposta |
|---|---|---|---|---|
| 1 | **Tempos de máquina não incluem alimentação e retirada manual** das peças | `modulos/usinagem.py` (premissa `_NAO_MANUSEIO`) | Subestima corte, furação e borda | Elementos manuais com coeficiente de fonte; ou medição |
| 2 | **NIOSH e Murrell não recebem dados no fluxo do plano** | `plano.py`: o contexto de tolerâncias só tem local e perfil | Só 9 % (FT ≈ 1,099) entra; o README anterior dizia o contrário | Atributos de condição de trabalho por passo (frequência, altura, gasto energético) |
| 3 | **Nenhuma checagem de cobertura do plano** | `plano.persistir`: `completo` só olha dado faltante | Se a IA omitir um passo, o plano sai "completo" e mais curto | Validar que toda peça está em algum passo e que existe montagem |
| 4 | **Viés da calibração com equipe de 2+ pessoas** | **Reproduzido em teste**: montagem de 2 pessoas, previsto 10 min corridos, real 10 min; razão = 1,0 se uma pessoa aponta e **2,0** se as duas apontam | Fator inflado até o teto de 2,0; pune quem aponta melhor | `observado = união dos intervalos × média ponderada do ritmo` (`timecalc.uniao_minutos` já existe); 3 testes de regressão |
| 5 | Caminho do histórico por operação (`estimativa._pelo_historico`) pode ter o mesmo viés | não verificado | idem | Verificar ao corrigir o item 4 |
| 6 | Calibrar o ritmo e o módulo juntos pode absorver o nível da equipe | documentado no código | O fator "não é verdade OIT" | Declarar no texto; modo cronoanálise |
| 7 | Limite de 50 % para tolerâncias e mínimos de amostra são escolhas heurísticas | `LIMITE_TOLERANCIA`, `min_amostras_*` | — | Calcular tamanho de amostra por confiança e erro |
| 8 | O assistente da Oficina pergunta "peças por hora", dado que o cálculo ignora; a ficha técnica só é editada na tela avançada | `telas_contorno.js` | Confunde o usuário | Reordenar o assistente; destacar a ficha técnica |
| 9 | O ciclo "medir e melhorar" fica atrás do interruptor de detalhes técnicos | `app.js` (rotas com flag) | Quem seguir só o menu principal nunca mede o real | Modo piloto com o ciclo visível |
| 10 | Catálogo acoplado à marcenaria (seção 6.6) | `catalogo.py`, `entradas.py` | Não é genérico na prática | Seção 12.2 |

### 11.3 Outras limitações
README anterior citava 306 testes (hoje 322). O sistema é triagem de apoio à decisão e **não** substitui estudo de tempos por profissional nem a AET.

---

## 12. Trabalhos futuros e roadmap de embasamento

### 12.1 Fechar o embasamento do tempo padrão na literatura  `[PROPOSTA]`
Ordem sugerida (do que mais reduz a distância entre o que se afirma e o que se calcula):
1. **Integrar a ergonomia ao fluxo principal:** cada passo ganha condições de trabalho (frequência de levantamento, alturas, gasto energético) para NIOSH e Murrell entrarem no FT.
2. **Corrigir os itens 3 e 4 da seção 11.2** (cobertura do plano; viés da calibração com equipe).
3. **Modo cronoanálise** (Barnes; Niebel e Freivalds): registro de ciclos por elemento, avaliação de ritmo por observação, **tamanho de amostra** pela fórmula clássica, tempo padrão por elemento. Substitui os coeficientes genéricos (itens 11 a 13 da 5.9) por dados com fonte e rastreabilidade.
4. **Sistema de tempos predeterminados** (MOST ou MTM) com índices conferidos no cartão certificado — ou declarar explicitamente que não é usado e remover o "ilustrativo".
5. **RULA** (McAtamney e Corlett, 1993) a partir das **tabelas originais**; conversão score → tolerância sempre rotulada como premissa.
6. **Tempos manuais de alimentação e retirada** nos módulos de máquina; fadiga de turno aprendida de dados; feriados na agenda; curva de aprendizagem.
7. **Conferir as fontes originais** das constantes da OIT (valor único × por sexo), NIOSH e Murrell.

### 12.2 Generalizar o catálogo (pacotes de módulos)  `[PROPOSTA]`
Os seis módulos são instâncias de poucas formas (seção 6.6). Desenho-alvo:
- **Módulo como dado:** forma de cálculo + fórmula do *driver* (reaproveita o interpretador de `formulas.py`) + parâmetros da ficha + coeficientes + preparo.
- **Registro de pacotes** no lugar do `Literal` fixo; o esquema da IA e a validação saem do registro. **Marcenaria = primeiro pacote** (congelado como v1); outro segmento = novo conjunto de dados.
- **Item de produto com atributos livres** (mantendo as colunas atuais e migrando por etapas).
- **Interface por pacote** ("Oficina" → "Local de produção"; sugestões de locais, máquinas, métodos).
- **Sequência padrão** declarada no pacote, para o planejador local funcionar sem IA externa.
- **Pré-requisito:** testes de regressão com planos completos de marcenaria em minutos fixos, para que a refatoração dê exatamente o mesmo número.

### 12.3 Fora do escopo atual (seção 20 do script conceitual)
Estoque e compras, vendas/CRM, integrações, importação de listas de materiais, IoT/CNC, modelos preditivos, aplicativo móvel, manutenção, módulo de qualidade, programação da produção entre vários produtos e simulação de capacidade.
Também: curva de aprendizagem, MTM-1 completo, REBA/OWAS, Snook e Ciriello, IBUTG, iluminação por tarefa, módulos de lixamento/pintura/acabamento.

---

## 13. Operação

### 13.1 Rodar localmente
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload          # http://localhost:8000  (API em /docs, só fora de produção)
python -m pytest -q                    # suíte de testes
```
Em desenvolvimento as tabelas são criadas automaticamente (SQLite). Em produção use migrações: `alembic upgrade head`.

### 13.2 Variáveis (`ERP_*`, veja `.env.example`)
| Variável | Padrão | Função |
|---|---|---|
| `ERP_AMBIENTE` | `desenvolvimento` | `producao` exige segredo forte e desliga `/docs` |
| `ERP_DATABASE_URL` | `sqlite:///./erp.db` | em produção, `postgresql://` (normalizado para `postgresql+psycopg://`) |
| `ERP_SECRET_KEY` | — | 32+ caracteres aleatórios |
| `ERP_TOKEN_MINUTOS` | 60 | validade do token |
| `ERP_PERMITIR_CADASTRO_PUBLICO` | `true` | `false` = só a equipe cria usuários |
| `ERP_CORS_ORIGENS` | vazio | vazio = só mesma origem |
| `ERP_MIN_AMOSTRAS_HISTORICO` | 3 | amostras para o histórico valer |
| `ERP_MIN_AMOSTRAS_RITMO` / `ERP_MIN_OPERACOES_RITMO` | 5 / 1 | calibração do ritmo |
| `ERP_MIN_AMOSTRAS_CALIBRACAO` / `ERP_MIN_AMOSTRAS_FAMILIA` | 10 / 8 | calibração por módulo / por família |
| `ERP_USAR_MODELO_IA_NAO_VALIDADO` | `true` | modelo legado não validado vale como tempo planejado (rotulado) |
| `ERP_IA_PROVEDOR` | `auto` | `auto` \| `heuristica` \| `claude` |
| `ERP_ANTHROPIC_API_KEY`, `ERP_IA_MODELO` | — / `claude-opus-5-5` | IA externa (opcional) |
| `POSTGRES_PASSWORD`, `FORWARDED_ALLOW_IPS` | — / `127.0.0.1` | `docker-compose` e proxy reverso |

### 13.3 Produção
- **Docker:** `cp .env.example .env`; preencha `ERP_SECRET_KEY` e `POSTGRES_PASSWORD`; `docker compose up -d`; ponha um proxy reverso com HTTPS na frente e ajuste `FORWARDED_ALLOW_IPS` (senão o limitador de tentativas vê todos como um IP).
- **Render:** *Blueprint* (`render.yaml`): serviço Docker + PostgreSQL, `healthCheckPath: /api/v1/saude`, segredo gerado.
- **Primeiro acesso:** o `render.yaml` sobe com `ERP_PERMITIR_CADASTRO_PUBLICO=true` para criar a primeira empresa; **depois, mude para `false`**. No `docker-compose.yml` o padrão é `false` e **não existe comando** para criar a primeira empresa: defina `true`, cadastre a empresa, volte para `false` e reinicie.

---

## 14. Apêndices

### Apêndice A — Mapeamento do *Script Conceitual* → implementação
| Seção do script | Implementação |
|---|---|
| Tela 1 – Cadastro e descrição | Unidade com descrição, objetivo, problemas, fontes (`/unidades`) |
| Tela 2 – Diagnóstico inteligente | Perguntas adaptativas por grupo (11 grupos), respostas gravadas (`/unidades/{id}/diagnostico`) |
| Tela 3 – Estrutura automática | Proposta da IA (processo › etapas › operações, recursos, materiais, indicadores, etapas possivelmente omitidas), editável antes de aprovar; cria rascunho |
| Tela 4 – Recursos | Ficha do recurso (capacidade, espaço); tempo médio e de preparação calculados do histórico aprovado |
| Tela 5 – Ordem | Roteiro do processo ativo ou do plano; status planejada → liberada → em produção ⇄ parada → concluída/cancelada |
| §10 Tempo e cálculo | `services/timecalc.py` (fórmulas `linear`, `lote`, `fixo`) e o motor modular |
| §11 IA em uso | Perguntas, estrutura, indicadores, operações semelhantes, explicação de desvios, gargalos, relatório (sempre como sugestão com evidências) |
| §12 Ergonomia | Fatores por operação + sinalização (não é avaliação ergonômica formal) |
| §13 Dashboard | Ordens abertas/atrasadas, planejado × realizado, gargalos, paradas, retrabalho, produtividade, utilização, qualidade, tendência semanal |
| §14 Entidades | `app/models.py` |
| §17 IA sugere, sistema valida | seção 8 |
| §18 Segurança e permissões | seção 9 |
| §20 Fora do MVP | seção 12.3 |

### Apêndice B — Coeficientes e constantes do catálogo (todas **referências genéricas do projeto**, exceto onde indicado)
| Chave | Valor | Unidade | Observação |
|---|---|---|---|
| `velocidade_caminhada_m_min` | 75 | m/min | genérico |
| `carga_manual_max_kg` | 20 | kg/pessoa | genérico (distinto dos limites legais, que são só alertas) |
| `preparacao_maquina_min` / `preparacao_posto_min` | 5 / 2 | min | genérico |
| `pegar_posicionar_peca_min` | 0,174 | min/peça | MOST **ilustrativo**: (20 + 9) índices × 10 × 0,0006 |
| `fixador:parafuso` | 0,30 | min/un | genérico |
| `fixador:cavilha` / `minifix` | 0,20 / 0,45 | min/un | genérico |
| `fixador:dobradica` / `corredica` | 1,50 / 2,00 | min/un | genérico |
| `fixador:cola` / `prego` / `encaixe` | 0,50 / 0,10 / 0,15 | min/un | genérico |
| `fixador:puxador` / `outro` | 0,80 / 0,50 | min/un | genérico |
| `conferencia_final` | 5,0 | min/unidade | genérico |
| tolerância pessoal / fadiga básica | 5 / 4 | % | OIT (fonte secundária) |
| `FADIGA_POR_LI` | ≤1: 0; ≤2: 5; ≤3: 10; >3: 15 | % | **premissa do projeto** |
| Densidades (estimar peso) | mdf 700; mdp 650; compensado 600; pinus 500; madeira 600; aço 7850; alumínio 2700; vidro 2500 | kg/m³ | referência, sempre rotulada "estimado" |
| Limites do motor | ritmo 50–150; fator ambiente 0,5–3; tolerância ≤ 50 %; calibração 0,5–2,0; expoente −0,5…1,0 | — | escolhas do projeto |
| Calibração da família | ≥ 3 tamanhos; dispersão ≥ 1,25×; extrapolação ±50 %; ganho ≥ 10 % | — | escolhas do projeto |
| Limites legais (alertas) | 60 kg (CLT 198); 20 kg contínuo / 25 kg ocasional (CLT 390, 405 §5º); ruído 85 dB(A) (NR-15) | — | conferir vigência |

### Apêndice C — Estados e regras de negócio
- **Plano:** rascunho → confirmado (manual) → ordem gerada; ou cancelado. Plano com passos sem tempo pode ser confirmado, com aviso; os passos entram na ordem como "sem base".
- **Ordem:** planejada → liberada → em produção ⇄ parada → concluída | cancelada.
- **Apontamento:** registrado → aprovado | rejeitado; anulável com motivo; nunca apagado.
- **Calibração:** pendente → validado (vigente, versionado) | rejeitado; nova versão aposenta a vigente.
- **Convenções de tempo:** realizado = preparação + execução + retrabalho (soma bruta dos apontamentos); total = realizado + espera; desvio = realizado − estimado (positivo = demorou mais); eficiência = estimado ÷ realizado.
  **Atenção:** o previsto do plano é **tempo padrão** (com tolerâncias), e o realizado é tempo bruto: trabalhar exatamente no tempo normal aparece como desvio negativo. A calibração compara tempo **normal** observado com o previsto.

### Apêndice D — Mapa de endpoints (123 rotas)
| Área | Rotas principais |
|---|---|
| Autenticação e equipe | `/auth/registrar`, `/auth/login`, `/auth/renovar`, `/auth/eu`, `/usuarios` |
| Empresa e unidades | `/empresa`, `/unidades` |
| Produto e plano | `/produtos/{id}/estrutura`, `/componentes`, `/ligacoes`, `/interpretar`, `/montar`; `/planos` (criar, recalcular, confirmar, `/prazo`, `/gerar-ordem`, `/exportar.csv`, `/arranjos`, `/de-arranjo`) |
| Oficina | `/contorno`, `/espacos`, `/distancias`, `/recursos`, `/recursos/{id}/ficha-tecnica`, `/meios/identificar`, `/recursos/{id}/estimar-capacidade` |
| Módulos e modelo | `/modulos`, `/operacoes/{id}/estimativa`, `/modulo/sugerir`, `/modelo-tempo`, `/ergonomia`, `/processos/{id}/prontidao` |
| Execução | `/ordens`, `/operador/fila`, `/apontamentos` (iniciar, finalizar, aprovar, rejeitar, anular), `/ocorrencias` |
| Calibração | `/calibracao/modulos` (prévia, aplicar, validar, rejeitar), `/pessoas/calibrar-ritmo` |
| Análise | `/relatorios/desempenho(.csv)`, `/dashboard`, `/analise/comparacao`, `/auditoria` |
| Processos (fluxo avançado) | `/processos`, `/etapas`, `/operacoes`, `/parametros`, `/unidades/{id}/diagnostico` |
| IA | `/recomendacoes`, `/ia/analises` |
| Saúde | `/api/v1/saude` |

### Apêndice E — Glossário
**Tempo normal:** tempo que um operador qualificado leva em ritmo normal. **Tolerância:** acréscimo para necessidades pessoais, fadiga e variáveis do trabalho. **Tempo padrão:** tempo normal mais tolerâncias.
**Ritmo:** avaliação do desempenho em relação ao normal (100). **TMU:** unidade de tempo do MTM/MOST (0,036 s). **Módulo:** unidade de cálculo do catálogo. **Elemento:** parcela de tempo de vocabulário fechado.
**Ficha técnica:** parâmetros do equipamento (avanço, velocidade, capacidade). **Contorno físico / oficina:** locais, distâncias, meios e pesos. **Arranjo:** combinação de equipe, lotes, regra e meio.
**Família:** conjunto de pedidos do mesmo produto com tamanhos diferentes. **Porte:** tempo normal previsto por unidade do pedido. **Pendência:** dado faltante listado, nunca valor escondido.

---

## 15. Referências  `[VERIFICAR edição, ano e páginas de cada item antes da entrega]`

BARNES, R. M. **Motion and time study: design and measurement of work**. 7. ed. New York: Wiley, 1980.

BRASIL. **Decreto-Lei nº 5.452, de 1º de maio de 1943** (Consolidação das Leis do Trabalho), arts. 58, 59, 71, 198, 390 e 405.

BRASIL. **Lei nº 13.709, de 14 de agosto de 2018** (Lei Geral de Proteção de Dados Pessoais).

BRASIL. Ministério do Trabalho e Emprego. **NR 15 – Atividades e operações insalubres** e **NR 17 – Ergonomia** (redação vigente).

GRIEVES, M. **Digital twin: manufacturing excellence through virtual factory replication**. White paper, 2014.

GRIEVES, M.; VICKERS, J. Digital twin: mitigating unpredictable, undesirable emergent behavior in complex systems. In: KAHLEN, F.-J.; FLUMERFELT, S.; ALVES, A. (ed.). **Transdisciplinary perspectives on complex systems**. Cham: Springer, 2017. p. 85–113.

GROOVER, M. P. **Fundamentals of modern manufacturing: materials, processes, and systems**. 4. ed. Hoboken: Wiley, 2010.

HEVNER, A. R.; MARCH, S. T.; PARK, J.; RAM, S. Design science in information systems research. **MIS Quarterly**, v. 28, n. 1, p. 75–105, 2004.

IIDA, I.; BUARQUE, L. **Ergonomia: projeto e produção**. 3. ed. São Paulo: Blucher, 2016.

KANAWATY, G. (ed.). **Introduction to work study**. 4. ed. (rev.). Geneva: International Labour Office, 1992.

MARTINS, P. G.; LAUGENI, F. P. **Administração da produção**. 2. ed. São Paulo: Saraiva, 2005.

MAYNARD, H. B.; STEGEMERTEN, G. J.; SCHWAB, J. L. **Methods-time measurement**. New York: McGraw-Hill, 1948.

McATAMNEY, L.; CORLETT, E. N. RULA: a survey method for the investigation of work-related upper limb disorders. **Applied Ergonomics**, v. 24, n. 2, p. 91–99, 1993.

MURRELL, K. F. H. **Ergonomics: man in his working environment**. London: Chapman and Hall, 1965.

NIEBEL, B. W.; FREIVALDS, A. **Methods, standards, and work design**. 11. ed. New York: McGraw-Hill, 2003.

SEN, P. K. Estimates of the regression coefficient based on Kendall's tau. **Journal of the American Statistical Association**, v. 63, n. 324, p. 1379–1389, 1968.

STONE, M. Cross-validatory choice and assessment of statistical predictions. **Journal of the Royal Statistical Society, Series B**, v. 36, n. 2, p. 111–147, 1974.

TAYLOR, F. W. **The principles of scientific management**. New York: Harper & Brothers, 1911.

THEIL, H. A rank-invariant method of linear and polynomial regression analysis. **Proceedings of the Koninklijke Nederlandse Akademie van Wetenschappen**, v. 53, p. 386–392, 521–525, 1397–1412, 1950.

WATERS, T. R.; PUTZ-ANDERSON, V.; GARG, A.; FINE, L. J. Revised NIOSH equation for the design and evaluation of manual lifting tasks. **Ergonomics**, v. 36, n. 7, p. 749–776, 1993.

WATERS, T. R.; PUTZ-ANDERSON, V.; GARG, A. **Applications manual for the revised NIOSH lifting equation**. Cincinnati: DHHS (NIOSH), 1994. (Publication n. 94-110).

ZANDIN, K. B. **MOST work measurement systems**. 3. ed. New York: Marcel Dekker, 2003.

> **Fontes citadas no código** (para conferência cruzada): OIT, *Introduction to Work Study* (constantes de tolerância); NIOSH Pub. 94-110 e CCOHS/CDC (tabelas FM e CM, conferidas em fonte secundária);
> McAtamney e Corlett (1993) (RULA, **não implementado**); NR-15 Anexo 1 (ruído, 85 dB(A), 8 h).

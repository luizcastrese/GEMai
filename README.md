# ERP de Produção com IA

ERP genérico orientado à produção, multiempresa, baseado no *Script Conceitual do Sistema ERP de Produção*
(PUC-Campinas – Engenharia de Produção). A empresa descreve a operação com as próprias palavras; a IA sugere
perguntas e uma estrutura de processo; **a IA sugere, o sistema valida** — nada vira dado do ERP sem
aprovação de um responsável, e tudo fica na trilha de auditoria.

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
| Tela 4 – Recursos | Ficha do recurso; tempo médio e de preparação **calculados do histórico aprovado** |
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
- **Não inventa tempo.** Sem parâmetro validado nem histórico, a operação fica `sem_base` e a ordem mostra "sem base" em vez de um número.
- **Estimativa.** Histórico (mediana de apontamentos **aprovados**, mín. `ERP_MIN_AMOSTRAS_HISTORICO`) > parâmetro validado > sem base. A fonte é exibida em cada operação. "Atualizar pelo histórico" grava nova versão do parâmetro, rastreável.
- **Convenções de tempo.** Realizado = preparação + execução + retrabalho (soma dos apontamentos, ou seja, tempo de trabalho). Total = realizado + espera. Desvio = realizado − estimado. Eficiência = estimado ÷ realizado. Fila entre operações é calculada (fim da anterior → início da próxima). Se a sua empresa usa outra convenção, ajuste `timecalc.py`/`metricas.py`.
- **Versionamento de processo.** Cada versão é uma linha; só rascunho edita estrutura; ordens ficam presas à versão em que nasceram.
- **Apontamentos nunca são apagados**, só anulados com motivo; operador só vê os próprios.

## Segurança (uso por terceiros)

- **Isolamento multiempresa:** toda tabela de negócio tem `empresa_id`; todo acesso passa por `Ctx` (`app/deps.py`) que filtra por empresa e, para gestor/operador, pelas **unidades atribuídas**. Recurso de outro tenant responde 404. Há testes dedicados (`tests/test_tenancy.py`).
- Perfis: **admin** (tudo da empresa), **gestor** (edita/aprova nas suas unidades), **operador** (fila e apontamentos próprios).
- Senhas com Argon2id; política mínima; bloqueio temporário após falhas; mensagens/tempos iguais para usuário inexistente; JWT curto com `token_versao` (trocar senha, desativar ou mudar perfil derruba sessões).
- Entradas validadas (`extra="forbid"` impede injetar `empresa_id`), limite de corpo de 1 MB, CSP estrita, `X-Frame-Options`, HSTS em produção, `/docs` desligado em produção, e a UI nunca usa `innerHTML`.
- Em produção a aplicação **não inicia** sem `ERP_SECRET_KEY` forte.
- **IA externa só com consentimento:** o admin precisa habilitar "IA externa" na empresa **e** o servidor precisa ter `ERP_ANTHROPIC_API_KEY`. Textos da empresa vão ao modelo como *dados* (não instruções), a saída é validada por schema e saneada, e falha do provedor cai para o provedor local.
- Auditoria append-only (`/auditoria`, admin) com antes/depois, usuário e IP.

### Limitações conhecidas / antes de abrir a terceiros em produção

- O limitador de tentativas é **em memória** (por processo). Com várias instâncias, use também o limitador do proxy/WAF ou troque por Redis.
- Token JWT fica em `sessionStorage` (mitigado pela CSP estrita). Não há 2FA, recuperação de senha por e-mail nem convite por e-mail: o admin define/redefine senhas. Se for relevante, são os próximos passos naturais.
- Defina `ERP_PERMITIR_CADASTRO_PUBLICO=false` em implantações fechadas.
- Backups e retenção de dados (LGPD) são responsabilidade de quem opera a implantação.
- **Validação feita:** 46 testes automatizados (SQLite) + percurso completo no navegador. **Não validado aqui:** execução contra PostgreSQL real e chamadas reais à API da Anthropic (o provedor Claude foi testado com resposta simulada; confirme com sua chave).

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

"""Arranjo recomendado: gera CANDIDATOS de forma determinística, avalia cada um com o motor modular e devolve os melhores.

Dimensões do candidato (espaço finito e pequeno): nº de pessoas da equipe, nº de lotes, regra de prioridade e meio de
movimentação. Máquinas da mesma função formam um pool (vale a que termina primeiro). Cada candidato é CALCULADO pelo
sistema (tempo padrão pelos módulos, agenda com recursos limitados); a IA pode apenas sugerir alternativas dentro do espaço e
explicar. Nada de tempo vem de IA nem de digitação.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from .. import plano as pl
from ..plano import Base
from .agenda import REGRAS, Alocada, Opcao, Tarefa, escalonar
from .dependencias import dependencias

LOTES_CANDIDATOS = (1, 2, 4)
MAX_EQUIPE = 8


@dataclass(frozen=True)
class Config:
    pessoas: int
    lotes: int
    regra: str
    meio_id: int | None = None
    origem: str = "sistema"  # sistema | ia

    @property
    def id(self) -> str:
        return f"p{self.pessoas}-l{self.lotes}-{self.regra}-m{self.meio_id or 0}"

    def como_dict(self) -> dict:
        return {"id": self.id, "pessoas": self.pessoas, "lotes": self.lotes, "regra": self.regra, "meio_id": self.meio_id, "origem": self.origem}


@dataclass
class Resultado:
    config: Config
    alocadas: list[Alocada]
    metricas: dict
    meio_nome: str | None = None
    linhas_por_tarefa: dict[int, dict] = field(default_factory=dict)


def _tamanhos(n: float, lotes: int) -> list[float]:
    """Divide N unidades em `lotes` partes inteiras o mais iguais possível (N fracionário só admite 1 lote)."""
    if lotes == 1 or n != int(n):
        return [n]
    n = int(n)
    return [float(n // lotes + (1 if i < n % lotes else 0)) for i in range(lotes)]


class Avaliador:
    def __init__(self, base: Base, proposta, quantidade: float):
        self.base, self.proposta, self.quantidade = base, proposta, quantidade
        self.passos = proposta.passos
        self.deps = dependencias(self.passos)
        self._cache: dict[tuple, list[list[Opcao]]] = {}
        self.pendencias: list[str] = []
        ativos = [r for r in base.recursos if r.ativo]
        self.maquinas = {f: [r for r in ativos if r.funcao == f] for f in ("corte", "bordo", "furacao")}
        self.meios = [r for r in ativos if r.funcao == "movimentacao"]
        self.meios_completos = [r for r in self.meios if base.fichas.get(r.id, {}).get("velocidade_meio_m_min")
                                and base.fichas.get(r.id, {}).get("capacidade_carga_kg")]

    # -------------------------------------------------------------- opções por passo (módulo calculado pelo sistema)
    def opcoes(self, qtd: float, meio) -> list[list[Opcao]]:
        chave = (qtd, meio.id if meio is not None else None)
        if chave in self._cache:
            return self._cache[chave]
        saida = []
        for p in self.passos:
            modulo_chave = p.modulo
            candidatos = [None]
            if modulo_chave in self.maquinas:
                pool = list(self.maquinas[modulo_chave])
                nomeado = self.base.rec_nome.get((p.recurso or "").lower())
                if nomeado is not None and nomeado not in pool:
                    pool.append(nomeado)
                candidatos = pool or [None]
            elif modulo_chave == "movimentacao":
                candidatos = [meio]
            ops = []
            ultima = None
            for rec in candidatos:
                l = pl.calcular_linha(self.base, p, qtd, recurso=rec, pessoas_cfg=1, fixar_recurso=modulo_chave == "movimentacao")
                ultima = l
                if l["total"] is not None:
                    ops.append(Opcao(rec.id if (rec is not None and modulo_chave in (*self.maquinas, "movimentacao")) else None, l["total"], l))
            if not ops and ultima is not None:
                ops = [Opcao(None, math.inf, ultima)]  # incompleto: guarda a linha para as pendências
            saida.append(ops)
        self._cache[chave] = saida
        return saida

    def incompletos(self, qtd: float, meio) -> list[str]:
        return [f"{p.nome}: {f}" for p, ops in zip(self.passos, self.opcoes(qtd, meio)) if all(o.dur == math.inf for o in ops)
                for f in ops[0].linha["falt"]]

    def equipe_minima(self, qtd: float, meio) -> int:
        return max((min(o.linha["pessoas"] for o in ops) for ops in self.opcoes(qtd, meio) if ops), default=1)

    # -------------------------------------------------------------- avaliação de um candidato
    def avaliar(self, cfg: Config) -> Resultado | None:
        meio = next((m for m in self.meios_completos if m.id == cfg.meio_id), None)
        tamanhos = _tamanhos(self.quantidade, cfg.lotes)
        tarefas: list[Tarefa] = []
        ids: dict[tuple[int, int], int] = {}
        for lote, q in enumerate(tamanhos):
            ops_passos = self.opcoes(q, meio)
            for i, p in enumerate(self.passos):
                ops = [o for o in ops_passos[i] if o.dur != math.inf]
                if not ops:
                    return None
                t = Tarefa(len(tarefas), i, lote, p.nome + (f" (lote {lote + 1}/{len(tamanhos)})" if len(tamanhos) > 1 else ""),
                           min(o.linha["pessoas"] for o in ops), ops, [ids[(lote, j)] for j in sorted(self.deps[i])])
                ids[(lote, i)] = t.id
                tarefas.append(t)
        alocadas = escalonar(tarefas, cfg.pessoas, cfg.regra)
        if alocadas is None:
            return None
        return Resultado(cfg, alocadas, self._metricas(cfg, alocadas), meio.nome if meio else None)

    def _metricas(self, cfg: Config, aloc: list[Alocada]) -> dict:
        makespan = max(a.fim for a in aloc)
        trab = sum((a.fim - a.ini) * a.tarefa.pessoas for a in aloc)
        por_maquina: dict[int, float] = {}
        for a in aloc:
            if a.opcao.recurso_id is not None:
                por_maquina[a.opcao.recurso_id] = por_maquina.get(a.opcao.recurso_id, 0.0) + (a.fim - a.ini)
        nomes = {r.id: r.nome for r in self.base.recursos}
        ocup = {"Equipe": round(trab / (cfg.pessoas * makespan) * 100, 1) if makespan else 0.0}
        ocup.update({nomes[r]: round(m / makespan * 100, 1) for r, m in sorted(por_maquina.items()) if makespan})
        gargalo = max(ocup.items(), key=lambda kv: (kv[1], kv[0] == "Equipe"))
        alertas = {x["msg"] for a in aloc for x in a.opcao.linha["alertas"] if x["categoria"] == "seguranca"}
        pesos = [a.opcao.linha["peso_por_pessoa"] for a in aloc if a.opcao.linha["peso_por_pessoa"]]
        return {"makespan_min": round(makespan, 2), "tempo_padrao_min": round(sum(a.fim - a.ini for a in aloc), 2),
                "pessoas_hora": round(trab / 60, 2), "ocupacao_pct": ocup, "gargalo": {"recurso": gargalo[0], "ocupacao_pct": gargalo[1]},
                "ergonomia": {"alertas_seguranca": len(alertas), "peso_max_por_pessoa_kg": round(max(pesos), 2) if pesos else None}}

    # -------------------------------------------------------------- espaço de candidatos
    def configs(self, pessoas_max: int, extras: list[Config] | None = None) -> list[Config]:
        n = self.quantidade
        meios = [m.id for m in self.meios_completos] or [None]  # sem meio cadastrado completo: a pé (premissa declarada)
        lotes = [1] + [l for l in LOTES_CANDIDATOS if l > 1 and n == int(n) and l <= int(n)]
        pmax = max(1, min(pessoas_max, MAX_EQUIPE))
        saida = [Config(p, l, r, m) for m in meios for l in lotes for r in REGRAS for p in range(1, pmax + 1)]
        for c in extras or []:
            if c not in saida and c.lotes in lotes and 1 <= c.pessoas <= MAX_EQUIPE and c.regra in REGRAS and (c.meio_id in meios):
                saida.append(c)
        return saida

    def pendencias_gerais(self) -> list[str]:
        pend = []
        if self.meios and not self.meios_completos:
            pend.append("Há meio(s) de movimentação cadastrado(s) sem ficha técnica validada (velocidade e capacidade de carga): "
                        "o transporte foi calculado a pé. Complete a ficha para o plano usá-los.")
        elif not self.meios:
            pend.append("Nenhum meio de movimentação cadastrado: o transporte foi calculado com pessoas carregando (referência genérica).")
        return pend


def dominado(a: Resultado, outros: list[Resultado]) -> bool:
    def v(r):
        return (r.metricas["makespan_min"], r.metricas["pessoas_hora"], r.metricas["ergonomia"]["alertas_seguranca"], r.config.pessoas)
    va = v(a)
    return any(all(x <= y for x, y in zip(v(o), va)) and v(o) != va for o in outros)


def melhores(resultados: list[Resultado], n: int) -> list[Resultado]:
    """Frente de Pareto (prazo, pessoas-hora, alertas de segurança, tamanho da equipe), em ordem estável: prazo, pessoas-hora, alertas, equipe, id."""
    frente = [r for r in resultados if not dominado(r, resultados)]
    unicos: dict[tuple, Resultado] = {}
    for r in sorted(frente, key=lambda r: r.config.id):  # empates idênticos: fica o de menor id
        m = r.metricas
        unicos.setdefault((m["makespan_min"], m["pessoas_hora"], m["ergonomia"]["alertas_seguranca"], r.config.pessoas), r)
    ordem = sorted(unicos.values(), key=lambda r: (r.metricas["makespan_min"], r.metricas["pessoas_hora"],
                                                   r.metricas["ergonomia"]["alertas_seguranca"], r.config.pessoas, r.config.id))
    return ordem[:n]


def cronograma(base: Base, res: Resultado, inicio_local: datetime) -> list[dict]:
    uteis = base.cfg.get("so_dias_uteis", True)
    out = []
    for a in res.alocadas:
        ini = pl._inicio_util(pl.instante_apos(inicio_local, base.blocos, uteis, a.ini), base.blocos, uteis)
        fim = pl.instante_apos(inicio_local, base.blocos, uteis, a.fim)
        nomes = {r.id: r.nome for r in base.recursos}
        out.append({"tarefa": a.tarefa.nome, "modulo": a.tarefa.opcoes[0].linha["modulo"].chave, "lote": a.tarefa.lote + 1, "pessoas": a.tarefa.pessoas,
                    "recurso": nomes.get(a.opcao.recurso_id), "inicio_min": round(a.ini, 2), "fim_min": round(a.fim, 2),
                    "duracao_min": round(a.fim - a.ini, 2), "inicio": ini.isoformat(), "fim": fim.isoformat()})
    return out

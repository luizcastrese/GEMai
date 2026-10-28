"""Escalonamento com RECURSOS LIMITADOS: equipe (nº de pessoas), máquinas (uma tarefa por vez) e dependências.

Algoritmo determinístico de lista: a cada passo, entre as tarefas prontas escolhe-se a que pode começar primeiro (empate pela
regra de prioridade) e ela é colocada no primeiro instante em que há `pessoas` livres e (se usa máquina) a máquina livre.
Quando há várias máquinas da mesma função, vale a que termina primeiro (desempate pelo id). Tempos em minutos de TRABALHO
(a jornada/calendário é aplicada depois). Nenhuma duração é inventada: vêm dos módulos de tempo.
"""
from __future__ import annotations

from dataclasses import dataclass, field

REGRAS = ("plano", "critico")


@dataclass
class Opcao:
    recurso_id: int | None  # máquina escolhida (None = sem máquina)
    dur: float  # minutos de trabalho (padrão: preparação + execução, com tolerâncias)
    linha: dict  # linha calculada pelo módulo (para persistir o passo)


@dataclass
class Tarefa:
    id: int
    passo: int
    lote: int
    nome: str
    pessoas: int
    opcoes: list[Opcao]
    preds: list[int] = field(default_factory=list)


@dataclass
class Alocada:
    tarefa: Tarefa
    ini: float
    fim: float
    opcao: Opcao
    equipe: list[int]


def _ranks(tarefas: list[Tarefa]) -> dict[int, float]:
    """Caminho crítico restante (duração mínima da tarefa + o maior caminho dos sucessores)."""
    sucessores: dict[int, list[int]] = {t.id: [] for t in tarefas}
    for t in tarefas:
        for p in t.preds:
            sucessores[p].append(t.id)
    por_id = {t.id: t for t in tarefas}
    rank: dict[int, float] = {}
    for t in sorted(tarefas, key=lambda t: -t.id):  # ids crescem na ordem topológica
        rank[t.id] = min(o.dur for o in t.opcoes) + max((rank[s] for s in sucessores[t.id]), default=0.0)
    return rank


def escalonar(tarefas: list[Tarefa], equipe: int, regra: str) -> list[Alocada] | None:
    """None se alguma tarefa precisa de mais pessoas que a equipe. Resultado ordenado por início."""
    if any(t.pessoas > equipe for t in tarefas):
        return None
    rank = _ranks(tarefas) if regra == "critico" else {}
    livre_pessoa = [0.0] * equipe
    livre_maq: dict[int, float] = {}
    feitas: dict[int, Alocada] = {}
    pendentes = list(tarefas)
    def colocar(t: Tarefa):
        """Melhor (fim, máquina) para a tarefa agora: devolve (chave, ini, opção, pessoas escolhidas)."""
        pronto_em = max((feitas[p].fim for p in t.preds), default=0.0)
        escolhidos = sorted(range(equipe), key=lambda i: (livre_pessoa[i], i))[:t.pessoas]
        t_pessoas = max(livre_pessoa[i] for i in escolhidos)
        melhor = None
        for o in t.opcoes:
            ini = max(pronto_em, t_pessoas, livre_maq.get(o.recurso_id, 0.0) if o.recurso_id is not None else 0.0)
            chave = (ini + o.dur, o.recurso_id if o.recurso_id is not None else -1)
            if melhor is None or chave < melhor[0]:
                melhor = (chave, ini, o, escolhidos)
        return melhor

    while pendentes:
        # entre as prontas, quem pode COMEÇAR primeiro; empate pela regra de prioridade (determinístico)
        prontas = [(t, colocar(t)) for t in pendentes if all(p in feitas for p in t.preds)]
        prio = (lambda x: (-rank.get(x.id, 0.0), x.lote, x.passo, x.id)) if regra == "critico" else (lambda x: (x.lote, x.passo, x.id))
        t, (_, ini, o, escolhidos) = min(prontas, key=lambda tc: (tc[1][1], prio(tc[0])))
        fim = ini + o.dur
        for i in escolhidos:
            livre_pessoa[i] = fim
        if o.recurso_id is not None:
            livre_maq[o.recurso_id] = fim
        feitas[t.id] = Alocada(t, ini, fim, o, escolhidos)
        pendentes.remove(t)
    return sorted(feitas.values(), key=lambda a: (a.ini, a.tarefa.lote, a.tarefa.passo, a.tarefa.id))

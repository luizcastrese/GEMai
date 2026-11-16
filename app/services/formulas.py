"""Fórmulas das peças: ligam as medidas do pedido (largura, altura, tipo…) às medidas e quantidades das peças.

Interpretador PRÓPRIO e fechado: não usa eval/exec. Só entende o que está listado aqui, tem limites de tamanho e profundidade,
e todo erro vira `FormulaErro` com uma mensagem em português para quem digitou.

    ={Altura}                      comprimento da lateral = altura do pedido
    ={Largura} - 0.036             duas laterais de 18 mm descontadas
    =se({Tipo} == "2 portas"; 2; 1)
    =teto({Largura} * 10)          parafusos proporcionais ao tamanho

Regras: decimal com PONTO; argumentos separados por PONTO E VÍRGULA (a vírgula é recusada para não ler "max(1,2)" como 1,2);
campos entre chaves, sem diferenciar maiúsculas; textos entre aspas duplas. Operadores: + - * / e comparações == != < <= > >=.
Funções: se(cond; a; b), min, max, abs, arred(x[; casas]), teto(x), piso(x).
Campos em cm/mm/m chegam à fórmula JÁ EM METROS (as peças são medidas em metros); os demais chegam como foram digitados.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

# Campos de uma peça que podem ter fórmula (e os limites que o resultado precisa respeitar: mínimo, máximo, estrito, inteiro).
CAMPOS_FORMULA = {
    "quantidade": (0.0, 100000.0, True, False), "comprimento_m": (0.0, 100.0, True, False), "largura_m": (0.0, 100.0, True, False),
    "espessura_m": (0.0, 10.0, True, False), "peso_kg": (0.0, 100000.0, False, False), "furos": (0.0, 10000.0, False, True),
    "bordas_m": (0.0, 1000.0, False, False)}
LIMITES = {**CAMPOS_FORMULA, "fixadores": (0.0, 10000.0, False, True)}  # + fixadores de uma ligação
MAX_TEXTO = 200
MAX_NOS = 80
MAX_PROFUNDIDADE = 12
LIMITE = 1e9


class FormulaErro(ValueError):
    pass


class FaltaValor(FormulaErro):
    """A fórmula usa um campo do pedido que não tem valor."""

    def __init__(self, campo: str):
        super().__init__(f"Falta informar «{campo}», que a fórmula usa.")
        self.campo = campo


# ---------------------------------------------------------------- análise léxica
_TOKEN = re.compile(r"""\s*(?:(?P<num>\d+(?:\.\d+)?)|(?P<str>"[^"]*")|(?P<var>\{[^{}]+\})|(?P<id>[A-Za-z_][A-Za-z_0-9]*)"""
                    r"""|(?P<op>==|!=|<=|>=|[-+*/()<>;]))""")


@dataclass
class _Tok:
    tipo: str
    valor: str


def _tokens(texto: str) -> list[_Tok]:
    if len(texto) > MAX_TEXTO:
        raise FormulaErro(f"Fórmula longa demais (máximo {MAX_TEXTO} caracteres).")
    out, i = [], 0
    while i < len(texto):
        if texto[i:].strip() == "":
            break
        m = _TOKEN.match(texto, i)
        if not m or m.end() == i:
            if texto[i:].lstrip().startswith(","):
                raise FormulaErro("Use ponto nos decimais (0.036) e ponto e vírgula entre argumentos: min(1; 2).")
            trecho = texto[i:].strip()[:12]
            raise FormulaErro(f"Não entendi «{trecho}». Escreva campos entre chaves, ex.: {{Altura}}.")
        tipo = m.lastgroup
        out.append(_Tok(tipo, m.group(tipo)))
        i = m.end()
    return out


# ---------------------------------------------------------------- árvore
# nós: ("num", x) ("str", s) ("var", nome) ("neg", n) ("bin", op, a, b) ("fn", nome, [args])
_FUNCOES = {"se": (3, 3), "min": (2, 20), "max": (2, 20), "abs": (1, 1), "arred": (1, 2), "teto": (1, 1), "piso": (1, 1)}


class _Parser:
    def __init__(self, toks: list[_Tok]):
        self.t, self.i, self.nos = toks, 0, 0

    def _no(self, *n):
        self.nos += 1
        if self.nos > MAX_NOS:
            raise FormulaErro("Fórmula complicada demais. Simplifique.")
        return n

    def _ver(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def _come(self, valor=None):
        tok = self._ver()
        if tok is None or (valor is not None and tok.valor != valor):
            raise FormulaErro(f"Fórmula incompleta: esperava «{valor}»." if valor else "Fórmula incompleta.")
        self.i += 1
        return tok

    def analisa(self):
        if not self.t:
            raise FormulaErro("Fórmula vazia.")
        no = self._cmp(0)
        if self._ver() is not None:
            raise FormulaErro(f"Sobrou «{self._ver().valor}» no fim da fórmula.")
        return no

    def _cmp(self, d):
        a = self._soma(d)
        tok = self._ver()
        if tok and tok.tipo == "op" and tok.valor in ("==", "!=", "<=", ">=", "<", ">"):
            self.i += 1
            return self._no("bin", tok.valor, a, self._soma(d))
        return a

    def _soma(self, d):
        a = self._mult(d)
        while (tok := self._ver()) and tok.tipo == "op" and tok.valor in "+-" and len(tok.valor) == 1:
            self.i += 1
            a = self._no("bin", tok.valor, a, self._mult(d))
        return a

    def _mult(self, d):
        a = self._unario(d)
        while (tok := self._ver()) and tok.tipo == "op" and tok.valor in ("*", "/"):
            self.i += 1
            a = self._no("bin", tok.valor, a, self._unario(d))
        return a

    def _unario(self, d):
        if d > MAX_PROFUNDIDADE:
            raise FormulaErro("Parênteses demais. Simplifique.")
        tok = self._ver()
        if tok and tok.tipo == "op" and tok.valor == "-":
            self.i += 1
            return self._no("neg", self._unario(d + 1))
        return self._primario(d)

    def _primario(self, d):
        tok = self._come()
        if tok.tipo == "num":
            return self._no("num", float(tok.valor))
        if tok.tipo == "str":
            return self._no("str", tok.valor[1:-1])
        if tok.tipo == "var":
            nome = tok.valor[1:-1].strip()
            if not nome:
                raise FormulaErro("Campo vazio entre chaves.")
            return self._no("var", nome)
        if tok.tipo == "id":
            nome = tok.valor.casefold()
            if nome not in _FUNCOES:
                raise FormulaErro(f"Função desconhecida: «{tok.valor}». Disponíveis: {', '.join(sorted(_FUNCOES))}.")
            self._come("(")
            args = [self._cmp(d + 1)]
            while (t := self._ver()) and t.valor == ";":
                self.i += 1
                args.append(self._cmp(d + 1))
            self._come(")")
            lo, hi = _FUNCOES[nome]
            if not lo <= len(args) <= hi:
                esperado = str(lo) if lo == hi else f"{lo} a {hi}"
                raise FormulaErro(f"«{nome}» recebe {esperado} valor(es), mas vieram {len(args)}.")
            return self._no("fn", nome, args)
        if tok.valor == "(":
            no = self._cmp(d + 1)
            self._come(")")
            return no
        raise FormulaErro(f"Não esperava «{tok.valor}» aqui.")


def compilar(texto: str):
    return _Parser(_tokens(texto or "")).analisa()


def campos_usados(no) -> set[str]:
    """Nomes (em minúsculas) dos campos do pedido que a fórmula usa."""
    if no[0] == "var":
        return {no[1].casefold()}
    if no[0] == "neg":
        return campos_usados(no[1])
    if no[0] == "bin":
        return campos_usados(no[2]) | campos_usados(no[3])
    if no[0] == "fn":
        return set().union(*(campos_usados(a) for a in no[2]))
    return set()


# ---------------------------------------------------------------- avaliação
def _num(v, o):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise FormulaErro(f"«{o}» precisa de números, mas recebeu texto ou verdadeiro/falso.")
    return float(v)


def _fim(x: float) -> float:
    if not math.isfinite(x) or abs(x) > LIMITE:
        raise FormulaErro("O resultado saiu do limite aceito.")
    return x


def _aval(no, vals: dict):
    t = no[0]
    if t in ("num", "str"):
        return no[1]
    if t == "var":
        chave = no[1].casefold()
        if chave not in vals:
            raise FaltaValor(no[1])
        return vals[chave]
    if t == "neg":
        return -_num(_aval(no[1], vals), "-")
    if t == "bin":
        op, a, b = no[1], _aval(no[2], vals), _aval(no[3], vals)
        if op in ("==", "!="):
            if isinstance(a, str) != isinstance(b, str):
                raise FormulaErro("Não dá para comparar texto com número.")
            igual = a.casefold() == b.casefold() if isinstance(a, str) else a == b
            return igual if op == "==" else not igual
        a, b = _num(a, op), _num(b, op)
        if op in ("<", "<=", ">", ">="):
            return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
        if op == "/" and b == 0:
            raise FormulaErro("Divisão por zero.")
        return _fim({"+": a + b, "-": a - b, "*": a * b, "/": a / b if b else 0.0}[op])
    nome, args = no[1], no[2]
    if nome == "se":
        c = _aval(args[0], vals)
        if not isinstance(c, bool):
            raise FormulaErro("O primeiro valor de «se» precisa ser uma comparação, ex.: {Largura} > 0.6.")
        return _aval(args[1] if c else args[2], vals)  # só avalia o ramo escolhido
    v = [_num(_aval(a, vals), nome) for a in args]
    if nome == "min":
        return min(v)
    if nome == "max":
        return max(v)
    if nome == "abs":
        return abs(v[0])
    if nome == "teto":
        return float(math.ceil(v[0] - 1e-9))
    if nome == "piso":
        return float(math.floor(v[0] + 1e-9))
    casas = int(v[1]) if len(v) > 1 else 0
    if not 0 <= casas <= 6:
        raise FormulaErro("«arred» aceita de 0 a 6 casas decimais.")
    return round(v[0] + (1e-12 if v[0] >= 0 else -1e-12), casas)


def avaliar(no, valores: dict) -> float:
    """Resultado numérico. `valores`: nome do campo em minúsculas → número ou texto."""
    r = _aval(no, {k.casefold(): v for k, v in valores.items()})
    if isinstance(r, bool) or not isinstance(r, (int, float)):
        raise FormulaErro("A fórmula precisa resultar em um número.")
    return _fim(float(r))

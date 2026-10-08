"""Limitador simples em memória (janela deslizante) para rotas sensíveis.

Em implantações com vários processos/instâncias, substitua por um limitador
compartilhado (ex.: Redis ou o proxy reverso). Veja README.
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, maximo: int, janela_s: int):
        self.maximo, self.janela = maximo, janela_s
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def checar(self, chave: str) -> None:
        agora = time.monotonic()
        with self._lock:
            q = self._hits[chave]
            while q and agora - q[0] > self.janela:
                q.popleft()
            if len(q) >= self.maximo:
                raise HTTPException(429, "Muitas tentativas. Aguarde alguns instantes.",
                                    headers={"Retry-After": str(self.janela)})
            q.append(agora)
            if len(self._hits) > 10_000:  # evita crescimento ilimitado
                for k in [k for k, v in self._hits.items() if not v]:
                    self._hits.pop(k, None)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def ip_cliente(request: Request) -> str:
    return request.client.host if request.client else "desconhecido"


limite_login = RateLimiter(maximo=20, janela_s=60)
limite_cadastro = RateLimiter(maximo=5, janela_s=3600)
limite_ia = RateLimiter(maximo=30, janela_s=3600)

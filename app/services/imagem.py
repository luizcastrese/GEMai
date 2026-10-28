"""Foto opcional de um meio: validação e remoção de metadados (EXIF/GPS) ANTES de qualquer uso.

Só JPEG e PNG, com limite de tamanho. A foto fica só em memória: é enviada à IA para identificar o equipamento e
descartada (nada é gravado em disco/banco nem registrado em log ou auditoria).
"""
from __future__ import annotations

import base64
import binascii
import struct

PNG_ASSINATURA = b"\x89PNG\r\n\x1a\n"
PNG_DESCARTAR = {b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"tIME"}  # metadados (texto, EXIF, data)


class FotoInvalida(ValueError):
    pass


def _jpeg(dados: bytes) -> bytes:
    """Mantém SOI, quantização, quadros e dados de imagem; remove APP1–APP15 (EXIF, XMP, ICC…) e comentários."""
    if dados[:2] != b"\xff\xd8":
        raise FotoInvalida("JPEG inválido")
    out, i, n = bytearray(b"\xff\xd8"), 2, len(dados)
    while i < n:
        if dados[i] != 0xFF:
            raise FotoInvalida("JPEG corrompido")
        while i < n and dados[i] == 0xFF:
            i += 1
        if i >= n:
            raise FotoInvalida("JPEG corrompido")
        marcador = dados[i]
        i += 1
        if marcador == 0xD9:  # EOI
            out += b"\xff\xd9"
            return bytes(out)
        if marcador == 0x01 or 0xD0 <= marcador <= 0xD7:  # sem tamanho
            out += bytes([0xFF, marcador])
            continue
        if i + 2 > n:
            raise FotoInvalida("JPEG corrompido")
        (tam,) = struct.unpack(">H", dados[i:i + 2])
        if tam < 2 or i + tam > n:
            raise FotoInvalida("JPEG corrompido")
        segmento = dados[i:i + tam]
        i += tam
        if 0xE1 <= marcador <= 0xEF or marcador == 0xFE:  # APP1..APP15 e COM
            continue
        out += bytes([0xFF, marcador]) + segmento
        if marcador == 0xDA:  # SOS: o resto são dados de imagem até o EOI
            out += dados[i:]
            return bytes(out)
    raise FotoInvalida("JPEG sem fim")


def _png(dados: bytes) -> bytes:
    if dados[:8] != PNG_ASSINATURA:
        raise FotoInvalida("PNG inválido")
    out, i, n = bytearray(PNG_ASSINATURA), 8, len(dados)
    while i + 8 <= n:
        (tam,) = struct.unpack(">I", dados[i:i + 4])
        tipo = dados[i + 4:i + 8]
        fim = i + 12 + tam
        if fim > n:
            raise FotoInvalida("PNG corrompido")
        if tipo not in PNG_DESCARTAR:
            out += dados[i:fim]
        i = fim
        if tipo == b"IEND":
            return bytes(out)
    raise FotoInvalida("PNG sem IEND")


def sanitizar(base64_str: str, max_bytes: int) -> tuple[bytes, str]:
    """(bytes sem metadados, media_type). Levanta FotoInvalida para tamanho, tipo ou estrutura inválidos."""
    if len(base64_str) > max_bytes * 4 // 3 + 16:
        raise FotoInvalida("foto grande demais")
    try:
        dados = base64.b64decode(base64_str, validate=True)
    except (binascii.Error, ValueError):
        raise FotoInvalida("base64 inválido")
    if not dados or len(dados) > max_bytes:
        raise FotoInvalida("foto vazia ou grande demais")
    if dados[:3] == b"\xff\xd8\xff":
        return _jpeg(dados), "image/jpeg"
    if dados[:8] == PNG_ASSINATURA:
        return _png(dados), "image/png"
    raise FotoInvalida("só JPEG e PNG são aceitos")

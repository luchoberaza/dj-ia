"""Tonalidad: compatibilidad armónica por rueda Camelot.

Dos temas al mismo BPM en tonalidades incompatibles suenan a choque. Sin esto, el
motor produce transiciones que técnicamente encajan y suenan mal.

Notación: 1-12 más A (menor) o B (mayor). 24 posiciones.
"""

from __future__ import annotations

import re

#: Debajo de esta confianza el término tonal se neutraliza en vez de castigar: no se
#: penaliza por un dato que no se conoce, porque eso sería inventar.
UMBRAL_CONFIANZA = 0.5

_PATRON = re.compile(r"^(?P<numero>[1-9]|1[0-2])(?P<letra>[AB])$")

# Costos por tipo de movimiento en la rueda.
MISMO = 0.0  # 100% compatible
VECINO = 0.15  # ±1 misma letra: el movimiento estándar
RELATIVA = 0.20  # A↔B mismo número: cambia el color emocional sin romper
SUBIDON = 0.35  # +2 misma letra: salto de energía deliberado
CHOQUE = 0.90  # todo lo demás


def parsear(codigo: str | None) -> tuple[int, str] | None:
    """`"8A"` → `(8, "A")`. Devuelve None si el código no es válido."""
    if not codigo:
        return None
    coincidencia = _PATRON.match(codigo.strip().upper())
    if coincidencia is None:
        return None
    return int(coincidencia.group("numero")), coincidencia.group("letra")


def _distancia_rueda(numero_a: int, numero_b: int) -> int:
    """Pasos con signo entre dos posiciones de la rueda, en el rango -6..5."""
    bruta = (numero_b - numero_a) % 12
    return bruta - 12 if bruta > 5 else bruta


def compatibilidad(camelot_a: str, camelot_b: str) -> float:
    """Costo armónico de pasar de una tonalidad a otra. 0 = perfecto."""
    a = parsear(camelot_a)
    b = parsear(camelot_b)
    if a is None or b is None:
        return 0.0

    numero_a, letra_a = a
    numero_b, letra_b = b
    pasos = _distancia_rueda(numero_a, numero_b)

    if letra_a == letra_b:
        if pasos == 0:
            return MISMO
        if abs(pasos) == 1:
            return VECINO
        if pasos == 2:
            return SUBIDON
        return CHOQUE

    if pasos == 0:
        return RELATIVA
    return CHOQUE


def costo_tonal(
    camelot_a: str | None,
    camelot_b: str | None,
    confianza_a: float = 1.0,
    confianza_b: float = 1.0,
) -> tuple[float, bool]:
    """Costo tonal de la transición.

    Devuelve ``(costo, neutralizado)``. Se neutraliza —costo cero— si falta alguna
    tonalidad o si alguna confianza está por debajo del umbral.
    """
    if camelot_a is None or camelot_b is None:
        return 0.0, True
    if confianza_a < UMBRAL_CONFIANZA or confianza_b < UMBRAL_CONFIANZA:
        return 0.0, True
    if parsear(camelot_a) is None or parsear(camelot_b) is None:
        return 0.0, True
    return compatibilidad(camelot_a, camelot_b), False


def compatibles(camelot_a: str, camelot_b: str) -> bool:
    """¿Es uno de los movimientos que un DJ haría sin pensarlo?"""
    return compatibilidad(camelot_a, camelot_b) <= RELATIVA

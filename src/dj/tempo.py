"""Tempo: distancia entre BPM, módulo octava.

El punto que rompe todo si se ignora: 90 y 180 BPM son el mismo pulso percibido. Una
cumbia a 95 y un tema a 190 encajan perfecto. Comparar BPM en valor absoluto hace que
el planificador vea un abismo donde hay una autopista.

Y el corolario feo: la mitad de los errores de detección automática de BPM son de
octava equivocada. Trabajar módulo octava también absorbe parte de ese error.
"""

from __future__ import annotations

import math

#: Límite de mezcla cómoda. Más allá de esto no es costura, es corte.
TOLERANCIA_COSTURA = 0.06

#: Diferencia transparente: nadie la nota.
LIBRE_BPM = 3.0

#: Costo que representa "esto no se puede costurar". No es infinito para que las
#: comparaciones y sumas sigan siendo números normales.
PROHIBITIVO = 1_000_000.0

#: Octavas consideradas al buscar el equivalente percibido.
_OCTAVAS = (-2, -1, 0, 1, 2)


def equivalente_octava(bpm_referencia: float, bpm: float) -> float:
    """Lleva `bpm` a la octava (×2 / ÷2) cuyo pulso se percibe más cerca de la referencia.

    >>> round(equivalente_octava(128.0, 190.0))
    95
    >>> round(equivalente_octava(96.0, 48.0))
    96
    """
    if bpm_referencia <= 0 or bpm <= 0:
        raise ValueError("los BPM tienen que ser positivos")

    mejor = bpm
    mejor_distancia = abs(math.log2(bpm / bpm_referencia))
    for k in _OCTAVAS:
        if k == 0:
            continue
        candidato = bpm * (2.0**k)
        distancia = abs(math.log2(candidato / bpm_referencia))
        if distancia < mejor_distancia:
            mejor, mejor_distancia = candidato, distancia
    return mejor


def diferencia_relativa(bpm_a: float, bpm_b: float) -> float:
    """Diferencia de tempo de B respecto de A, módulo octava.

    Positiva = B se siente más rápido. Es un porcentaje del tempo de A, no BPM
    absolutos: el rango válido a 95 BPM no es el mismo que a 140.
    """
    return (equivalente_octava(bpm_a, bpm_b) - bpm_a) / bpm_a


def costo_tempo(bpm_a: float, bpm_b: float) -> tuple[float, float, float]:
    """Costo de saltar de A a B por tempo.

    Devuelve ``(costo, diferencia_relativa, bpm_equivalente)``.

    Cero hasta ±3 BPM, sube cuadráticamente hasta el 6%, y a partir del 6% devuelve
    PROHIBITIVO — que significa "no se puede costurar", no "no se puede tocar". El
    motor no descarta el tema: le cambia el tipo de transición a corte.
    """
    equivalente = equivalente_octava(bpm_a, bpm_b)
    relativa = (equivalente - bpm_a) / bpm_a
    distancia = abs(relativa)

    libre = LIBRE_BPM / bpm_a
    if distancia <= libre:
        return 0.0, relativa, equivalente
    if distancia >= TOLERANCIA_COSTURA or libre >= TOLERANCIA_COSTURA:
        return PROHIBITIVO, relativa, equivalente

    t = (distancia - libre) / (TOLERANCIA_COSTURA - libre)
    return t * t, relativa, equivalente


def costurable_por_tempo(bpm_a: float, bpm_b: float) -> bool:
    """¿La diferencia de tempo permite una costura, o hay que cortar?"""
    return abs(diferencia_relativa(bpm_a, bpm_b)) < TOLERANCIA_COSTURA

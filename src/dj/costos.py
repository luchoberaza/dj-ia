"""Costo de una transición y elección del tipo de transición.

Dos preguntas distintas que no hay que mezclar:

    puntaje(B) = deseabilidad(B) − costo_transicion(A → B)
                 ¿qué tan bueno       ¿cuánto cuesta llegar
                  es este tema         hasta él desde lo que
                  ahora mismo?         está sonando?

Este módulo resuelve la segunda. La primera vive en `deseabilidad.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from .dominio import Desglose, GrafoGeneros, Pista, TipoTransicion
from .tempo import PROHIBITIVO, costo_tempo, equivalente_octava
from .tonalidad import RELATIVA, costo_tonal

#: Debajo de esta diferencia relativa la costura puede ser larga y tranquila.
UMBRAL_COSTURA_LARGA = 0.03

#: Cortar porque una de las dos pistas no es costurable no es un error de programación:
#: es la naturaleza del material. Se penaliza poco.
PENAL_CORTE_INEVITABLE = 0.25

#: Cortar porque el salto de tempo es grande sí es una decisión, y se paga más caro.
PENAL_CORTE_POR_SALTO = 0.55

#: Un corte con puente marca cambio de bloque. Es un recurso legítimo, no una falla.
PENAL_CORTE_PUENTE = 0.15

#: Arriba de este costo de arista, el cambio de género se trata como cambio de bloque.
UMBRAL_BLOQUE = 0.5

#: Techo del término de tempo cuando la transición ya es un corte: la distancia sigue
#: importando (no da lo mismo cortar a +8% que a +60%), pero acotada.
_ESCALA_TEMPO_EN_CORTE = 0.25

#: Cada 8% de desvío respecto del tempo objetivo suma 1.0 al costo de curva.
#:
#: Dos propiedades que se pagaron caro en pruebas: el término NO satura dentro del
#: rango útil (si saturara, un set 30% lejos del objetivo no tendría ningún incentivo
#: para acercarse y la escalera hacia lo votado nunca arrancaría), y la escala tiene
#: que ser lo bastante chica como para vencer a la inercia — con 0.15 el motor se
#: quedaba cómodo 20 BPM abajo del pico porque moverse costaba más que quedarse.
_ESCALA_CURVA = 0.08

#: Techo del costo de curva, solo para que un dato absurdo no rompa las comparaciones.
_TECHO_CURVA = 4.0


@dataclass(frozen=True, slots=True)
class Pesos:
    """Los pesos del motor.

    Arrancan curados a mano y se ajustan contra el corpus de sets reales. Nunca se
    reemplazan por un modelo opaco: un motor que no se puede explicar es invendible.

    `genero` es el peso más alto a propósito — el principio de diseño es "aburrido
    pero nunca mal, antes que brillante con riesgo de catástrofe".
    """

    tempo: float = 1.0
    tonal: float = 0.6
    genero: float = 1.2
    energia: float = 0.8
    costura: float = 0.5
    curva: float = 0.9
    deseabilidad: float = 1.0
    atractor: float = 0.9


def costo_genero(desde: Pista, hacia: Pista, grafo: GrafoGeneros) -> float | None:
    """Costo de la arista. None si no existe: ese salto no se puede hacer, nunca."""
    return grafo.costo(desde.genero, hacia.genero)


def costo_curva(bpm: float, bpm_objetivo: float) -> float:
    """Distancia al tempo objetivo de la fase.

    Sin este término la noche deriva: cada transición individual es correcta y aun así
    el set termina 20 BPM lejos de donde tenía que estar. Es el término que hace que la
    curva de la noche exista, y no solo la coherencia entre temas vecinos.
    """
    if bpm_objetivo <= 0:
        return 0.0
    equivalente = equivalente_octava(bpm_objetivo, bpm)
    desvio = abs(equivalente - bpm_objetivo) / bpm_objetivo
    return min(_TECHO_CURVA, desvio / _ESCALA_CURVA)


def costo_energia(energia: float, objetivo: float, es_build: bool) -> float:
    """Distancia a la energía objetivo de la fase, no a la del tema anterior.

    Asimétrico: durante el build, bajar la energía cuesta mucho más que subirla. Es el
    error clásico —subir el BPM y bajar la energía— y el motor no lo puede cometer
    sin pagarlo.
    """
    delta = energia - objetivo
    if delta >= 0:
        return 0.5 * (delta / 9.0) ** 2
    penalizacion = 2.0 if es_build else 1.0
    return penalizacion * abs(delta) / 9.0


def evaluar_transicion(
    desde: Pista | None,
    hacia: Pista,
    *,
    grafo: GrafoGeneros,
    energia_objetivo: float,
    bpm_objetivo: float = 0.0,
    es_build: bool = False,
    pesos: Pesos = Pesos(),
    deseabilidad: float = 0.0,
    ignorar_tonal: bool = False,
    ignorar_energia: bool = False,
) -> tuple[TipoTransicion, Desglose]:
    """Evalúa pasar de `desde` a `hacia`.

    Asume que `hacia` ya pasó las restricciones duras (ver `restricciones.py`): acá no
    se decide si algo está permitido, solo cuánto cuesta.

    `desde=None` es el primer tema de la noche: solo pesan la energía y la curva.
    """
    c_energia = 0.0 if ignorar_energia else costo_energia(hacia.energia, energia_objetivo, es_build)
    c_curva = costo_curva(hacia.bpm, bpm_objetivo)

    if desde is None:
        total = (
            pesos.energia * c_energia
            + pesos.curva * c_curva
            - pesos.deseabilidad * deseabilidad
        )
        return TipoTransicion.CORTE_PUENTE, Desglose(
            costo_total=total,
            tempo=0.0,
            tonal=0.0,
            genero=0.0,
            energia=c_energia,
            costura=0.0,
            deseabilidad=deseabilidad,
            diferencia_tempo_rel=0.0,
            bpm_equivalente=hacia.bpm,
            curva=c_curva,
            bpm_objetivo=bpm_objetivo,
        )

    c_tempo_bruto, relativa, equivalente = costo_tempo(desde.bpm, hacia.bpm)

    if ignorar_tonal:
        c_tonal, neutralizado = 0.0, True
    else:
        c_tonal, neutralizado = costo_tonal(
            desde.camelot, hacia.camelot, desde.camelot_confianza, hacia.camelot_confianza
        )

    arista = costo_genero(desde, hacia, grafo)
    if arista is None:
        raise ValueError(
            f"no hay arista {desde.genero!r} → {hacia.genero!r}: "
            "eso lo tiene que haber filtrado la capa de restricciones"
        )

    ambas_aptas = desde.apta_para_costura and hacia.apta_para_costura
    tempo_permite_costura = c_tempo_bruto < PROHIBITIVO
    cambia_bloque = arista >= UMBRAL_BLOQUE

    if ambas_aptas and tempo_permite_costura:
        c_tempo = c_tempo_bruto
        c_costura = 0.0
        if abs(relativa) <= UMBRAL_COSTURA_LARGA and c_tonal <= RELATIVA and not cambia_bloque:
            tipo = TipoTransicion.COSTURA_LARGA
        else:
            tipo = TipoTransicion.COSTURA_CORTA
    else:
        c_tempo = min(1.0, abs(relativa) / _ESCALA_TEMPO_EN_CORTE)
        c_costura = PENAL_CORTE_INEVITABLE if not ambas_aptas else PENAL_CORTE_POR_SALTO
        if cambia_bloque:
            tipo = TipoTransicion.CORTE_PUENTE
            c_costura += PENAL_CORTE_PUENTE
        else:
            tipo = TipoTransicion.CORTE_BREAK

    total = (
        pesos.tempo * c_tempo
        + pesos.tonal * c_tonal
        + pesos.genero * arista
        + pesos.energia * c_energia
        + pesos.costura * c_costura
        + pesos.curva * c_curva
        - pesos.deseabilidad * deseabilidad
    )

    return tipo, Desglose(
        costo_total=total,
        tempo=c_tempo,
        tonal=c_tonal,
        genero=arista,
        energia=c_energia,
        costura=c_costura,
        deseabilidad=deseabilidad,
        diferencia_tempo_rel=relativa,
        bpm_equivalente=equivalente,
        curva=c_curva,
        bpm_objetivo=bpm_objetivo,
        tonal_neutralizado=neutralizado,
    )

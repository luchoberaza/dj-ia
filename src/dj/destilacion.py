"""Destilación del corpus: convertir sets reales en las reglas del motor.

Acá es donde el gusto deja de ser mi opinión y pasa a ser una estadística. De miles de
transiciones que alguien tocó de verdad ante una pista de verdad salen, medidos:

- **el grafo de géneros**, con el costo de cada arista sacado de su frecuencia
- **la distribución real de saltos de tempo**, que confirma o refuta el ±6% del diseño
- **los movimientos de Camelot que se usan de verdad**, contra los del manual
- **la forma de la curva** de tempo y energía a lo largo de un set

Una decisión de curaduría explícita: una transición que aparece una sola vez **no** se
convierte en arista. Un DJ haciendo algo raro una noche no puede volverse una regla del
motor. El umbral es un parámetro y las aristas que descarta quedan reportadas, porque
esconder lo que se tiró sería exactamente el tipo de recorte silencioso que el diseño
prohíbe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from .corpus import Corpus, cobertura, secuencias_de_genero
from .dominio import GrafoGeneros
from .tempo import diferencia_relativa
from .tonalidad import CHOQUE, MISMO, RELATIVA, SUBIDON, VECINO, compatibilidad

#: Costo de la arista más transitada de un género, y de la que apenas pasa el umbral.
COSTO_MINIMO = 0.05
COSTO_MAXIMO = 0.90

#: Cuántas veces tiene que aparecer una transición de género para volverse arista.
MINIMO_APARICIONES = 3

#: Y qué proporción de las salidas de ese género tiene que representar. Sin esto, en un
#: género con muchísimo volumen tres apariciones siguen siendo ruido.
PROPORCION_MINIMA = 0.01

_ETIQUETAS_CAMELOT = {
    MISMO: "mismo",
    VECINO: "vecino",
    RELATIVA: "relativa",
    SUBIDON: "subidon",
    CHOQUE: "choque",
}

_DECILES = 10


@dataclass(frozen=True, slots=True)
class DistribucionSaltos:
    """La distribución empírica de saltos de tempo entre temas consecutivos.

    Es la medición que valida o refuta el número más importante del diseño: si el
    percentil 95 de los sets reales está en 4%, el ±6% es generoso; si está en 9%, el
    motor es más conservador que los DJs que dice imitar.
    """

    muestras: int
    p50: float
    p75: float
    p90: float
    p95: float
    p99: float
    maximo: float
    proporcion_bajo_3pct: float
    proporcion_bajo_6pct: float

    def veredicto_sobre_tolerancia(self, tolerancia: float = 0.06) -> str:
        if self.muestras < 100:
            return f"muestra insuficiente ({self.muestras} transiciones con tempo)"
        if self.p95 <= tolerancia * 0.7:
            return f"la tolerancia de {tolerancia:.0%} es generosa: el p95 real es {self.p95:.1%}"
        if self.p95 >= tolerancia * 1.3:
            return (
                f"la tolerancia de {tolerancia:.0%} es conservadora: "
                f"el p95 real es {self.p95:.1%}"
            )
        return f"la tolerancia de {tolerancia:.0%} coincide con el p95 real ({self.p95:.1%})"


@dataclass(frozen=True, slots=True)
class Destilado:
    grafo: GrafoGeneros
    transiciones_genero: Mapping[tuple[str, str], int]
    aristas_descartadas: Mapping[tuple[str, str], int]
    saltos_tempo: DistribucionSaltos
    movimientos_camelot: Mapping[str, int]
    curva_tempo: tuple[float, ...]
    curva_energia: tuple[float, ...]
    sets: int
    transiciones: int
    cobertura: Mapping[str, float]

    def informe(self) -> str:
        lineas = [
            f"Corpus: {self.sets} sets · {self.transiciones} transiciones",
            "Cobertura: "
            + " · ".join(f"{campo} {valor:.0%}" for campo, valor in self.cobertura.items()),
            "",
            f"Grafo destilado: {len(self.grafo.aristas)} aristas sobre "
            f"{len(self.grafo.generos())} géneros",
        ]
        if self.aristas_descartadas:
            total = sum(self.aristas_descartadas.values())
            lineas.append(
                f"  descartadas por umbral: {len(self.aristas_descartadas)} pares "
                f"({total} transiciones) — ver `aristas_descartadas`"
            )

        s = self.saltos_tempo
        lineas += [
            "",
            f"Saltos de tempo ({s.muestras} muestras):",
            f"  p50 {s.p50:.1%} · p75 {s.p75:.1%} · p90 {s.p90:.1%} · "
            f"p95 {s.p95:.1%} · p99 {s.p99:.1%} · máx {s.maximo:.1%}",
            f"  bajo 3%: {s.proporcion_bajo_3pct:.0%} · bajo 6%: {s.proporcion_bajo_6pct:.0%}",
            f"  → {s.veredicto_sobre_tolerancia()}",
        ]

        total_camelot = sum(self.movimientos_camelot.values())
        if total_camelot:
            lineas += ["", f"Movimientos de Camelot ({total_camelot} muestras):"]
            for etiqueta, conteo in sorted(
                self.movimientos_camelot.items(), key=lambda par: -par[1]
            ):
                lineas.append(f"  {etiqueta:<9} {conteo:>6}  {conteo / total_camelot:>5.0%}")

        if any(self.curva_tempo):
            lineas += [
                "",
                "Curva a lo largo del set (tempo relativo al promedio del set):",
                "  " + " ".join(f"{v:+.0%}" for v in self.curva_tempo),
            ]
        if any(self.curva_energia):
            lineas += [
                "Curva de energía (1-10):",
                "  " + " ".join(f"{v:.1f}" for v in self.curva_energia),
            ]
        return "\n".join(lineas)


def destilar(
    corpus: Corpus,
    *,
    minimo_apariciones: int = MINIMO_APARICIONES,
    proporcion_minima: float = PROPORCION_MINIMA,
) -> Destilado:
    """Convierte un corpus de sets reales en las reglas que usa el motor."""
    aceptadas, descartadas, conteos = _destilar_grafo(
        corpus, minimo_apariciones, proporcion_minima
    )
    return Destilado(
        grafo=GrafoGeneros(aceptadas),
        transiciones_genero=conteos,
        aristas_descartadas=descartadas,
        saltos_tempo=_destilar_saltos(corpus),
        movimientos_camelot=_destilar_camelot(corpus),
        curva_tempo=_destilar_curva(corpus, "bpm", normalizar=True),
        curva_energia=_destilar_curva(corpus, "energia", normalizar=False),
        sets=len(corpus),
        transiciones=corpus.total_transiciones,
        cobertura={
            campo: cobertura(corpus, campo) for campo in ("genero", "bpm", "camelot", "energia")
        },
    )


# ------------------------------------------------------------------- grafo de géneros


def _destilar_grafo(
    corpus: Corpus, minimo_apariciones: int, proporcion_minima: float
) -> tuple[dict[tuple[str, str], float], dict[tuple[str, str], int], dict[tuple[str, str], int]]:
    conteos: dict[tuple[str, str], int] = {}
    salidas: dict[str, int] = {}

    for generos in secuencias_de_genero(corpus):
        for desde, hacia in zip(generos, generos[1:]):
            if desde == hacia:
                continue  # quedarse en el mismo género no es una arista
            conteos[(desde, hacia)] = conteos.get((desde, hacia), 0) + 1
            salidas[desde] = salidas.get(desde, 0) + 1

    maximo_desde: dict[str, int] = {}
    for (desde, _), n in conteos.items():
        maximo_desde[desde] = max(maximo_desde.get(desde, 0), n)

    aceptadas: dict[tuple[str, str], float] = {}
    descartadas: dict[tuple[str, str], int] = {}

    for (desde, hacia), n in conteos.items():
        proporcion = n / salidas[desde]
        if n < minimo_apariciones or proporcion < proporcion_minima:
            descartadas[(desde, hacia)] = n
            continue
        aceptadas[(desde, hacia)] = _costo_desde_frecuencia(n, maximo_desde[desde])

    return aceptadas, descartadas, conteos


def _costo_desde_frecuencia(conteo: int, maximo: int) -> float:
    """Cuanto más transitada la transición, más barata.

    Se usa escala logarítmica porque las frecuencias de transición tienen colas largas:
    en lineal, la arista más popular aplasta a todas las demás contra el costo máximo y
    el grafo queda con un solo camino usable.
    """
    if maximo <= 1:
        return COSTO_MINIMO
    proporcion = math.log1p(conteo) / math.log1p(maximo)
    return round(COSTO_MAXIMO - (COSTO_MAXIMO - COSTO_MINIMO) * min(1.0, proporcion), 3)


# --------------------------------------------------------------------- saltos de tempo


def _destilar_saltos(corpus: Corpus) -> DistribucionSaltos:
    saltos: list[float] = []
    for grabado in corpus:
        for anterior, actual in grabado.pares():
            if anterior.bpm and actual.bpm and anterior.bpm > 0 and actual.bpm > 0:
                saltos.append(abs(diferencia_relativa(anterior.bpm, actual.bpm)))

    if not saltos:
        return DistribucionSaltos(0, 0, 0, 0, 0, 0, 0, 0, 0)

    saltos.sort()
    return DistribucionSaltos(
        muestras=len(saltos),
        p50=_percentil(saltos, 0.50),
        p75=_percentil(saltos, 0.75),
        p90=_percentil(saltos, 0.90),
        p95=_percentil(saltos, 0.95),
        p99=_percentil(saltos, 0.99),
        maximo=saltos[-1],
        proporcion_bajo_3pct=sum(1 for s in saltos if s < 0.03) / len(saltos),
        proporcion_bajo_6pct=sum(1 for s in saltos if s < 0.06) / len(saltos),
    )


def _percentil(ordenados: Sequence[float], p: float) -> float:
    if not ordenados:
        return 0.0
    indice = min(len(ordenados) - 1, max(0, int(round(p * (len(ordenados) - 1)))))
    return ordenados[indice]


# -------------------------------------------------------------------------- Camelot


def _destilar_camelot(corpus: Corpus) -> dict[str, int]:
    conteos: dict[str, int] = {}
    for grabado in corpus:
        for anterior, actual in grabado.pares():
            if not anterior.camelot or not actual.camelot:
                continue
            etiqueta = _ETIQUETAS_CAMELOT.get(compatibilidad(anterior.camelot, actual.camelot))
            if etiqueta:
                conteos[etiqueta] = conteos.get(etiqueta, 0) + 1
    return conteos


# --------------------------------------------------------------------------- curvas


def _destilar_curva(corpus: Corpus, campo: str, *, normalizar: bool) -> tuple[float, ...]:
    """Promedio del campo por decil de avance del set.

    Con `normalizar`, cada set se expresa relativo a su propio promedio. Es lo correcto
    para el tempo: promediar en absoluto un set de drum and bass con uno de cumbia da un
    número que no describe a ninguno de los dos. La **forma** sí es comparable.
    """
    sumas = [0.0] * _DECILES
    conteos = [0] * _DECILES

    for grabado in corpus:
        valores = [(t.posicion, getattr(t, campo)) for t in grabado.temas]
        valores = [(pos, v) for pos, v in valores if v is not None]
        if len(valores) < _DECILES // 2:
            continue

        referencia = sum(v for _, v in valores) / len(valores) if normalizar else 1.0
        if normalizar and referencia == 0:
            continue

        for indice, (_, valor) in enumerate(valores):
            decil = min(_DECILES - 1, int(_DECILES * indice / len(valores)))
            sumas[decil] += (valor / referencia - 1.0) if normalizar else valor
            conteos[decil] += 1

    return tuple(
        round(suma / conteo, 4) if conteo else 0.0 for suma, conteo in zip(sumas, conteos)
    )

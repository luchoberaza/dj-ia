"""Auditoría de la configuración: el grafo y el catálogo contra la política.

Las invariantes de `invariantes.py` auditan **planes**. Esto audita lo que el motor
recibe antes de planificar nada, y existe por dos hallazgos de la etapa 1:

- **H2, trampa de tempo.** Un grafo de géneros puede estar perfectamente conectado y
  ser inservible, porque la conectividad no garantiza que exista una ruta cuyo tempo
  suba de forma monótona. Si el único camino de 105 a 126 BPM pasa por un género que
  está en 95, el motor no lo va a tomar —y hace bien—, y la fase se queda corta. La
  falla no es del planificador: es del mapa que le dimos.

- **H4, profundidad por fase.** El cuello de botella de un catálogo no es su tamaño
  total sino cuántos temas sirven a cada fase. Un catálogo de 900 temas puede dejar al
  motor sin material en el pico y hacerlo caer a la tanda de emergencia.

Esto es una función del onboarding: se corre cuando entra un cliente, y su salida es la
lista de compras del record pool.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median
from typing import Iterable, Mapping, Sequence

from .dominio import Fase, GrafoGeneros, Pista, PoliticaNoche

#: Un tema "sirve" a una fase si su tempo está dentro de esto del objetivo.
TOLERANCIA_SERVICIO = 0.10

#: Cuánto puede bajar el tempo un salto sin que cuente como pozo. Un movimiento lateral
#: chico es normal; un pozo real es lo que hace que el motor se quede quieto.
TOLERANCIA_POZO = 0.02

#: Cuántas veces la cantidad de temas de una noche hacen falta en catálogo para que
#: haya variedad real y los cooldowns no ahoguen la fase.
FACTOR_VARIEDAD = 5.0

#: Duración media de un tema, en minutos.
DURACION_MEDIA_MIN = 3.5

#: Qué parte de una fase tiene que cubrir un género para que valga la pena auditar si
#: es una trampa. Sin esto, un género con dos temas sueltos en el rango genera ruido.
_PARTICIPACION_MINIMA = 0.05


@dataclass(frozen=True, slots=True)
class Advertencia:
    tipo: str
    gravedad: str  # "bloqueante" | "aviso"
    detalle: str

    def __str__(self) -> str:
        marca = "✗" if self.gravedad == "bloqueante" else "!"
        return f"{marca} {self.tipo}: {self.detalle}"


def tempos_por_genero(catalogo: Iterable[Pista]) -> dict[str, float]:
    """Tempo mediano de cada género del catálogo. Mediana y no promedio: un tema mal
    analizado al doble de tiempo arrastra el promedio y no mueve la mediana."""
    agrupados: dict[str, list[float]] = {}
    for pista in catalogo:
        agrupados.setdefault(pista.genero, []).append(pista.bpm)
    return {genero: median(bpms) for genero, bpms in agrupados.items()}


def generos_que_sirven(
    catalogo: Iterable[Pista], fase: Fase, tolerancia: float = TOLERANCIA_SERVICIO
) -> dict[str, int]:
    """Géneros con temas útiles para esa fase, y cuántos temas aporta cada uno."""
    conteo: dict[str, int] = {}
    for pista in catalogo:
        if fase.generos_permitidos is not None and pista.genero not in fase.generos_permitidos:
            continue
        if abs(pista.bpm - fase.bpm_objetivo) / fase.bpm_objetivo <= tolerancia:
            conteo[pista.genero] = conteo.get(pista.genero, 0) + 1
    return conteo


def ruta_monotona(
    grafo: GrafoGeneros,
    tempos: Mapping[str, float],
    origenes: Iterable[str],
    destinos: Iterable[str],
    *,
    subiendo: bool,
    tolerancia_pozo: float = TOLERANCIA_POZO,
) -> list[str] | None:
    """Camino en el grafo cuyo tempo se mueve en la dirección pedida, sin pozos.

    Devuelve la secuencia de géneros, o None si no existe. Es exactamente la pregunta
    que el planificador se hace implícitamente y que nadie había chequeado.
    """
    destinos = set(destinos)
    pendientes: list[list[str]] = [[o] for o in origenes if o in tempos]
    for ruta in pendientes:
        if ruta[0] in destinos:
            return ruta

    vistos = {ruta[0] for ruta in pendientes}

    while pendientes:
        siguiente: list[list[str]] = []
        for ruta in pendientes:
            actual = ruta[-1]
            tempo_actual = tempos[actual]
            for vecino in grafo.vecinos(actual):
                if vecino in vistos or vecino not in tempos:
                    continue
                delta = (tempos[vecino] - tempo_actual) / tempo_actual
                if subiendo and delta < -tolerancia_pozo:
                    continue
                if not subiendo and delta > tolerancia_pozo:
                    continue
                camino = ruta + [vecino]
                if vecino in destinos:
                    return camino
                vistos.add(vecino)
                siguiente.append(camino)
        pendientes = siguiente

    return None


def auditar(
    catalogo: Sequence[Pista],
    politica: PoliticaNoche,
    grafo: GrafoGeneros,
    *,
    duracion_noche_min: float = 360.0,
    factor_variedad: float = FACTOR_VARIEDAD,
    duracion_media_min: float = DURACION_MEDIA_MIN,
) -> list[Advertencia]:
    """Todo lo que el motor va a sufrir, dicho antes de la primera noche."""
    advertencias: list[Advertencia] = []
    tempos = tempos_por_genero(catalogo)

    advertencias.extend(_auditar_generos_aislados(tempos, grafo))
    advertencias.extend(
        _auditar_profundidad(
            catalogo, politica, duracion_noche_min, factor_variedad, duracion_media_min
        )
    )
    advertencias.extend(_auditar_trampas_de_tempo(catalogo, politica, grafo, tempos))
    return advertencias


def _auditar_generos_aislados(
    tempos: Mapping[str, float], grafo: GrafoGeneros
) -> list[Advertencia]:
    aislados = [g for g in tempos if not grafo.vecinos(g) and g not in grafo.generos()]
    return [
        Advertencia(
            "genero_aislado",
            "aviso",
            f"{genero} está en el catálogo pero no tiene ninguna arista: "
            "esos temas no se van a poder tocar nunca",
        )
        for genero in sorted(aislados)
    ]


def _duracion_de_fase(politica: PoliticaNoche, indice: int, duracion_noche: float) -> float:
    fase = politica.fases[indice]
    if indice + 1 < len(politica.fases):
        return politica.fases[indice + 1].desde_min - fase.desde_min
    return max(0.0, duracion_noche - fase.desde_min)


def _auditar_profundidad(
    catalogo: Sequence[Pista],
    politica: PoliticaNoche,
    duracion_noche: float,
    factor_variedad: float,
    duracion_media: float,
) -> list[Advertencia]:
    advertencias: list[Advertencia] = []

    for indice, fase in enumerate(politica.fases):
        duracion = _duracion_de_fase(politica, indice, duracion_noche)
        if duracion <= 0:
            continue

        por_noche = duracion / duracion_media
        minimo = math.ceil(por_noche * factor_variedad)
        sirven = generos_que_sirven(catalogo, fase)
        disponibles = sum(sirven.values())

        if disponibles < minimo:
            advertencias.append(
                Advertencia(
                    "profundidad_de_fase",
                    "bloqueante",
                    f"fase {fase.nombre}: {disponibles} temas útiles y hacen falta ~{minimo} "
                    f"({duracion:.0f} min ÷ {duracion_media:.1f} min × {factor_variedad:.0f}). "
                    f"Faltan temas entre {fase.bpm_objetivo * 0.9:.0f} y "
                    f"{fase.bpm_objetivo * 1.1:.0f} BPM",
                )
            )
        elif len(sirven) < 2:
            advertencias.append(
                Advertencia(
                    "monocultivo_de_fase",
                    "aviso",
                    f"fase {fase.nombre}: todos los temas útiles son de un solo género "
                    f"({next(iter(sirven), 'ninguno')}). La fase va a sonar monótona",
                )
            )

    return advertencias


def _auditar_trampas_de_tempo(
    catalogo: Sequence[Pista],
    politica: PoliticaNoche,
    grafo: GrafoGeneros,
    tempos: Mapping[str, float],
) -> list[Advertencia]:
    advertencias: list[Advertencia] = []

    for anterior, siguiente in zip(politica.fases, politica.fases[1:]):
        if abs(siguiente.bpm_objetivo - anterior.bpm_objetivo) / anterior.bpm_objetivo < 0.02:
            continue  # las fases están al mismo tempo: no hay nada que atravesar

        origenes = generos_que_sirven(catalogo, anterior)
        destinos = generos_que_sirven(catalogo, siguiente)
        if not origenes or not destinos:
            continue  # ya lo reporta la auditoría de profundidad

        subiendo = siguiente.bpm_objetivo > anterior.bpm_objetivo
        total_origen = sum(origenes.values())

        # No alcanza con preguntar si ALGÚN género llega: hay que preguntarlo por cada
        # género en el que el motor pueda estar parado. Un género que sirve a la fase A
        # y no tiene salida monótona hacia B es una trampa — el planificador se mete y
        # se queda, y la fase siguiente arranca corta. Fue exactamente lo que pasó.
        atrapados = [
            genero
            for genero, cuantos in origenes.items()
            if cuantos / total_origen >= _PARTICIPACION_MINIMA
            and ruta_monotona(grafo, tempos, [genero], destinos, subiendo=subiendo) is None
        ]

        if atrapados:
            advertencias.append(
                Advertencia(
                    "trampa_de_tempo",
                    "bloqueante",
                    f"de {anterior.nombre} ({anterior.bpm_objetivo:.0f} BPM) a "
                    f"{siguiente.nombre} ({siguiente.bpm_objetivo:.0f}): desde "
                    f"{sorted(atrapados)} no hay ninguna ruta que "
                    f"{'suba' if subiendo else 'baje'} sin pasar por un pozo. "
                    f"Hacia {sorted(destinos)} falta un puente",
                )
            )

    return advertencias

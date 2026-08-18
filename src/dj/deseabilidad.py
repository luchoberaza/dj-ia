"""Qué tan bueno es un tema *ahora mismo*, con independencia de dónde venimos.

Es la mitad del puntaje. La otra mitad —cuánto cuesta llegar hasta él— vive en
`costos.py`, y mezclarlas en un solo número es el error de diseño típico.

Nota sobre el diseño original: listaba "frescura" y "fatiga" como señales separadas,
pero son los dos extremos del mismo eje. Se unificaron en `rotacion` para no contar
dos veces lo mismo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .dominio import Atractor, Pista


@dataclass(frozen=True, slots=True)
class PesosDeseabilidad:
    """A los seis meses, `rendimiento_local` vale más que todo el resto junto — y es
    la única señal que ningún competidor puede copiar."""

    votos: float = 1.00
    tendencia: float = 0.35
    rendimiento_local: float = 0.50
    rotacion: float = 0.30


@dataclass(frozen=True, slots=True)
class Senales:
    """Señales acumuladas del catálogo, todas opcionales.

    - `tendencia`: 0..1, de Last.fm y charts.
    - `rendimiento_local`: -1..1, del histórico propio del establecimiento. Cuando este
      tema sonó acá, ¿la pista aguantó o se vació?
    - `rotacion`: 0..1. 0 = hace mucho que no suena, 1 = suena todo el tiempo.
    """

    tendencia: Mapping[str, float] = field(default_factory=dict)
    rendimiento_local: Mapping[str, float] = field(default_factory=dict)
    rotacion: Mapping[str, float] = field(default_factory=dict)


class Deseabilidad:
    """Evaluador para una llamada de planificación.

    Se construye una vez por plan porque cachea la normalización de los votos: el peso
    de un voto es relativo al voto más fuerte de esa noche, no un absoluto.
    """

    __slots__ = ("_atractor", "_senales", "_pesos", "_max_voto", "_cache")

    def __init__(
        self,
        atractor: Atractor | None = None,
        senales: Senales | None = None,
        pesos: PesosDeseabilidad | None = None,
    ) -> None:
        self._atractor = atractor if atractor is not None else Atractor()
        self._senales = senales if senales is not None else Senales()
        self._pesos = pesos if pesos is not None else PesosDeseabilidad()
        self._max_voto = max(self._atractor.pistas.values(), default=0.0)
        self._cache: dict[str, float] = {}

    def para(self, pista: Pista) -> float:
        """La deseabilidad no depende del estado, así que se cachea por plan.

        El planificador la consulta miles de veces por llamada: sin caché es el
        segundo cuello de botella después del grafo.
        """
        valor = self._cache.get(pista.id)
        if valor is None:
            valor = self._calcular(pista)
            self._cache[pista.id] = valor
        return valor

    def _calcular(self, pista: Pista) -> float:
        p = self._pesos
        s = self._senales

        votos = 0.0
        if self._max_voto > 0:
            votos = self._atractor.peso(pista.id) / self._max_voto

        tendencia = s.tendencia.get(pista.id, 0.0)
        rendimiento = s.rendimiento_local.get(pista.id, 0.0)
        rotacion = s.rotacion.get(pista.id, 0.5)

        return (
            p.votos * votos
            + p.tendencia * tendencia
            + p.rendimiento_local * rendimiento
            + p.rotacion * (0.5 - rotacion)
        )

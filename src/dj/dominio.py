"""Tipos del dominio.

El vocabulario está en español a propósito: es el vocabulario del cliente, y según el
diseño tiene que serlo en la UI, en el código, en las tablas y en los archivos.

Este módulo no depende de nada más del paquete: es la base sobre la que se apoyan los
costos, las restricciones y el planificador.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


# --------------------------------------------------------------------------- pistas


class TipoTransicion(str, Enum):
    """Cómo se pasa de un tema al siguiente.

    El corte no es el fracaso: un corte al final de una frase suena intencional.
    Lo que suena a error es el corte arbitrario, a mitad de frase.
    """

    COSTURA_LARGA = "costura_larga"
    COSTURA_CORTA = "costura_corta"
    CORTE_BREAK = "corte_break"
    CORTE_PUENTE = "corte_puente"

    @property
    def es_costura(self) -> bool:
        return self in (TipoTransicion.COSTURA_LARGA, TipoTransicion.COSTURA_CORTA)


@dataclass(frozen=True, slots=True)
class Pista:
    """Un tema del catálogo del establecimiento, ya analizado.

    `apta_para_costura` es el campo que evita que el motor se rompa con música de
    tempo variable: la pista no se descarta, se programa por corte.
    """

    id: str
    titulo: str
    artista: str
    genero: str
    bpm: float
    duracion_s: float
    camelot: str | None = None  # "8A" (menor) / "8B" (mayor); None = desconocido
    energia: float = 5.0  # 1-10
    isrc: str | None = None
    bpm_confianza: float = 1.0  # 0-1
    camelot_confianza: float = 1.0
    apta_para_costura: bool = True
    loudness_lufs: float = -8.0
    mix_in_ms: int = 0  # los usa el agente reproductor, no el planificador
    mix_out_ms: int = 0

    @property
    def duracion_min(self) -> float:
        return self.duracion_s / 60.0


# ------------------------------------------------------------------- grafo de géneros


@dataclass(frozen=True, slots=True)
class GrafoGeneros:
    """Qué género puede seguir a cuál, y cuánto cuesta.

    Es la pieza donde vive literalmente la queja que originó el proyecto: "de la nada
    te cambia de género". En este modelo eso es una arista que no existe, y el motor
    no puede tomarla. No es que "trata de evitarlo".

    Es cultural, no universal: el grafo de un boliche de cumbia y el de un after no
    son el mismo grafo.
    """

    aristas: Mapping[tuple[str, str], float]

    #: Índices derivados. Se calculan una vez en la construcción porque el grafo es
    #: chico (decenas de géneros) y el planificador los consulta en su bucle interno:
    #: recorrer las aristas por candidato era el cuello de botella del motor.
    _vecinos: dict[str, tuple[str, ...]] = field(
        default_factory=dict, repr=False, compare=False
    )
    _saltos: dict[tuple[str, str], int] = field(
        default_factory=dict, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        adyacencia: dict[str, list[str]] = {}
        for desde, hacia in self.aristas:
            adyacencia.setdefault(desde, []).append(hacia)
            adyacencia.setdefault(hacia, [])
        for genero, vecinos in adyacencia.items():
            self._vecinos[genero] = tuple(dict.fromkeys(vecinos))
        for origen in self._vecinos:
            self._saltos.update(self._bfs(origen))

    def _bfs(self, origen: str) -> dict[tuple[str, str], int]:
        distancias = {(origen, origen): 0}
        frontera = [origen]
        profundidad = 0
        while frontera:
            profundidad += 1
            siguiente: list[str] = []
            for actual in frontera:
                for vecino in self._vecinos.get(actual, ()):
                    if (origen, vecino) not in distancias:
                        distancias[(origen, vecino)] = profundidad
                        siguiente.append(vecino)
            frontera = siguiente
        return distancias

    def costo(self, desde: str, hacia: str) -> float | None:
        """Costo de la arista, o None si no existe (⇒ ese salto no se hace nunca)."""
        if desde == hacia:
            return 0.0
        return self.aristas.get((desde, hacia))

    def hay_arista(self, desde: str, hacia: str) -> bool:
        return desde == hacia or (desde, hacia) in self.aristas

    def vecinos(self, genero: str) -> tuple[str, ...]:
        """Géneros a los que se puede ir directamente desde `genero`."""
        return self._vecinos.get(genero, ())

    def generos(self) -> set[str]:
        return set(self._vecinos)

    def saltos(self, desde: str, hacia: str) -> int | None:
        """Cantidad mínima de aristas para ir de un género a otro.

        None si no hay camino. Lo usa la heurística del planificador para estimar
        cuán lejos está el destino votado.
        """
        if desde == hacia:
            return 0
        return self._saltos.get((desde, hacia))


# ------------------------------------------------------------------ política de noche


@dataclass(frozen=True, slots=True)
class Fase:
    """Un tramo de la noche con su objetivo de tempo y energía.

    `desde_min` son minutos desde el arranque de la noche, no hora de reloj: evita
    todo el enredo de cruzar la medianoche.
    """

    nombre: str
    desde_min: float
    bpm_objetivo: float
    energia_objetivo: float
    generos_permitidos: frozenset[str] | None = None  # None = todos
    permite_bajar_bpm: bool = True
    es_build: bool = False


@dataclass(frozen=True, slots=True)
class PoliticaNoche:
    """La configuración de la noche de un establecimiento.

    Las restricciones de acá son duras: no se negocian con ningún peso ni con ningún
    voto. Un voto puede torcer el rumbo; no puede romper la noche.
    """

    nombre: str
    fases: tuple[Fase, ...]
    cooldown_tema_min: float = 240.0
    cooldown_artista_min: float = 45.0
    max_por_artista_por_hora: int = 2
    max_concesiones_voto_por_hora: int = 4
    lista_negra: frozenset[str] = frozenset()
    margen_bajada_bpm: float = 1.0  # tolerancia de ruido para la regla del pico
    #: Cuánto puede correr el voto el tempo objetivo de una fase, como fracción. Es el
    #: techo declarado de "el voto tuerce el rumbo pero no lo manda", y tiene que ser
    #: menor que la tolerancia con la que se audita el promedio de la fase.
    max_desvio_voto: float = 0.10

    def __post_init__(self) -> None:
        if not self.fases:
            raise ValueError("una política necesita al menos una fase")
        minutos = [f.desde_min for f in self.fases]
        if minutos != sorted(minutos):
            raise ValueError("las fases tienen que estar ordenadas por desde_min")
        if minutos[0] != 0:
            raise ValueError("la primera fase tiene que arrancar en el minuto 0")

    def fase_en(self, minuto: float) -> Fase:
        elegida = self.fases[0]
        for fase in self.fases:
            if minuto >= fase.desde_min:
                elegida = fase
            else:
                break
        return elegida


# ------------------------------------------------------------------------- el atractor


@dataclass(frozen=True, slots=True)
class Atractor:
    """Hacia dónde quiere ir la pista, según lo votado.

    No es un tema: es una dirección. El voto es un destino, no una instrucción — esa
    es toda la diferencia entre esto y un jukebox.
    """

    pistas: Mapping[str, float] = field(default_factory=dict)  # id_pista -> peso
    genero: str | None = None
    delta_energia: float = 0.0
    delta_bpm: float = 0.0

    @property
    def vacio(self) -> bool:
        return not self.pistas and self.genero is None and self.delta_energia == 0.0

    def peso(self, id_pista: str) -> float:
        return self.pistas.get(id_pista, 0.0)

    def destino_principal(self) -> str | None:
        if not self.pistas:
            return None
        return max(self.pistas.items(), key=lambda par: par[1])[0]


# ---------------------------------------------------------------- estado de la noche


@dataclass(frozen=True, slots=True)
class EstadoNoche:
    """Dónde estamos parados. Inmutable: el planificador simula avanzando copias."""

    minuto: float = 0.0
    actual: Pista | None = None
    ultimo_minuto_pista: Mapping[str, float] = field(default_factory=dict)
    minutos_artista: Mapping[str, tuple[float, ...]] = field(default_factory=dict)
    concesiones: tuple[float, ...] = ()

    def avanzar(self, pista: Pista, cedio_al_voto: bool = False) -> EstadoNoche:
        """Devuelve el estado después de reproducir `pista` desde el minuto actual."""
        fin = self.minuto + pista.duracion_min

        ultimo = dict(self.ultimo_minuto_pista)
        ultimo[pista.id] = self.minuto

        artistas = dict(self.minutos_artista)
        previos = artistas.get(pista.artista, ())
        # se podan los que ya no pueden influir en ninguna ventana de una hora
        vigentes = tuple(m for m in previos if fin - m <= 120.0)
        artistas[pista.artista] = vigentes + (self.minuto,)

        concesiones = self.concesiones
        if cedio_al_voto:
            concesiones = tuple(m for m in concesiones if fin - m <= 60.0) + (self.minuto,)

        return EstadoNoche(
            minuto=fin,
            actual=pista,
            ultimo_minuto_pista=ultimo,
            minutos_artista=artistas,
            concesiones=concesiones,
        )

    def minutos_desde(self, id_pista: str) -> float | None:
        visto = self.ultimo_minuto_pista.get(id_pista)
        return None if visto is None else self.minuto - visto

    def veces_artista_ultima_hora(self, artista: str) -> int:
        return sum(1 for m in self.minutos_artista.get(artista, ()) if self.minuto - m < 60.0)

    def minutos_desde_artista(self, artista: str) -> float | None:
        previos = self.minutos_artista.get(artista, ())
        if not previos:
            return None
        return self.minuto - max(previos)

    def concesiones_ultima_hora(self) -> int:
        return sum(1 for m in self.concesiones if self.minuto - m < 60.0)


# ---------------------------------------------------------------------- explicabilidad


@dataclass(frozen=True, slots=True)
class Desglose:
    """Por qué el motor eligió este tema.

    No es un lujo: es lo que te deja depurar una mala noche, convencer al DJ escéptico
    y responderle al dueño. Un motor que no podés explicar es invendible.
    """

    costo_total: float
    tempo: float
    tonal: float
    genero: float
    energia: float
    costura: float
    deseabilidad: float
    diferencia_tempo_rel: float
    bpm_equivalente: float
    curva: float = 0.0
    bpm_objetivo: float = 0.0
    tonal_neutralizado: bool = False

    def como_texto(self, desde: Pista | None, hacia: Pista) -> str:
        partes: list[str] = []
        if desde is not None:
            partes.append(
                f"tempo {desde.bpm:.0f}→{self.bpm_equivalente:.0f} "
                f"({self.diferencia_tempo_rel:+.1%}, costo {self.tempo:.2f})"
            )
            if self.tonal_neutralizado:
                partes.append("tonalidad desconocida (término neutralizado)")
            else:
                partes.append(f"{desde.camelot}→{hacia.camelot} ({self.tonal:.2f})")
            if desde.genero == hacia.genero:
                partes.append("mismo género (0.00)")
            else:
                partes.append(f"{desde.genero}→{hacia.genero} ({self.genero:.2f})")
        if self.bpm_objetivo:
            partes.append(f"curva → {self.bpm_objetivo:.0f} BPM ({self.curva:.2f})")
        partes.append(f"energía {hacia.energia:.0f} ({self.energia:.2f})")
        partes.append(f"deseabilidad {self.deseabilidad:.2f}")
        return " · ".join(partes)

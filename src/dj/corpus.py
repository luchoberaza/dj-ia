"""El corpus de sets reales: la fuente de verdad del nivel 1.

Un set grabado es una **secuencia ordenada de temas que alguien tocó ante una pista
real**. Miles de esas secuencias contienen el gusto ya destilado, y se pueden medir en
vez de opinar.

Esto existe porque un DJ mediocre como oráculo codifica su mediocridad — y peor: el DJ
que cambia de género sin corte no se da cuenta de que lo hace, así que tampoco lo marca
cuando revisa un plan. Es un oráculo roto. Los sets, no.

El formato de ingesta está documentado en `docs/formato-corpus.md`. Es deliberadamente
tonto —artista, título, y lo que se sepa— porque las fuentes reales traen muy poco y el
resto se enriquece después contra Deezer y el analizador.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence


@dataclass(frozen=True, slots=True)
class TemaDeSet:
    """Un tema tal como aparece en un tracklist.

    Casi todo es opcional a propósito: un tracklist de 1001Tracklists trae artista y
    título, nada más. El BPM, la tonalidad y la energía llegan después del
    enriquecimiento, y muchas veces no llegan. Cada métrica del destilado reporta su
    propia cobertura para que nadie confunda "500 sets" con "500 sets con tempo".
    """

    posicion: int
    artista: str | None = None
    titulo: str | None = None
    isrc: str | None = None
    genero: str | None = None
    bpm: float | None = None
    camelot: str | None = None
    energia: float | None = None


@dataclass(frozen=True, slots=True)
class SetGrabado:
    id: str
    temas: tuple[TemaDeSet, ...]
    fuente: str = "desconocida"
    #: Con qué escena se corresponde. El gusto no es universal: el grafo de un boliche
    #: de cumbia y el de un after no son el mismo grafo, así que destilarlos juntos
    #: produce un promedio que no sirve para ninguno de los dos.
    escena: str | None = None
    url: str | None = None

    def __len__(self) -> int:
        return len(self.temas)

    def pares(self) -> Iterator[tuple[TemaDeSet, TemaDeSet]]:
        """Las transiciones del set: los pares consecutivos."""
        return zip(self.temas, self.temas[1:])


@dataclass(frozen=True, slots=True)
class Corpus:
    sets: tuple[SetGrabado, ...]

    def __len__(self) -> int:
        return len(self.sets)

    def __iter__(self) -> Iterator[SetGrabado]:
        return iter(self.sets)

    def de_escena(self, escena: str) -> Corpus:
        return Corpus(tuple(s for s in self.sets if s.escena == escena))

    def escenas(self) -> dict[str, int]:
        conteo: dict[str, int] = {}
        for s in self.sets:
            conteo[s.escena or "sin_escena"] = conteo.get(s.escena or "sin_escena", 0) + 1
        return conteo

    @property
    def total_temas(self) -> int:
        return sum(len(s) for s in self.sets)

    @property
    def total_transiciones(self) -> int:
        return sum(max(0, len(s) - 1) for s in self.sets)


# ------------------------------------------------------------------------ ingesta


def desde_diccionarios(datos: Iterable[dict]) -> Corpus:
    """Construye un corpus desde estructuras ya parseadas.

    Es el punto de entrada que usa cualquier adaptador de fuente: el que lea
    tracklists, el que lea planillas de airplay de radio, o el que lea el histórico de
    un local que ya funciona. Ninguno de ellos vive acá.
    """
    sets: list[SetGrabado] = []
    for bruto in datos:
        temas = tuple(
            TemaDeSet(
                posicion=int(t.get("posicion", i + 1)),
                artista=t.get("artista"),
                titulo=t.get("titulo"),
                isrc=t.get("isrc"),
                genero=t.get("genero"),
                bpm=_flotante(t.get("bpm")),
                camelot=t.get("camelot"),
                energia=_flotante(t.get("energia")),
            )
            for i, t in enumerate(bruto.get("temas", ()))
        )
        sets.append(
            SetGrabado(
                id=str(bruto.get("id", f"set{len(sets) + 1:05d}")),
                temas=temas,
                fuente=bruto.get("fuente", "desconocida"),
                escena=bruto.get("escena"),
                url=bruto.get("url"),
            )
        )
    return Corpus(tuple(sets))


def cargar(ruta: str | Path) -> Corpus:
    """Lee un corpus de un archivo JSON. Ver `docs/formato-corpus.md`."""
    contenido = json.loads(Path(ruta).read_text(encoding="utf-8"))
    if isinstance(contenido, dict):
        contenido = contenido.get("sets", ())
    return desde_diccionarios(contenido)


def guardar(corpus: Corpus, ruta: str | Path) -> None:
    datos = {
        "sets": [
            {
                "id": s.id,
                "fuente": s.fuente,
                "escena": s.escena,
                "url": s.url,
                "temas": [
                    {
                        k: v
                        for k, v in (
                            ("posicion", t.posicion),
                            ("artista", t.artista),
                            ("titulo", t.titulo),
                            ("isrc", t.isrc),
                            ("genero", t.genero),
                            ("bpm", t.bpm),
                            ("camelot", t.camelot),
                            ("energia", t.energia),
                        )
                        if v is not None
                    }
                    for t in s.temas
                ],
            }
            for s in corpus.sets
        ]
    }
    Path(ruta).write_text(
        json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def cobertura(corpus: Corpus, campo: str) -> float:
    """Qué proporción de los temas del corpus tiene ese campo cargado.

    Se reporta junto a cada métrica: un corpus de 500 sets con 30% de cobertura de BPM
    da una distribución de saltos basada en el 30%, y decir "500 sets" a secas sería
    mentir por omisión.
    """
    total = corpus.total_temas
    if total == 0:
        return 0.0
    con_dato = sum(
        1 for s in corpus.sets for t in s.temas if getattr(t, campo, None) is not None
    )
    return con_dato / total


def _flotante(valor: object) -> float | None:
    if valor is None or valor == "":
        return None
    try:
        return float(valor)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def secuencias_de_genero(corpus: Corpus) -> Iterator[Sequence[str]]:
    """Los géneros de cada set, en orden, salteando los temas sin género."""
    for s in corpus.sets:
        generos = [t.genero for t in s.temas if t.genero]
        if len(generos) >= 2:
            yield generos

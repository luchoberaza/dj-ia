"""Las invariantes mecánicas: el nivel 0 de validación.

La queja que originó el proyecto —"de la nada te cambia completamente de género sin
ningún corte"— **no es una opinión de gusto**: es un defecto detectable sin que nadie
opine nada. Este módulo lo detecta.

Es la red de seguridad que permite tocar los pesos del motor durante meses sin romper
nada, y es lo que ya pone al sistema por encima del DJ del problema antes de haber
aprendido ningún gusto.

Vive en `src/` y no en `tests/` a propósito: además de ser la suite de tests, se corre
sobre los planes reales en producción antes de comprometerlos.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .dominio import GrafoGeneros, PoliticaNoche, TipoTransicion
from .planificador import PasoPlan
from .tempo import TOLERANCIA_COSTURA, diferencia_relativa, equivalente_octava

#: Cuánto puede desviarse el BPM promedio de una fase respecto de su objetivo.
TOLERANCIA_FASE = 0.15

#: Invariantes que un tramo de emergencia tiene permiso de violar.
#:
#: Sale directo de la escala de prioridades del diseño: el silencio es el único
#: fracaso inaceptable, así que cuando no hay ruta válida se sacrifica "que la decisión
#: sea óptima" —repetir un tema antes de tiempo, machacar un artista, salirse de la
#: curva— pero nunca "que no rompa el ambiente". El salto de género sin puente, la
#: costura imposible, la lista negra y la regla del pico se auditan siempre.
TOLERADAS_EN_EMERGENCIA: frozenset[str] = frozenset(
    {
        "cooldown_tema",
        "artista_por_hora",
        "sin_artista_consecutivo",
        "genero_permitido_por_fase",
        "bpm_promedio_de_fase",
    }
)


@dataclass(frozen=True, slots=True)
class Infraccion:
    invariante: str
    indice: int
    detalle: str

    def __str__(self) -> str:
        return f"[{self.indice}] {self.invariante}: {self.detalle}"


def verificar(
    pasos: Sequence[PasoPlan],
    politica: PoliticaNoche,
    grafo: GrafoGeneros,
    *,
    tolerancia_fase: float = TOLERANCIA_FASE,
) -> list[Infraccion]:
    """Devuelve todas las infracciones del plan. Lista vacía = el plan es sano."""
    fallas: list[Infraccion] = []

    for i, paso in enumerate(pasos):
        pista = paso.pista
        previo = pasos[i - 1].pista if i > 0 else None
        fase = politica.fase_en(paso.minuto_inicio)

        if pista.id in politica.lista_negra or (
            pista.isrc is not None and pista.isrc in politica.lista_negra
        ):
            fallas.append(Infraccion("sin_lista_negra", i, f"{pista.titulo} está vetada"))

        if fase.generos_permitidos is not None and pista.genero not in fase.generos_permitidos:
            fallas.append(
                Infraccion(
                    "genero_permitido_por_fase",
                    i,
                    f"{pista.genero} no entra en la fase {fase.nombre}",
                )
            )

        if previo is None:
            continue

        if previo.genero != pista.genero and not grafo.hay_arista(previo.genero, pista.genero):
            fallas.append(
                Infraccion(
                    "genero_con_arista",
                    i,
                    f"salto {previo.genero} → {pista.genero} sin puente en el grafo",
                )
            )

        if paso.transicion.es_costura:
            relativa = diferencia_relativa(previo.bpm, pista.bpm)
            if abs(relativa) >= TOLERANCIA_COSTURA:
                fallas.append(
                    Infraccion(
                        "costura_dentro_de_tolerancia",
                        i,
                        f"costura con {relativa:+.1%} de diferencia de tempo",
                    )
                )
            if not (previo.apta_para_costura and pista.apta_para_costura):
                fallas.append(
                    Infraccion(
                        "costura_solo_entre_aptas",
                        i,
                        f"se costuró {previo.titulo} → {pista.titulo} con material no apto",
                    )
                )

        if previo.artista == pista.artista:
            fallas.append(
                Infraccion("sin_artista_consecutivo", i, f"{pista.artista} dos veces seguidas")
            )

        if not fase.permite_bajar_bpm:
            equivalente = equivalente_octava(previo.bpm, pista.bpm)
            if equivalente < previo.bpm - politica.margen_bajada_bpm:
                fallas.append(
                    Infraccion(
                        "bpm_no_baja_en_pico",
                        i,
                        f"{previo.bpm:.0f} → {equivalente:.0f} en fase {fase.nombre}",
                    )
                )

    fallas.extend(_verificar_cooldowns(pasos, politica))
    fallas.extend(_verificar_bpm_por_fase(pasos, politica, tolerancia_fase))
    return _filtrar_emergencia(fallas, pasos)


def _filtrar_emergencia(
    fallas: list[Infraccion], pasos: Sequence[PasoPlan]
) -> list[Infraccion]:
    """Descarta las infracciones que un tramo de emergencia tiene permitido cometer."""
    return [
        f
        for f in fallas
        if not (
            f.invariante in TOLERADAS_EN_EMERGENCIA
            and 0 <= f.indice < len(pasos)
            and pasos[f.indice].emergencia
        )
    ]


def _verificar_cooldowns(
    pasos: Sequence[PasoPlan], politica: PoliticaNoche
) -> list[Infraccion]:
    fallas: list[Infraccion] = []
    ultimo_tema: dict[str, float] = {}
    minutos_artista: dict[str, list[float]] = {}

    for i, paso in enumerate(pasos):
        pista = paso.pista
        minuto = paso.minuto_inicio

        anterior = ultimo_tema.get(pista.id)
        if anterior is not None and minuto - anterior < politica.cooldown_tema_min:
            fallas.append(
                Infraccion(
                    "cooldown_tema",
                    i,
                    f"{pista.titulo} repetido a los {minuto - anterior:.0f} min "
                    f"(mínimo {politica.cooldown_tema_min:.0f})",
                )
            )
        ultimo_tema[pista.id] = minuto

        previos = minutos_artista.setdefault(pista.artista, [])
        en_la_hora = sum(1 for m in previos if minuto - m < 60.0)
        if en_la_hora >= politica.max_por_artista_por_hora:
            fallas.append(
                Infraccion(
                    "artista_por_hora",
                    i,
                    f"{pista.artista} suena {en_la_hora + 1} veces en una hora "
                    f"(máximo {politica.max_por_artista_por_hora})",
                )
            )
        previos.append(minuto)

    return fallas


def _verificar_bpm_por_fase(
    pasos: Sequence[PasoPlan], politica: PoliticaNoche, tolerancia: float
) -> list[Infraccion]:
    """El BPM promedio de cada fase tiene que caer dentro de su objetivo.

    Es la invariante que atrapa la deriva lenta: el set que se va de tempo de a poco
    sin que ninguna transición individual esté mal.
    """
    por_fase: dict[str, list[float]] = {}
    referencia: dict[str, float] = {}

    for paso in pasos:
        if paso.emergencia:  # un tramo de emergencia no define la curva de la noche
            continue
        fase = politica.fase_en(paso.minuto_inicio)
        por_fase.setdefault(fase.nombre, []).append(paso.pista.bpm)
        referencia[fase.nombre] = fase.bpm_objetivo

    fallas: list[Infraccion] = []
    for nombre, bpms in por_fase.items():
        if len(bpms) < 3:  # con menos de tres temas el promedio no dice nada
            continue
        objetivo = referencia[nombre]
        # se compara módulo octava: un tema a 190 en una fase de 126 no es una deriva
        equivalentes = [equivalente_octava(objetivo, b) for b in bpms]
        promedio = sum(equivalentes) / len(equivalentes)
        desvio = (promedio - objetivo) / objetivo
        if abs(desvio) > tolerancia:
            fallas.append(
                Infraccion(
                    "bpm_promedio_de_fase",
                    0,
                    f"fase {nombre}: promedio {promedio:.0f} vs objetivo {objetivo:.0f} "
                    f"({desvio:+.0%}, tolerancia ±{tolerancia:.0%})",
                )
            )
    return fallas

"""Restricciones duras: no son costo, son ley.

No se negocian con ningún peso ni con ningún voto. Un voto puede torcer el rumbo; no
puede romper la noche.

Dos de estas no se relajan jamás, ni cuando el motor se queda sin plan válido: la
lista negra y el salto de género sin arista. La segunda es la razón de existir del
producto.
"""

from __future__ import annotations

from dataclasses import dataclass

from .dominio import EstadoNoche, Fase, GrafoGeneros, Pista, PoliticaNoche
from .tempo import equivalente_octava

#: Restricciones que se pueden relajar cuando no hay ninguna ruta válida, en este
#: orden exacto. El orden está declarado en el diseño y no se improvisa en runtime.
ORDEN_RELAJACION: tuple[str, ...] = ("cooldown_artista", "energia", "tonal")

#: Nunca, bajo ninguna circunstancia.
INNEGOCIABLES: frozenset[str] = frozenset({"lista_negra", "genero_sin_arista"})


@dataclass(frozen=True, slots=True)
class Violacion:
    regla: str
    detalle: str

    def __str__(self) -> str:  # pragma: no cover - conveniencia de depuración
        return f"{self.regla}: {self.detalle}"


def evaluar(
    candidata: Pista,
    estado: EstadoNoche,
    politica: PoliticaNoche,
    fase: Fase,
    grafo: GrafoGeneros,
    *,
    cede_al_voto: bool = False,
    relajaciones: frozenset[str] = frozenset(),
) -> Violacion | None:
    """Devuelve la primera violación encontrada, o None si la candidata pasa.

    `relajaciones` solo puede contener nombres de `ORDEN_RELAJACION`; cualquier otra
    cosa se ignora deliberadamente para que un error de tipeo no abra una puerta.
    """
    if candidata.id in politica.lista_negra or (
        candidata.isrc is not None and candidata.isrc in politica.lista_negra
    ):
        return Violacion("lista_negra", f"{candidata.titulo} está vetada en este local")

    actual = estado.actual

    if actual is not None and not grafo.hay_arista(actual.genero, candidata.genero):
        return Violacion(
            "genero_sin_arista",
            f"no existe puente {actual.genero} → {candidata.genero}",
        )

    if fase.generos_permitidos is not None and candidata.genero not in fase.generos_permitidos:
        return Violacion(
            "genero_no_permitido",
            f"{candidata.genero} no entra en la fase {fase.nombre}",
        )

    desde_tema = estado.minutos_desde(candidata.id)
    if desde_tema is not None and desde_tema < politica.cooldown_tema_min:
        return Violacion(
            "cooldown_tema",
            f"{candidata.titulo} sonó hace {desde_tema:.0f} min "
            f"(mínimo {politica.cooldown_tema_min:.0f})",
        )

    if "cooldown_artista" not in relajaciones:
        if actual is not None and actual.artista == candidata.artista:
            return Violacion("artista_consecutivo", f"{candidata.artista} dos veces seguidas")

        desde_artista = estado.minutos_desde_artista(candidata.artista)
        if desde_artista is not None and desde_artista < politica.cooldown_artista_min:
            return Violacion(
                "cooldown_artista",
                f"{candidata.artista} sonó hace {desde_artista:.0f} min",
            )

        if estado.veces_artista_ultima_hora(candidata.artista) >= politica.max_por_artista_por_hora:
            return Violacion(
                "artista_por_hora",
                f"{candidata.artista} ya suena {politica.max_por_artista_por_hora} veces esta hora",
            )

    if actual is not None and not fase.permite_bajar_bpm:
        equivalente = equivalente_octava(actual.bpm, candidata.bpm)
        if equivalente < actual.bpm - politica.margen_bajada_bpm:
            return Violacion(
                "baja_bpm_en_pico",
                f"{equivalente:.0f} < {actual.bpm:.0f} en fase {fase.nombre}",
            )

    if cede_al_voto and estado.concesiones_ultima_hora() >= politica.max_concesiones_voto_por_hora:
        return Violacion(
            "cupo_voto",
            f"ya se cedió al voto {politica.max_concesiones_voto_por_hora} veces esta hora",
        )

    return None


def relajaciones_hasta(nivel: int) -> frozenset[str]:
    """Las primeras `nivel` relajaciones del orden declarado.

    nivel=0 ⇒ ninguna. nivel=3 ⇒ las tres. Nunca devuelve una innegociable.
    """
    if nivel <= 0:
        return frozenset()
    return frozenset(ORDEN_RELAJACION[: min(nivel, len(ORDEN_RELAJACION))]) - INNEGOCIABLES

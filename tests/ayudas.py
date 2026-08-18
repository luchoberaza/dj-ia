"""Constructores cortos para armar casos en los tests."""

from __future__ import annotations

from dj.dominio import Pista


def pista(
    id_pista: str,
    *,
    genero: str = "reggaeton",
    bpm: float = 96.0,
    camelot: str | None = "8A",
    energia: float = 6.0,
    artista: str | None = None,
    apta: bool = True,
    duracion_s: float = 210.0,
    confianza_tono: float = 1.0,
    isrc: str | None = None,
) -> Pista:
    return Pista(
        id=id_pista,
        titulo=f"Tema {id_pista}",
        artista=artista or f"Artista {id_pista}",
        genero=genero,
        bpm=bpm,
        duracion_s=duracion_s,
        camelot=camelot,
        energia=energia,
        apta_para_costura=apta,
        camelot_confianza=confianza_tono,
        isrc=isrc,
    )

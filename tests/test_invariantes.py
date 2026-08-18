"""Tests de propiedad: el nivel 0 de validación.

No verifican que el set suene lindo —eso es gusto— sino que **no contenga las fallas
que el DJ del problema comete**. Se corren sobre noches generadas con catálogos y
votaciones distintas: cualquier plan, con cualquier biblioteca, con cualquier voto.

Es la red de seguridad que permite tocar los pesos del motor sin romper nada.
"""

from __future__ import annotations

import pytest
from ayudas import pista

from dj.catalogo_demo import (
    atractor_demo,
    catalogo_demo,
    emergencia_demo,
    grafo_boliche,
    politica_boliche,
    senales_demo,
)
from dj.dominio import PoliticaNoche
from dj.invariantes import TOLERADAS_EN_EMERGENCIA, verificar
from dj.planificador import generar_noche

SEMILLAS = (1, 7, 17, 42, 101)
GENEROS_VOTADOS = (None, "cumbia", "techno", "cuarteto", "perreo")

#: Seis horas: cubre las seis fases, incluido el pico. Generar una noche cuesta varios
#: segundos, así que se cachean y se reusan entre tests.
DURACION = 360.0
_CACHE: dict[tuple[int, str | None], tuple] = {}


def _noche(semilla: int, genero_votado: str | None):
    clave = (semilla, genero_votado)
    if clave not in _CACHE:
        catalogo = catalogo_demo(900, semilla=semilla)
        politica = politica_boliche()
        grafo = grafo_boliche()
        pasos = generar_noche(
            catalogo,
            politica,
            grafo,
            duracion_min=DURACION,
            atractor=atractor_demo(catalogo, genero_votado) if genero_votado else None,
            senales=senales_demo(catalogo, semilla=semilla),
            emergencia=emergencia_demo(catalogo, politica),
        )
        _CACHE[clave] = (pasos, politica, grafo)
    return _CACHE[clave]


@pytest.mark.parametrize("semilla", SEMILLAS)
def test_ninguna_noche_viola_las_invariantes(semilla):
    """La propiedad central: sea cual sea el catálogo, el plan es sano."""
    pasos, politica, grafo = _noche(semilla, None)
    fallas = verificar(pasos, politica, grafo)
    assert not fallas, "\n".join(str(f) for f in fallas)


@pytest.mark.parametrize("genero", GENEROS_VOTADOS)
def test_el_voto_no_rompe_la_noche(genero):
    """Aunque la gente vote algo que tira del tempo para abajo o cambia de género."""
    pasos, politica, grafo = _noche(17, genero)
    fallas = verificar(pasos, politica, grafo)
    assert not fallas, "\n".join(str(f) for f in fallas)


@pytest.mark.parametrize("semilla", SEMILLAS)
def test_nunca_hay_un_salto_de_genero_sin_puente(semilla):
    """La queja original, aislada: 'de la nada te cambia completamente de género'.

    Se audita sobre TODOS los pasos, incluidos los de emergencia: ésta es una de las
    reglas que no se relajan nunca, bajo ninguna circunstancia.
    """
    pasos, _, grafo = _noche(semilla, "cumbia")
    for anterior, actual in zip(pasos, pasos[1:]):
        a, b = anterior.pista.genero, actual.pista.genero
        assert a == b or grafo.hay_arista(a, b), f"salto {a} -> {b} sin puente"


@pytest.mark.parametrize("semilla", SEMILLAS)
def test_nunca_se_costura_material_que_no_se_puede_costurar(semilla):
    """El material con análisis dudoso entra por corte, no por costura."""
    pasos, _, _ = _noche(semilla, None)
    for anterior, actual in zip(pasos, pasos[1:]):
        if actual.transicion.es_costura:
            assert anterior.pista.apta_para_costura and actual.pista.apta_para_costura


@pytest.mark.parametrize("semilla", SEMILLAS)
def test_en_el_pico_el_tempo_nunca_baja(semilla):
    pasos, politica, grafo = _noche(semilla, "cumbia")
    fallas = [f for f in verificar(pasos, politica, grafo) if f.invariante == "bpm_no_baja_en_pico"]
    assert not fallas, "\n".join(str(f) for f in fallas)


@pytest.mark.parametrize("semilla", SEMILLAS)
def test_la_curva_de_la_noche_se_respeta(semilla):
    """Atrapa la deriva lenta: cada transición correcta, el set entero desviado."""
    pasos, politica, grafo = _noche(semilla, None)
    fallas = [
        f for f in verificar(pasos, politica, grafo) if f.invariante == "bpm_promedio_de_fase"
    ]
    assert not fallas, "\n".join(str(f) for f in fallas)


class TestLaEmergenciaSacrificaLoCorrecto:
    """Un tramo de emergencia puede repetir un tema. No puede romper el ambiente."""

    def test_las_toleradas_son_solo_de_la_capa_optima(self):
        # ninguna de las reglas que definen "no romper el ambiente" es tolerable
        assert "genero_con_arista" not in TOLERADAS_EN_EMERGENCIA
        assert "sin_lista_negra" not in TOLERADAS_EN_EMERGENCIA
        assert "bpm_no_baja_en_pico" not in TOLERADAS_EN_EMERGENCIA
        assert "costura_dentro_de_tolerancia" not in TOLERADAS_EN_EMERGENCIA
        assert "costura_solo_entre_aptas" not in TOLERADAS_EN_EMERGENCIA

    @pytest.mark.parametrize("semilla", SEMILLAS)
    def test_los_tramos_de_emergencia_respetan_las_innegociables(self, semilla):
        pasos, politica, grafo = _noche(semilla, None)
        emergencias = [p for p in pasos if p.emergencia]
        if not emergencias:
            pytest.skip("esta noche no necesitó el plan B")
        for anterior, actual in zip(pasos, pasos[1:]):
            if not actual.emergencia:
                continue
            a, b = anterior.pista.genero, actual.pista.genero
            assert a == b or grafo.hay_arista(a, b)
            assert actual.pista.id not in politica.lista_negra


class TestQueLasInvariantesDetectanDeVerdad:
    """Si las invariantes no fallan nunca, no están midiendo nada.

    Estos tests les meten planes rotos a propósito y verifican que los caché.
    """

    def _plan_de(self, pistas, politica, emergencia=False):
        from dj.dominio import Desglose, TipoTransicion
        from dj.planificador import PasoPlan

        pasos = []
        minuto = 0.0
        for p in pistas:
            pasos.append(
                PasoPlan(
                    pista=p,
                    minuto_inicio=minuto,
                    transicion=TipoTransicion.COSTURA_LARGA,
                    desglose=Desglose(0, 0, 0, 0, 0, 0, 0, 0, p.bpm),
                    fase=politica.fase_en(minuto).nombre,
                    emergencia=emergencia,
                )
            )
            minuto += p.duracion_min
        return pasos

    def test_detecta_el_salto_de_genero_sin_puente(self, politica, grafo):
        roto = self._plan_de(
            [
                pista("x1", genero="cumbia", bpm=98.0, artista="A"),
                pista("x2", genero="techno", bpm=98.0, artista="B"),
            ],
            politica,
        )
        assert any(f.invariante == "genero_con_arista" for f in verificar(roto, politica, grafo))

    def test_lo_detecta_tambien_en_emergencia(self, politica, grafo):
        roto = self._plan_de(
            [
                pista("x1", genero="cumbia", bpm=98.0, artista="A"),
                pista("x2", genero="techno", bpm=98.0, artista="B"),
            ],
            politica,
            emergencia=True,
        )
        assert any(f.invariante == "genero_con_arista" for f in verificar(roto, politica, grafo))

    def test_detecta_la_costura_fuera_de_tolerancia(self, politica, grafo):
        roto = self._plan_de(
            [
                pista("x1", genero="cumbia", bpm=95.0, artista="A"),
                pista("x2", genero="cumbia", bpm=104.0, artista="B"),  # +9,5%
            ],
            politica,
        )
        assert any(
            f.invariante == "costura_dentro_de_tolerancia" for f in verificar(roto, politica, grafo)
        )

    def test_detecta_la_costura_con_material_no_apto(self, politica, grafo):
        roto = self._plan_de(
            [
                pista("x1", genero="cumbia", bpm=98.0, artista="A"),
                pista("x2", genero="cumbia", bpm=99.0, artista="B", apta=False),
            ],
            politica,
        )
        assert any(
            f.invariante == "costura_solo_entre_aptas" for f in verificar(roto, politica, grafo)
        )

    def test_detecta_el_artista_repetido(self, politica, grafo):
        roto = self._plan_de(
            [
                pista("x1", genero="cumbia", bpm=98.0, artista="Duki"),
                pista("x2", genero="cumbia", bpm=99.0, artista="Duki"),
            ],
            politica,
        )
        assert any(
            f.invariante == "sin_artista_consecutivo" for f in verificar(roto, politica, grafo)
        )

    def test_el_artista_repetido_se_tolera_en_emergencia(self, politica, grafo):
        tolerado = self._plan_de(
            [
                pista("x1", genero="cumbia", bpm=98.0, artista="Duki"),
                pista("x2", genero="cumbia", bpm=99.0, artista="Duki"),
            ],
            politica,
            emergencia=True,
        )
        assert not any(
            f.invariante == "sin_artista_consecutivo" for f in verificar(tolerado, politica, grafo)
        )

    def test_detecta_el_tema_de_la_lista_negra(self, grafo):
        politica = PoliticaNoche(
            nombre="con_veto", fases=politica_boliche().fases, lista_negra=frozenset({"x2"})
        )
        roto = self._plan_de(
            [
                pista("x1", genero="cumbia", bpm=98.0, artista="A"),
                pista("x2", genero="cumbia", bpm=99.0, artista="B"),
            ],
            politica,
        )
        assert any(f.invariante == "sin_lista_negra" for f in verificar(roto, politica, grafo))

    def test_detecta_la_deriva_de_tempo_de_la_fase(self, politica, grafo):
        # la fase "apertura" apunta a 96 BPM; este plan se va a 130
        roto = self._plan_de(
            [
                pista(f"x{i}", genero="cuarteto", bpm=130.0 + i, artista=f"A{i}")
                for i in range(5)
            ],
            politica,
        )
        assert any(f.invariante == "bpm_promedio_de_fase" for f in verificar(roto, politica, grafo))

    def test_un_plan_sano_no_dispara_nada(self, politica, grafo):
        sano = self._plan_de(
            [
                pista("x1", genero="cumbia", bpm=95.0, artista="A"),
                pista("x2", genero="cumbia", bpm=96.5, artista="B"),
                pista("x3", genero="cumbia_420", bpm=97.0, artista="C"),
            ],
            politica,
        )
        assert verificar(sano, politica, grafo) == []

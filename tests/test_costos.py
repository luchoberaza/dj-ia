from __future__ import annotations

import pytest

from dj.costos import Pesos, costo_energia, evaluar_transicion
from dj.dominio import GrafoGeneros, TipoTransicion

from ayudas import pista


@pytest.fixture
def grafo():
    return GrafoGeneros(
        {
            ("a", "b"): 0.2,  # géneros vecinos
            ("b", "a"): 0.2,
            ("a", "c"): 0.7,  # cambio de bloque
            ("c", "a"): 0.7,
        }
    )


def evaluar(desde, hacia, grafo, **kwargs):
    kwargs.setdefault("energia_objetivo", 6.0)
    return evaluar_transicion(desde, hacia, grafo=grafo, **kwargs)


class TestTipoDeTransicion:
    def test_temas_cercanos_en_todo_dan_costura_larga(self, grafo):
        a = pista("a", genero="a", bpm=124.0, camelot="8A")
        b = pista("b", genero="a", bpm=125.0, camelot="9A")
        tipo, _ = evaluar(a, b, grafo)
        assert tipo is TipoTransicion.COSTURA_LARGA

    def test_diferencia_de_tempo_media_da_costura_corta(self, grafo):
        a = pista("a", genero="a", bpm=120.0, camelot="8A")
        b = pista("b", genero="a", bpm=125.0, camelot="8A")  # +4.2%
        tipo, _ = evaluar(a, b, grafo)
        assert tipo is TipoTransicion.COSTURA_CORTA

    def test_tonalidad_que_choca_impide_la_costura_larga(self, grafo):
        a = pista("a", genero="a", bpm=124.0, camelot="8A")
        b = pista("b", genero="a", bpm=124.5, camelot="2A")
        tipo, _ = evaluar(a, b, grafo)
        assert tipo is TipoTransicion.COSTURA_CORTA

    def test_salto_grande_de_tempo_fuerza_corte(self, grafo):
        a = pista("a", genero="a", bpm=128.0)
        b = pista("b", genero="a", bpm=100.0)
        tipo, _ = evaluar(a, b, grafo)
        assert not tipo.es_costura

    def test_material_no_costurable_fuerza_corte(self, grafo):
        a = pista("a", genero="a", bpm=124.0)
        b = pista("b", genero="a", bpm=124.5, apta=False)
        tipo, _ = evaluar(a, b, grafo)
        assert tipo is TipoTransicion.CORTE_BREAK

    def test_cambio_de_bloque_da_corte_con_puente(self, grafo):
        a = pista("a", genero="a", bpm=124.0)
        b = pista("b", genero="c", bpm=100.0)
        tipo, _ = evaluar(a, b, grafo)
        assert tipo is TipoTransicion.CORTE_PUENTE


class TestCosto:
    def test_cortar_por_material_cuesta_menos_que_cortar_por_salto(self, grafo):
        base = pista("a", genero="a", bpm=124.0, camelot="8A")
        inevitable = pista("b", genero="a", bpm=124.5, camelot="8A", apta=False)
        por_salto = pista("c", genero="a", bpm=100.0, camelot="8A")
        _, d_inevitable = evaluar(base, inevitable, grafo)
        _, d_salto = evaluar(base, por_salto, grafo)
        assert d_inevitable.costura < d_salto.costura

    def test_la_deseabilidad_baja_el_costo(self, grafo):
        a = pista("a", genero="a", bpm=124.0)
        b = pista("b", genero="a", bpm=125.0)
        _, sin_votos = evaluar(a, b, grafo, deseabilidad=0.0)
        _, con_votos = evaluar(a, b, grafo, deseabilidad=1.0)
        assert con_votos.costo_total < sin_votos.costo_total

    def test_cambiar_de_genero_cuesta_mas_que_quedarse(self, grafo):
        a = pista("a", genero="a", bpm=124.0, camelot="8A")
        mismo = pista("b", genero="a", bpm=124.5, camelot="8A")
        otro = pista("c", genero="b", bpm=124.5, camelot="8A")
        _, d_mismo = evaluar(a, mismo, grafo)
        _, d_otro = evaluar(a, otro, grafo)
        assert d_otro.costo_total > d_mismo.costo_total

    def test_genero_sin_arista_es_un_error_de_programacion(self, grafo):
        a = pista("a", genero="b", bpm=124.0)
        b = pista("b", genero="c", bpm=124.5)
        with pytest.raises(ValueError, match="no hay arista"):
            evaluar(a, b, grafo)

    def test_primer_tema_de_la_noche_no_necesita_anterior(self, grafo):
        b = pista("b", genero="a", bpm=96.0)
        tipo, desglose = evaluar(None, b, grafo)
        assert tipo is TipoTransicion.CORTE_PUENTE
        assert desglose.tempo == 0.0


class TestCostoEnergia:
    def test_dar_en_el_objetivo_es_gratis(self):
        assert costo_energia(7.0, 7.0, es_build=False) == 0.0

    def test_bajar_cuesta_mas_que_subir_durante_el_build(self):
        subir = costo_energia(9.0, 7.0, es_build=True)
        bajar = costo_energia(5.0, 7.0, es_build=True)
        assert bajar > subir

    def test_el_build_castiga_bajar_mas_que_la_meseta(self):
        assert costo_energia(5.0, 7.0, es_build=True) > costo_energia(5.0, 7.0, es_build=False)


class TestPesos:
    def test_el_genero_pesa_mas_que_la_tonalidad(self):
        # "aburrido pero nunca mal": romper el género es peor que una tonalidad fea
        pesos = Pesos()
        assert pesos.genero > pesos.tonal

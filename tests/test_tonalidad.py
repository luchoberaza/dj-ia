from __future__ import annotations

import pytest

from dj.tonalidad import (
    CHOQUE,
    MISMO,
    RELATIVA,
    SUBIDON,
    VECINO,
    compatibilidad,
    compatibles,
    costo_tonal,
    parsear,
)


class TestParseo:
    @pytest.mark.parametrize("codigo,esperado", [("8A", (8, "A")), ("12b", (12, "B")), (" 1A ", (1, "A"))])
    def test_codigos_validos(self, codigo, esperado):
        assert parsear(codigo) == esperado

    @pytest.mark.parametrize("codigo", ["0A", "13A", "8C", "A8", "", None, "ocho"])
    def test_codigos_invalidos(self, codigo):
        assert parsear(codigo) is None


class TestCompatibilidad:
    def test_misma_tonalidad_es_perfecta(self):
        assert compatibilidad("8A", "8A") == MISMO

    def test_vecino_en_la_rueda(self):
        assert compatibilidad("8A", "9A") == VECINO
        assert compatibilidad("8A", "7A") == VECINO

    def test_relativa_mayor_menor(self):
        assert compatibilidad("8A", "8B") == RELATIVA

    def test_subidon_de_dos_pasos(self):
        assert compatibilidad("8A", "10A") == SUBIDON

    def test_bajar_dos_pasos_no_es_el_subidon(self):
        assert compatibilidad("8A", "6A") == CHOQUE

    def test_tonalidades_lejanas_chocan(self):
        assert compatibilidad("8A", "2A") == CHOQUE
        assert compatibilidad("8A", "3B") == CHOQUE

    def test_la_rueda_da_la_vuelta(self):
        assert compatibilidad("12A", "1A") == VECINO
        assert compatibilidad("1A", "12A") == VECINO
        assert compatibilidad("12A", "2A") == SUBIDON

    def test_compatibles_acepta_los_movimientos_estandar(self):
        assert compatibles("8A", "8A")
        assert compatibles("8A", "9A")
        assert compatibles("8A", "8B")
        assert not compatibles("8A", "2A")


class TestCostoTonal:
    def test_se_neutraliza_si_falta_la_tonalidad(self):
        costo, neutralizado = costo_tonal(None, "8A")
        assert (costo, neutralizado) == (0.0, True)

    def test_se_neutraliza_con_confianza_baja(self):
        # no se penaliza por un dato que no se conoce: eso sería inventar
        costo, neutralizado = costo_tonal("8A", "2A", confianza_a=0.9, confianza_b=0.2)
        assert (costo, neutralizado) == (0.0, True)

    def test_penaliza_cuando_hay_confianza(self):
        costo, neutralizado = costo_tonal("8A", "2A", confianza_a=0.9, confianza_b=0.9)
        assert costo == CHOQUE
        assert neutralizado is False

    def test_codigo_basura_se_neutraliza(self):
        assert costo_tonal("no-es-camelot", "8A") == (0.0, True)

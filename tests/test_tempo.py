"""El módulo de tempo es la base de todo: si la octava está mal, el motor ve abismos
donde hay autopistas."""

from __future__ import annotations

import pytest

from dj.tempo import (
    LIBRE_BPM,
    PROHIBITIVO,
    TOLERANCIA_COSTURA,
    costo_tempo,
    costurable_por_tempo,
    diferencia_relativa,
    equivalente_octava,
)


class TestEquivalenteOctava:
    def test_mismo_bpm_es_identidad(self):
        assert equivalente_octava(128.0, 128.0) == pytest.approx(128.0)

    def test_doble_tiempo_se_baja_a_la_octava_cercana(self):
        # 190 contra 128: el pulso percibido es 95, no 190
        assert equivalente_octava(128.0, 190.0) == pytest.approx(95.0)

    def test_medio_tiempo_se_sube(self):
        assert equivalente_octava(96.0, 48.0) == pytest.approx(96.0)

    def test_cumbia_y_salsa_al_doble_son_el_mismo_pulso(self):
        # una salsa a 190 contra una cumbia a 95: distancia cero, no 95 BPM de abismo
        assert diferencia_relativa(95.0, 190.0) == pytest.approx(0.0)

    def test_rechaza_bpm_no_positivos(self):
        with pytest.raises(ValueError):
            equivalente_octava(0.0, 120.0)
        with pytest.raises(ValueError):
            equivalente_octava(120.0, -1.0)


class TestDiferenciaRelativa:
    def test_signo_positivo_si_acelera(self):
        assert diferencia_relativa(120.0, 126.0) > 0

    def test_signo_negativo_si_desacelera(self):
        assert diferencia_relativa(126.0, 120.0) < 0

    def test_es_porcentaje_del_tempo_de_origen(self):
        # 3 BPM pesan mucho más a 95 que a 140
        assert abs(diferencia_relativa(95.0, 98.0)) > abs(diferencia_relativa(140.0, 143.0))


class TestCostoTempo:
    def test_hasta_tres_bpm_es_gratis(self):
        costo, _, _ = costo_tempo(120.0, 120.0 + LIBRE_BPM - 0.1)
        assert costo == 0.0

    def test_crece_de_forma_monotona_dentro_del_rango(self):
        costos = [costo_tempo(120.0, 120.0 * (1 + d))[0] for d in (0.03, 0.04, 0.05)]
        assert costos == sorted(costos)
        assert all(c < PROHIBITIVO for c in costos)

    def test_seis_por_ciento_es_el_limite(self):
        justo_abajo, _, _ = costo_tempo(120.0, 120.0 * (1 + TOLERANCIA_COSTURA - 0.001))
        justo_arriba, _, _ = costo_tempo(120.0, 120.0 * (1 + TOLERANCIA_COSTURA + 0.001))
        assert justo_abajo < PROHIBITIVO
        assert justo_arriba == PROHIBITIVO

    def test_es_simetrico_en_magnitud(self):
        subir, _, _ = costo_tempo(120.0, 124.0)
        bajar, _, _ = costo_tempo(120.0, 116.0)
        assert subir == pytest.approx(bajar, rel=0.15)

    def test_bpm_muy_bajo_no_divide_por_cero(self):
        costo, _, _ = costo_tempo(40.0, 44.0)
        assert costo in (0.0, PROHIBITIVO) or 0.0 < costo < PROHIBITIVO


class TestCosturable:
    def test_salto_chico_es_costurable(self):
        assert costurable_por_tempo(124.0, 127.0)

    def test_salto_grande_no_es_costurable(self):
        assert not costurable_por_tempo(128.0, 95.0)

    def test_salto_grande_pero_de_octava_si_es_costurable(self):
        assert costurable_por_tempo(128.0, 254.0)

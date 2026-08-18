"""Las restricciones duras no se negocian. Estos tests son el contrato."""

from __future__ import annotations

from ayudas import pista

from dj.dominio import EstadoNoche, Fase, GrafoGeneros, PoliticaNoche
from dj.restricciones import (
    INNEGOCIABLES,
    ORDEN_RELAJACION,
    evaluar,
    relajaciones_hasta,
)

GRAFO = GrafoGeneros({("a", "b"): 0.3, ("b", "a"): 0.3})
FASE = Fase("normal", 0, 120, 6.0)
FASE_PICO = Fase("pico", 0, 126, 9.0, permite_bajar_bpm=False)
POLITICA = PoliticaNoche(
    nombre="test",
    fases=(FASE,),
    cooldown_tema_min=240.0,
    cooldown_artista_min=45.0,
    max_por_artista_por_hora=2,
    max_concesiones_voto_por_hora=2,
)


def estado_con(actual=None, minuto=100.0, historial=()):
    estado = EstadoNoche(minuto=0.0)
    for p in historial:
        estado = estado.avanzar(p)
    if actual is not None and (not historial or historial[-1] is not actual):
        estado = estado.avanzar(actual)
    return EstadoNoche(
        minuto=max(minuto, estado.minuto),
        actual=estado.actual,
        ultimo_minuto_pista=estado.ultimo_minuto_pista,
        minutos_artista=estado.minutos_artista,
        concesiones=estado.concesiones,
    )


class TestInnegociables:
    def test_lista_negra_bloquea_por_id(self):
        vetada = pista("x", genero="a")
        politica = PoliticaNoche(nombre="t", fases=(FASE,), lista_negra=frozenset({"x"}))
        violacion = evaluar(vetada, EstadoNoche(), politica, FASE, GRAFO)
        assert violacion is not None and violacion.regla == "lista_negra"

    def test_lista_negra_bloquea_por_isrc(self):
        vetada = pista("x", genero="a", isrc="AR123")
        politica = PoliticaNoche(nombre="t", fases=(FASE,), lista_negra=frozenset({"AR123"}))
        violacion = evaluar(vetada, EstadoNoche(), politica, FASE, GRAFO)
        assert violacion is not None and violacion.regla == "lista_negra"

    def test_genero_sin_arista_es_el_corazon_del_producto(self):
        # "de la nada te cambia completamente de género": estructuralmente imposible
        actual = pista("a1", genero="a", bpm=120.0)
        candidata = pista("z1", genero="z", bpm=120.0)
        violacion = evaluar(candidata, estado_con(actual), POLITICA, FASE, GRAFO)
        assert violacion is not None and violacion.regla == "genero_sin_arista"

    def test_ninguna_relajacion_habilita_las_innegociables(self):
        actual = pista("a1", genero="a", bpm=120.0)
        candidata = pista("z1", genero="z", bpm=120.0)
        todas = frozenset(ORDEN_RELAJACION)
        violacion = evaluar(
            candidata, estado_con(actual), POLITICA, FASE, GRAFO, relajaciones=todas
        )
        assert violacion is not None and violacion.regla == "genero_sin_arista"

    def test_las_innegociables_no_estan_en_el_orden_de_relajacion(self):
        assert INNEGOCIABLES.isdisjoint(ORDEN_RELAJACION)


class TestArtista:
    def test_no_dos_veces_seguidas(self):
        actual = pista("a1", genero="a", bpm=120.0, artista="Duki")
        candidata = pista("a2", genero="a", bpm=120.0, artista="Duki")
        violacion = evaluar(candidata, estado_con(actual), POLITICA, FASE, GRAFO)
        assert violacion is not None and violacion.regla == "artista_consecutivo"

    def test_cooldown_de_artista(self):
        previa = pista("a1", genero="a", bpm=120.0, artista="Duki", duracion_s=180)
        otra = pista("a9", genero="a", bpm=120.0, artista="Otro", duracion_s=180)
        candidata = pista("a2", genero="a", bpm=120.0, artista="Duki")
        estado = estado_con(minuto=6.0, historial=(previa, otra))
        violacion = evaluar(candidata, estado, POLITICA, FASE, GRAFO)
        assert violacion is not None and violacion.regla == "cooldown_artista"

    def test_el_cooldown_de_artista_se_puede_relajar(self):
        previa = pista("a1", genero="a", bpm=120.0, artista="Duki", duracion_s=180)
        otra = pista("a9", genero="a", bpm=120.0, artista="Otro", duracion_s=180)
        candidata = pista("a2", genero="a", bpm=120.0, artista="Duki")
        estado = estado_con(minuto=6.0, historial=(previa, otra))
        assert (
            evaluar(
                candidata,
                estado,
                POLITICA,
                FASE,
                GRAFO,
                relajaciones=frozenset({"cooldown_artista"}),
            )
            is None
        )


class TestCooldownDeTema:
    def test_no_se_repite_dentro_de_la_ventana(self):
        tema = pista("a1", genero="a", bpm=120.0, duracion_s=180)
        estado = estado_con(minuto=60.0, historial=(tema, pista("a2", genero="a", bpm=120.0)))
        violacion = evaluar(tema, estado, POLITICA, FASE, GRAFO)
        assert violacion is not None and violacion.regla == "cooldown_tema"

    def test_no_se_puede_relajar_el_cooldown_de_tema(self):
        tema = pista("a1", genero="a", bpm=120.0, duracion_s=180)
        estado = estado_con(minuto=60.0, historial=(tema, pista("a2", genero="a", bpm=120.0)))
        violacion = evaluar(
            tema, estado, POLITICA, FASE, GRAFO, relajaciones=frozenset(ORDEN_RELAJACION)
        )
        assert violacion is not None and violacion.regla == "cooldown_tema"


class TestFase:
    def test_genero_fuera_de_la_fase(self):
        fase = Fase("solo_a", 0, 120, 6.0, generos_permitidos=frozenset({"a"}))
        candidata = pista("b1", genero="b", bpm=120.0)
        actual = pista("a1", genero="a", bpm=120.0)
        violacion = evaluar(candidata, estado_con(actual), POLITICA, fase, GRAFO)
        assert violacion is not None and violacion.regla == "genero_no_permitido"

    def test_en_el_pico_no_se_baja_el_bpm(self):
        actual = pista("a1", genero="a", bpm=128.0)
        candidata = pista("a2", genero="a", bpm=120.0)
        violacion = evaluar(candidata, estado_con(actual), POLITICA, FASE_PICO, GRAFO)
        assert violacion is not None and violacion.regla == "baja_bpm_en_pico"

    def test_en_el_pico_subir_esta_permitido(self):
        actual = pista("a1", genero="a", bpm=128.0)
        candidata = pista("a2", genero="a", bpm=131.0)
        assert evaluar(candidata, estado_con(actual), POLITICA, FASE_PICO, GRAFO) is None

    def test_el_pico_razona_modulo_octava(self):
        # 258 BPM contra 128 se percibe como 129: sube, no baja
        actual = pista("a1", genero="a", bpm=128.0)
        candidata = pista("a2", genero="a", bpm=258.0)
        assert evaluar(candidata, estado_con(actual), POLITICA, FASE_PICO, GRAFO) is None


class TestCupoDeVoto:
    def test_el_voto_tiene_techo_por_hora(self):
        estado = EstadoNoche(minuto=30.0, actual=pista("a1", genero="a", bpm=120.0))
        estado = EstadoNoche(
            minuto=30.0,
            actual=estado.actual,
            concesiones=(5.0, 10.0),  # ya son 2, el máximo de la política
        )
        candidata = pista("a2", genero="a", bpm=120.0)
        violacion = evaluar(candidata, estado, POLITICA, FASE, GRAFO, cede_al_voto=True)
        assert violacion is not None and violacion.regla == "cupo_voto"

    def test_sin_ceder_al_voto_el_cupo_no_aplica(self):
        estado = EstadoNoche(
            minuto=30.0,
            actual=pista("a1", genero="a", bpm=120.0),
            concesiones=(5.0, 10.0),
        )
        candidata = pista("a2", genero="a", bpm=120.0)
        assert evaluar(candidata, estado, POLITICA, FASE, GRAFO, cede_al_voto=False) is None


class TestRelajacionesHasta:
    def test_nivel_cero_no_relaja_nada(self):
        assert relajaciones_hasta(0) == frozenset()

    def test_respeta_el_orden_declarado(self):
        assert relajaciones_hasta(1) == frozenset({ORDEN_RELAJACION[0]})
        assert relajaciones_hasta(2) == frozenset(ORDEN_RELAJACION[:2])

    def test_no_se_pasa_del_final(self):
        assert relajaciones_hasta(99) == frozenset(ORDEN_RELAJACION)

"""La auditoría de configuración: los hallazgos H2 y H4 convertidos en chequeo.

El test central de este archivo es una regresión sobre un bug real: el grafo con el que
se construyó la etapa 1 tenía una trampa de tempo que dejó a la fase de build 8% abajo
de su objetivo, y nos costó una auditoría manual descubrirla. Ahora se detecta sola.
"""

from __future__ import annotations

from ayudas import pista

from dj.auditoria import (
    auditar,
    generos_que_sirven,
    ruta_monotona,
    tempos_por_genero,
)
from dj.catalogo_demo import ARISTAS_BOLICHE, catalogo_demo, grafo_boliche, politica_boliche
from dj.dominio import Fase, GrafoGeneros, PoliticaNoche

#: El grafo tal como estaba antes de descubrir H2: sin los puentes hacia dembow, la
#: única forma de subir de 105 a 126 BPM pasaba por reggaetón, que está más abajo.
ARISTAS_CON_TRAMPA = {
    par: costo
    for par, costo in ARISTAS_BOLICHE.items()
    if par
    not in {
        ("cumbia_420", "dembow"),
        ("dembow", "cumbia_420"),
        ("pop_latino", "dembow"),
        ("dembow", "pop_latino"),
    }
}


class TestTrampaDeTempo:
    def test_detecta_la_trampa_que_tuvimos_de_verdad(self):
        catalogo = catalogo_demo(1200, semilla=17)
        advertencias = auditar(
            list(catalogo), politica_boliche(), GrafoGeneros(dict(ARISTAS_CON_TRAMPA))
        )
        trampas = [a for a in advertencias if a.tipo == "trampa_de_tempo"]
        assert trampas, "no detectó la trampa de tempo que le costó 8% a la fase de build"
        assert all(a.gravedad == "bloqueante" for a in trampas)

    def test_el_grafo_corregido_ya_no_la_tiene(self):
        catalogo = catalogo_demo(1200, semilla=17)
        advertencias = auditar(list(catalogo), politica_boliche(), grafo_boliche())
        assert not [a for a in advertencias if a.tipo == "trampa_de_tempo"]

    def test_el_mensaje_dice_entre_que_generos_falta_el_puente(self):
        catalogo = catalogo_demo(1200, semilla=17)
        trampas = [
            a
            for a in auditar(
                list(catalogo), politica_boliche(), GrafoGeneros(dict(ARISTAS_CON_TRAMPA))
            )
            if a.tipo == "trampa_de_tempo"
        ]
        assert "falta un puente" in trampas[0].detalle


class TestRutaMonotona:
    def test_encuentra_una_subida_limpia(self):
        grafo = GrafoGeneros({("a", "b"): 0.2, ("b", "c"): 0.2})
        tempos = {"a": 100.0, "b": 112.0, "c": 126.0}
        assert ruta_monotona(grafo, tempos, ["a"], ["c"], subiendo=True) == ["a", "b", "c"]

    def test_rechaza_el_camino_que_pasa_por_un_pozo(self):
        grafo = GrafoGeneros({("a", "b"): 0.2, ("b", "c"): 0.2})
        tempos = {"a": 105.0, "b": 92.0, "c": 126.0}  # hay que bajar para poder subir
        assert ruta_monotona(grafo, tempos, ["a"], ["c"], subiendo=True) is None

    def test_tolera_un_movimiento_lateral_chico(self):
        grafo = GrafoGeneros({("a", "b"): 0.2, ("b", "c"): 0.2})
        tempos = {"a": 100.0, "b": 99.0, "c": 126.0}  # -1%: lateral, no pozo
        assert ruta_monotona(grafo, tempos, ["a"], ["c"], subiendo=True) is not None

    def test_tambien_audita_bajadas(self):
        grafo = GrafoGeneros({("a", "b"): 0.2})
        tempos = {"a": 126.0, "b": 100.0}
        assert ruta_monotona(grafo, tempos, ["a"], ["b"], subiendo=False) == ["a", "b"]
        assert ruta_monotona(grafo, tempos, ["a"], ["b"], subiendo=True) is None

    def test_origen_y_destino_iguales_es_ruta_trivial(self):
        grafo = GrafoGeneros({("a", "b"): 0.2})
        assert ruta_monotona(grafo, {"a": 100.0}, ["a"], ["a"], subiendo=True) == ["a"]


class TestProfundidadPorFase:
    def test_detecta_el_catalogo_sin_material_de_pico(self):
        """H4: el cuello de botella no es el tamaño total, es la profundidad por fase."""
        solo_lento = [
            pista(f"c{i}", genero="cumbia", bpm=95.0 + (i % 8), artista=f"a{i}")
            for i in range(900)
        ]
        politica = politica_boliche()
        advertencias = auditar(solo_lento, politica, grafo_boliche())
        faltantes = [a for a in advertencias if a.tipo == "profundidad_de_fase"]
        assert any("pico" in a.detalle for a in faltantes)

    def test_el_mensaje_es_la_lista_de_compras(self):
        solo_lento = [
            pista(f"c{i}", genero="cumbia", bpm=95.0, artista=f"a{i}") for i in range(900)
        ]
        faltantes = [
            a
            for a in auditar(solo_lento, politica_boliche(), grafo_boliche())
            if a.tipo == "profundidad_de_fase" and "pico" in a.detalle
        ]
        assert "BPM" in faltantes[0].detalle and "Faltan temas entre" in faltantes[0].detalle

    def test_un_catalogo_completo_no_dispara_faltantes(self):
        catalogo = catalogo_demo(1200, semilla=17)
        advertencias = auditar(list(catalogo), politica_boliche(), grafo_boliche())
        assert not [a for a in advertencias if a.gravedad == "bloqueante"]

    def test_avisa_cuando_una_fase_es_monocultivo(self):
        una_sola = [
            pista(f"c{i}", genero="cumbia", bpm=96.0, artista=f"a{i}") for i in range(400)
        ]
        politica = PoliticaNoche(nombre="corta", fases=(Fase("unica", 0, 96, 5.0),))
        advertencias = auditar(una_sola, politica, grafo_boliche(), duracion_noche_min=60.0)
        assert any(a.tipo == "monocultivo_de_fase" for a in advertencias)


class TestUtilidades:
    def test_el_tempo_por_genero_usa_la_mediana(self):
        """Un tema mal analizado al doble de tiempo arrastra el promedio, no la mediana."""
        catalogo = [
            pista("a", genero="cumbia", bpm=95.0),
            pista("b", genero="cumbia", bpm=97.0),
            pista("c", genero="cumbia", bpm=99.0),
            pista("mal", genero="cumbia", bpm=194.0),  # octava equivocada
        ]
        assert tempos_por_genero(catalogo)["cumbia"] == 98.0

    def test_generos_que_sirven_respeta_los_permitidos_de_la_fase(self):
        catalogo = [
            pista("a", genero="cumbia", bpm=96.0),
            pista("b", genero="cuarteto", bpm=96.0),
        ]
        fase = Fase("solo_cumbia", 0, 96, 5.0, generos_permitidos=frozenset({"cumbia"}))
        assert generos_que_sirven(catalogo, fase) == {"cumbia": 1}

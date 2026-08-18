"""El destilador tiene que recuperar patrones que pusimos a propósito en el corpus.

Nada de estos tests mide gusto: miden que la máquina que extrae el gusto de los datos
extraiga lo que hay. El corpus de prueba es sintético y sus números no significan nada
sobre música real.
"""

from __future__ import annotations

import pytest

from dj.corpus import Corpus, SetGrabado, TemaDeSet, cargar, cobertura, guardar
from dj.destilacion import COSTO_MINIMO, destilar


def _set(id_set: str, temas: list[dict], escena: str | None = None) -> SetGrabado:
    return SetGrabado(
        id=id_set,
        escena=escena,
        temas=tuple(TemaDeSet(posicion=i + 1, **t) for i, t in enumerate(temas)),
    )


def _corpus_de_generos(secuencias: list[list[str]]) -> Corpus:
    return Corpus(
        tuple(
            _set(f"s{i}", [{"genero": g, "titulo": f"t{j}"} for j, g in enumerate(seq)])
            for i, seq in enumerate(secuencias)
        )
    )


class TestGrafoDestilado:
    def test_aprende_las_transiciones_que_se_repiten(self):
        corpus = _corpus_de_generos([["a", "b"]] * 20)
        destilado = destilar(corpus)
        assert destilado.grafo.hay_arista("a", "b")

    def test_descarta_lo_que_pasa_una_sola_vez(self):
        """Un DJ haciendo algo raro una noche no puede volverse una regla del motor."""
        corpus = _corpus_de_generos([["a", "b"]] * 20 + [["a", "z"]])
        destilado = destilar(corpus)
        assert destilado.grafo.hay_arista("a", "b")
        assert not destilado.grafo.hay_arista("a", "z")
        assert ("a", "z") in destilado.aristas_descartadas

    def test_lo_descartado_queda_reportado(self):
        """Esconder lo que se tiró sería el recorte silencioso que el diseño prohíbe."""
        corpus = _corpus_de_generos([["a", "b"]] * 20 + [["a", "z"], ["a", "z"]])
        destilado = destilar(corpus)
        assert destilado.aristas_descartadas[("a", "z")] == 2
        assert "descartadas por umbral" in destilado.informe()

    def test_lo_mas_transitado_sale_mas_barato(self):
        corpus = _corpus_de_generos([["a", "b"]] * 50 + [["a", "c"]] * 5)
        destilado = destilar(corpus)
        assert destilado.grafo.costo("a", "b") < destilado.grafo.costo("a", "c")

    def test_la_arista_dominante_toca_el_costo_minimo(self):
        corpus = _corpus_de_generos([["a", "b"]] * 50)
        assert destilar(corpus).grafo.costo("a", "b") == pytest.approx(COSTO_MINIMO, abs=0.01)

    def test_el_grafo_es_dirigido(self):
        """Que se pase de cumbia a cuarteto no implica que se vuelva."""
        corpus = _corpus_de_generos([["a", "b"]] * 20)
        destilado = destilar(corpus)
        assert destilado.grafo.hay_arista("a", "b")
        assert not destilado.grafo.hay_arista("b", "a")

    def test_quedarse_en_el_mismo_genero_no_genera_arista(self):
        corpus = _corpus_de_generos([["a", "a", "a"]] * 20)
        assert destilar(corpus).grafo.aristas == {}

    def test_el_umbral_es_configurable(self):
        corpus = _corpus_de_generos([["a", "b"]] * 20 + [["a", "z"]])
        laxo = destilar(corpus, minimo_apariciones=1, proporcion_minima=0.0)
        assert laxo.grafo.hay_arista("a", "z")


class TestSaltosDeTempo:
    def test_mide_la_distribucion_real(self):
        # 150 transiciones de exactamente +2% y 50 de +10%
        temas_chico = [{"genero": "a", "bpm": 120.0}, {"genero": "a", "bpm": 122.4}]
        temas_grande = [{"genero": "a", "bpm": 120.0}, {"genero": "a", "bpm": 132.0}]
        corpus = Corpus(
            tuple([_set(f"c{i}", temas_chico) for i in range(150)])
            + tuple([_set(f"g{i}", temas_grande) for i in range(50)])
        )
        s = destilar(corpus).saltos_tempo
        assert s.muestras == 200
        assert s.p50 == pytest.approx(0.02, abs=0.005)
        assert s.p99 == pytest.approx(0.10, abs=0.005)
        assert s.proporcion_bajo_6pct == pytest.approx(0.75, abs=0.01)
        assert s.maximo == pytest.approx(0.10, abs=0.005)

    def test_razona_modulo_octava(self):
        """120 → 240 es distancia cero, no un salto del 100%."""
        corpus = Corpus(
            tuple(
                _set(f"s{i}", [{"genero": "a", "bpm": 120.0}, {"genero": "a", "bpm": 240.0}])
                for i in range(10)
            )
        )
        assert destilar(corpus).saltos_tempo.maximo == pytest.approx(0.0, abs=1e-9)

    def test_el_veredicto_avisa_cuando_la_muestra_no_alcanza(self):
        corpus = Corpus((_set("s1", [{"bpm": 120.0}, {"bpm": 124.0}]),))
        assert "muestra insuficiente" in destilar(corpus).saltos_tempo.veredicto_sobre_tolerancia()

    def test_el_veredicto_detecta_una_tolerancia_conservadora(self):
        temas = [{"bpm": 120.0}, {"bpm": 132.0}]  # +10%
        corpus = Corpus(tuple(_set(f"s{i}", temas) for i in range(200)))
        veredicto = destilar(corpus).saltos_tempo.veredicto_sobre_tolerancia(0.06)
        assert "conservadora" in veredicto

    def test_el_veredicto_detecta_una_tolerancia_generosa(self):
        temas = [{"bpm": 120.0}, {"bpm": 121.2}]  # +1%
        corpus = Corpus(tuple(_set(f"s{i}", temas) for i in range(200)))
        assert "generosa" in destilar(corpus).saltos_tempo.veredicto_sobre_tolerancia(0.06)


class TestCamelot:
    def test_clasifica_los_movimientos(self):
        corpus = Corpus(
            (
                _set("s1", [{"camelot": "8A"}, {"camelot": "8A"}]),  # mismo
                _set("s2", [{"camelot": "8A"}, {"camelot": "9A"}]),  # vecino
                _set("s3", [{"camelot": "8A"}, {"camelot": "8B"}]),  # relativa
                _set("s4", [{"camelot": "8A"}, {"camelot": "10A"}]),  # subidon
                _set("s5", [{"camelot": "8A"}, {"camelot": "2A"}]),  # choque
            )
        )
        movimientos = destilar(corpus).movimientos_camelot
        assert movimientos == {
            "mismo": 1,
            "vecino": 1,
            "relativa": 1,
            "subidon": 1,
            "choque": 1,
        }

    def test_ignora_los_temas_sin_tonalidad(self):
        corpus = Corpus((_set("s1", [{"camelot": "8A"}, {"titulo": "sin tonalidad"}]),))
        assert destilar(corpus).movimientos_camelot == {}


class TestCurvas:
    def test_recupera_una_curva_ascendente(self):
        subiendo = [{"bpm": 100.0 + i * 2} for i in range(20)]
        corpus = Corpus(tuple(_set(f"s{i}", subiendo) for i in range(10)))
        curva = destilar(corpus).curva_tempo
        assert curva[0] < 0 < curva[-1]
        assert list(curva) == sorted(curva)

    def test_la_curva_de_tempo_es_relativa_al_set(self):
        """Promediar en absoluto un set de techno con uno de cumbia no describe a ninguno."""
        lento = [{"bpm": 90.0 + i} for i in range(20)]
        rapido = [{"bpm": 170.0 + i * 2} for i in range(20)]
        corpus = Corpus((_set("lento", lento), _set("rapido", rapido)))
        curva = destilar(corpus).curva_tempo
        assert all(-1.0 < v < 1.0 for v in curva)  # son desvíos, no BPM

    def test_la_energia_se_promedia_en_absoluto(self):
        temas = [{"energia": 5.0} for _ in range(20)]
        corpus = Corpus(tuple(_set(f"s{i}", temas) for i in range(5)))
        assert all(v == pytest.approx(5.0) for v in destilar(corpus).curva_energia)


class TestCobertura:
    def test_reporta_la_cobertura_de_cada_campo(self):
        corpus = Corpus(
            (_set("s1", [{"genero": "a", "bpm": 120.0}, {"genero": "a"}]),)
        )
        assert cobertura(corpus, "genero") == 1.0
        assert cobertura(corpus, "bpm") == 0.5
        assert cobertura(corpus, "camelot") == 0.0

    def test_el_informe_declara_la_cobertura(self):
        """500 sets con 30% de BPM no son 500 sets con tempo. Decirlo o mentir por omisión."""
        corpus = _corpus_de_generos([["a", "b"]] * 20)
        informe = destilar(corpus).informe()
        assert "Cobertura" in informe and "bpm 0%" in informe


class TestIngesta:
    def test_ida_y_vuelta_por_archivo(self, tmp_path):
        original = Corpus(
            (
                _set(
                    "s1",
                    [
                        {"genero": "cumbia", "bpm": 95.0, "camelot": "8A", "titulo": "Uno"},
                        {"genero": "cumbia_420", "bpm": 98.0, "camelot": "9A", "titulo": "Dos"},
                    ],
                    escena="boliche_ar",
                ),
            )
        )
        ruta = tmp_path / "corpus.json"
        guardar(original, ruta)
        vuelto = cargar(ruta)

        assert len(vuelto) == 1
        assert vuelto.sets[0].escena == "boliche_ar"
        assert [t.genero for t in vuelto.sets[0].temas] == ["cumbia", "cumbia_420"]
        assert vuelto.sets[0].temas[0].bpm == 95.0

    def test_separa_por_escena(self):
        corpus = Corpus(
            (
                _set("s1", [{"genero": "a"}, {"genero": "b"}], escena="boliche_ar"),
                _set("s2", [{"genero": "x"}, {"genero": "y"}], escena="edm"),
            )
        )
        # el gusto no es universal: destilar las dos escenas juntas da un promedio que
        # no le sirve a ninguna
        assert len(corpus.de_escena("boliche_ar")) == 1
        assert corpus.escenas() == {"boliche_ar": 1, "edm": 1}

    def test_tolera_campos_faltantes(self):
        corpus = Corpus((_set("s1", [{"titulo": "solo titulo"}, {"artista": "solo artista"}]),))
        destilado = destilar(corpus)
        assert destilado.grafo.aristas == {}
        assert destilado.saltos_tempo.muestras == 0

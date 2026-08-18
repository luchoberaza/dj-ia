"""Nivel 2: que el sistema se corrija con lo que mide, no con lo que alguien opina.

El test que más importa de este archivo es el de la asimetría: el motor puede volverse
más conservador solo, y no puede volverse más aventurero solo.
"""

from __future__ import annotations

import pytest

from dj.aprendizaje import (
    COSTO_MAXIMO,
    MINIMO_USOS,
    Resultado,
    actualizar_rendimiento,
    ajustar_grafo,
    mejores_tramos,
)
from dj.dominio import GrafoGeneros


def resultado(
    id_pista="t1",
    genero="a",
    anterior=None,
    *,
    ocupacion=None,
    salteada=False,
    mala=False,
    favor=0,
    contra=0,
    activos=0,
    minuto=0.0,
) -> Resultado:
    antes, despues = (None, None) if ocupacion is None else ocupacion
    return Resultado(
        id_pista=id_pista,
        genero=genero,
        genero_anterior=anterior,
        minuto=minuto,
        ocupacion_antes=antes,
        ocupacion_despues=despues,
        salteada=salteada,
        transicion_marcada_mala=mala,
        votos_a_favor=favor,
        votos_en_contra=contra,
        votantes_activos=activos,
    )


GRAFO = GrafoGeneros({("a", "b"): 0.2, ("b", "a"): 0.2, ("b", "c"): 0.4})


class TestPuntaje:
    def test_la_pista_llenandose_es_positivo(self):
        assert resultado(ocupacion=(0.4, 0.7)).puntaje() > 0

    def test_la_pista_vaciandose_es_negativo(self):
        assert resultado(ocupacion=(0.8, 0.4)).puntaje() < 0

    def test_saltear_es_negativo(self):
        assert resultado(salteada=True).puntaje() < 0

    def test_los_votos_a_favor_suman(self):
        assert resultado(favor=30, contra=2, activos=40).puntaje() > 0

    def test_los_votos_en_contra_restan(self):
        assert resultado(favor=2, contra=30, activos=40).puntaje() < 0

    def test_sin_ninguna_senal_es_neutro(self):
        assert resultado().puntaje() == 0.0

    def test_esta_acotado(self):
        assert -1.0 <= resultado(ocupacion=(1.0, 0.0), salteada=True).puntaje() <= 1.0
        assert -1.0 <= resultado(ocupacion=(0.0, 1.0), favor=99, activos=1).puntaje() <= 1.0


class TestRendimientoPorTema:
    def test_un_tema_que_funciona_sube(self):
        buenos = [resultado("t1", ocupacion=(0.3, 0.8)) for _ in range(5)]
        assert actualizar_rendimiento({}, buenos)["t1"] > 0

    def test_un_tema_que_vacia_baja(self):
        malos = [resultado("t1", ocupacion=(0.8, 0.3)) for _ in range(5)]
        assert actualizar_rendimiento({}, malos)["t1"] < 0

    def test_una_sola_mala_noche_no_descalifica(self):
        """Con una observación el valor queda atenuado: no se condena a nadie por una."""
        una = actualizar_rendimiento({}, [resultado("t1", ocupacion=(0.9, 0.2))])["t1"]
        varias = actualizar_rendimiento(
            {}, [resultado("t1", ocupacion=(0.9, 0.2)) for _ in range(6)]
        )["t1"]
        assert abs(una) < abs(varias)

    def test_arrastra_el_valor_previo(self):
        previo = {"t1": 0.8}
        actualizado = actualizar_rendimiento(previo, [resultado("t1", ocupacion=(0.5, 0.4))])
        assert 0 < actualizado["t1"] < 0.8  # baja, pero no se derrumba de un saque

    def test_no_toca_los_temas_que_no_sonaron(self):
        previo = {"t1": 0.5, "t2": -0.3}
        actualizado = actualizar_rendimiento(previo, [resultado("t1", ocupacion=(0.5, 0.6))])
        assert actualizado["t2"] == -0.3


class TestAjusteDelGrafo:
    def _malos(self, cuantos, arista=("a", "b"), **extra):
        return [
            resultado("t%d" % i, genero=arista[1], anterior=arista[0], **extra)
            for i in range(cuantos)
        ]

    def test_encarece_una_arista_que_funciona_mal(self):
        # -10 puntos de ocupación: mala, pero no catastrófica
        grafo, ajustes = ajustar_grafo(
            GRAFO, self._malos(MINIMO_USOS, ocupacion=(0.70, 0.60))
        )
        assert ajustes and ajustes[0].accion == "encarecida"
        assert grafo.costo("a", "b") > GRAFO.costo("a", "b")

    def test_vaciar_la_pista_pesa_mas_que_incomodarla(self):
        _, leve = ajustar_grafo(GRAFO, self._malos(MINIMO_USOS, ocupacion=(0.70, 0.60)))
        _, grave = ajustar_grafo(GRAFO, self._malos(MINIMO_USOS, ocupacion=(0.90, 0.10)))
        assert leve[0].accion == "encarecida"
        assert grave[0].accion == "removida"

    def test_saca_una_arista_que_vacia_la_pista(self):
        grafo, ajustes = ajustar_grafo(
            GRAFO, self._malos(MINIMO_USOS, ocupacion=(0.9, 0.1))
        )
        assert ajustes and ajustes[0].accion == "removida"
        assert not grafo.hay_arista("a", "b")

    def test_no_toca_nada_con_pocas_observaciones(self):
        """Una anécdota no es una regla, ni para agregar ni para sacar."""
        grafo, ajustes = ajustar_grafo(
            GRAFO, self._malos(MINIMO_USOS - 1, ocupacion=(0.9, 0.1))
        )
        assert ajustes == []
        assert grafo.aristas == GRAFO.aristas

    def test_no_toca_las_aristas_que_funcionan(self):
        buenos = self._malos(MINIMO_USOS * 2, ocupacion=(0.4, 0.8))
        grafo, ajustes = ajustar_grafo(GRAFO, buenos)
        assert ajustes == []
        assert grafo.aristas == GRAFO.aristas

    def test_nunca_agrega_una_arista(self):
        """La asimetría central: más conservador solo, más aventurero nunca.

        Que una transición no exista no genera evidencia de que debería existir: el
        motor nunca la prueba. Descubrir aristas es una decisión de gusto, de persona.
        """
        excelentes = [
            resultado("t%d" % i, genero="z", anterior="a", ocupacion=(0.2, 1.0))
            for i in range(MINIMO_USOS * 5)
        ]
        grafo, ajustes = ajustar_grafo(GRAFO, excelentes)
        assert not grafo.hay_arista("a", "z")
        assert ajustes == []

    def test_el_boton_de_transicion_mala_pega_directo(self):
        """El feedback más barato del sistema tiene que ser el más contundente."""
        marcadas = self._malos(MINIMO_USOS, mala=True)
        grafo, ajustes = ajustar_grafo(GRAFO, marcadas)
        assert ajustes and ajustes[0].accion == "removida"

    def test_el_encarecimiento_tiene_techo(self):
        grafo, _ = ajustar_grafo(
            GrafoGeneros({("a", "b"): 0.9}),
            self._malos(MINIMO_USOS, ocupacion=(0.75, 0.65)),
        )
        assert grafo.costo("a", "b") is not None
        assert grafo.costo("a", "b") <= COSTO_MAXIMO

    def test_ignora_transiciones_dentro_del_mismo_genero(self):
        mismos = [
            resultado("t%d" % i, genero="a", anterior="a", ocupacion=(0.9, 0.1))
            for i in range(MINIMO_USOS * 2)
        ]
        _, ajustes = ajustar_grafo(GRAFO, mismos)
        assert ajustes == []

    def test_el_ajuste_se_explica(self):
        _, ajustes = ajustar_grafo(GRAFO, self._malos(MINIMO_USOS, ocupacion=(0.9, 0.1)))
        texto = str(ajustes[0])
        assert "a → b" in texto and "usos" in texto and "puntaje medio" in texto


class TestMejoresTramos:
    def test_encuentra_la_cola_buena_de_una_noche_mediocre(self):
        """Un local con 80% de noches flojas sirve igual si se identifica el 20%."""
        flojos = [resultado(f"m{i}", ocupacion=(0.6, 0.5)) for i in range(40)]
        buenos = [resultado(f"b{i}", ocupacion=(0.4, 0.95)) for i in range(10)]
        historia = flojos[:20] + buenos + flojos[20:]

        tramos = mejores_tramos(historia, largo=8, proporcion=0.05)
        assert tramos
        ids = {r.id_pista for r in tramos[0]}
        assert all(i.startswith("b") for i in ids), ids

    def test_los_tramos_no_se_solapan(self):
        """Dos ventanas corridas un lugar no son dos evidencias distintas."""
        historia = [resultado(f"t{i}", ocupacion=(0.4, 0.9)) for i in range(40)]
        tramos = mejores_tramos(historia, largo=8, proporcion=0.5)
        vistos: set[str] = set()
        for tramo in tramos:
            ids = {r.id_pista for r in tramo}
            assert not (ids & vistos)
            vistos |= ids

    def test_devuelve_vacio_si_no_hay_historia_suficiente(self):
        assert mejores_tramos([resultado("t1")], largo=8) == []

    def test_el_filtro_es_el_resultado_y_no_el_orden(self):
        # lo bueno está al final; si el filtro fuera posicional lo perdería
        historia = [resultado(f"m{i}", ocupacion=(0.7, 0.4)) for i in range(24)]
        historia += [resultado(f"b{i}", ocupacion=(0.3, 0.95)) for i in range(8)]
        tramos = mejores_tramos(historia, largo=8, proporcion=0.05)
        assert all(r.id_pista.startswith("b") for r in tramos[0])


class TestIntegracionConElPlanificador:
    def test_el_grafo_ajustado_sigue_sirviendo_para_planificar(self, catalogo, politica):
        from dj.catalogo_demo import grafo_boliche
        from dj.invariantes import verificar
        from dj.planificador import generar_noche

        # el público rechaza sistemáticamente el salto cumbia → cuarteto
        rechazos = [
            Resultado(
                id_pista=f"r{i}",
                genero="cuarteto",
                genero_anterior="cumbia",
                transicion_marcada_mala=True,
            )
            for i in range(MINIMO_USOS * 2)
        ]
        ajustado, ajustes = ajustar_grafo(grafo_boliche(), rechazos)
        assert ajustes and not ajustado.hay_arista("cumbia", "cuarteto")

        pasos = generar_noche(catalogo, politica, ajustado, duracion_min=180.0)
        assert pasos
        assert not verificar(pasos, politica, ajustado)
        # y el motor deja de usar la arista que el dato le sacó
        for anterior, actual in zip(pasos, pasos[1:]):
            assert not (
                anterior.pista.genero == "cumbia" and actual.pista.genero == "cuarteto"
            )

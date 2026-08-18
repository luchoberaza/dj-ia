"""El planificador: que encuentre la escalera solo es toda la idea del producto."""

from __future__ import annotations

import pytest
from ayudas import pista

from dj.dominio import Atractor, EstadoNoche, Fase, GrafoGeneros, PoliticaNoche
from dj.planificador import Catalogo, Config, generar_noche, planificar
from dj.tempo import TOLERANCIA_COSTURA, diferencia_relativa

# ---------------------------------------------------------------- escenario de rampa
#
# Cuatro géneros encadenados, cada uno en su franja de tempo. Para ir de "a" (130) a
# "d" (95) hay que bajar el tempo Y atravesar tres aristas de género. No hay atajo:
# o el planificador construye la escalera, o no llega.

TRAMOS = (("a", 126.0, 136.0), ("b", 114.0, 126.0), ("c", 102.0, 114.0), ("d", 92.0, 102.0))

GRAFO_RAMPA = GrafoGeneros(
    {
        ("a", "b"): 0.2,
        ("b", "a"): 0.2,
        ("b", "c"): 0.2,
        ("c", "b"): 0.2,
        ("c", "d"): 0.2,
        ("d", "c"): 0.2,
    }
)


@pytest.fixture(scope="module")
def catalogo_rampa() -> Catalogo:
    pistas = []
    contador = 0
    for genero, bajo, alto in TRAMOS:
        for k in range(24):
            contador += 1
            bpm = bajo + (alto - bajo) * k / 23
            pistas.append(
                pista(
                    f"{genero}{k:02d}",
                    genero=genero,
                    bpm=round(bpm, 1),
                    artista=f"art{contador:03d}",
                    camelot="8A",
                    energia=6.0,
                )
            )
    return Catalogo(pistas)


@pytest.fixture(scope="module")
def politica_rampa() -> PoliticaNoche:
    # El escenario realista: venimos tocando arriba (134) y la parte de la noche en la
    # que estamos apunta a 100. La gente vota una cumbia a 93. El motor tiene que
    # construir la bajada, no pegar el salto.
    return PoliticaNoche(nombre="rampa", fases=(Fase("unica", 0, 100, 6.0),))


class TestRutaHaciaLoVotado:
    """El caso que originó el proyecto: el tema más votado baja mucho los BPM."""

    def test_llega_al_tema_votado_bajando_progresivamente(self, catalogo_rampa, politica_rampa):
        arranque = catalogo_rampa.get("a20")  # ~134 BPM, género "a"
        destino = catalogo_rampa.get("d02")  # ~93 BPM, género "d"
        estado = EstadoNoche(minuto=0.0, actual=arranque)

        plan = planificar(
            estado,
            catalogo_rampa,
            politica_rampa,
            GRAFO_RAMPA,
            Atractor(pistas={destino.id: 10.0}),
            config=Config(horizonte=8, ancho_haz=12),
        )

        ids = [p.pista.id for p in plan.pasos]
        assert destino.id in ids, f"no llegó a lo votado: {ids}"
        assert plan.alcanza_atractor

    def test_cada_transicion_de_la_escalera_es_chica(self, catalogo_rampa, politica_rampa):
        arranque = catalogo_rampa.get("a20")
        destino = catalogo_rampa.get("d02")
        plan = planificar(
            EstadoNoche(minuto=0.0, actual=arranque),
            catalogo_rampa,
            politica_rampa,
            GRAFO_RAMPA,
            Atractor(pistas={destino.id: 10.0}),
            config=Config(horizonte=8, ancho_haz=12),
        )

        anterior = arranque
        for paso in plan.pasos:
            if paso.transicion.es_costura:
                salto = abs(diferencia_relativa(anterior.bpm, paso.pista.bpm))
                assert salto < TOLERANCIA_COSTURA, (
                    f"costura de {salto:.1%} entre {anterior.id} y {paso.pista.id}"
                )
            anterior = paso.pista

    def test_el_tempo_baja_de_forma_sostenida(self, catalogo_rampa, politica_rampa):
        arranque = catalogo_rampa.get("a20")
        destino = catalogo_rampa.get("d02")
        plan = planificar(
            EstadoNoche(minuto=0.0, actual=arranque),
            catalogo_rampa,
            politica_rampa,
            GRAFO_RAMPA,
            Atractor(pistas={destino.id: 10.0}),
            config=Config(horizonte=8, ancho_haz=12),
        )
        indice = next(i for i, p in enumerate(plan.pasos) if p.pista.id == destino.id)
        bpms = [arranque.bpm] + [p.pista.bpm for p in plan.pasos[: indice + 1]]
        # no exigimos monotonía estricta, sí que el tramo sea claramente descendente
        assert bpms[-1] < bpms[0]
        subidas = sum(1 for a, b in zip(bpms, bpms[1:]) if b > a + 0.5)
        assert subidas <= 1, f"la escalera sube demasiadas veces: {bpms}"

    def test_los_pasos_quedan_etiquetados_para_mostrarle_a_la_gente(
        self, catalogo_rampa, politica_rampa
    ):
        arranque = catalogo_rampa.get("a20")
        destino = catalogo_rampa.get("d02")
        plan = planificar(
            EstadoNoche(minuto=0.0, actual=arranque),
            catalogo_rampa,
            politica_rampa,
            GRAFO_RAMPA,
            Atractor(pistas={destino.id: 10.0}),
            config=Config(horizonte=8, ancho_haz=12),
        )
        indice = next(i for i, p in enumerate(plan.pasos) if p.pista.id == destino.id)
        primero = plan.pasos[0]
        assert primero.hacia == destino.id
        assert primero.paso_de == (1, indice + 1)
        assert plan.pasos[indice].paso_de == (indice + 1, indice + 1)


class TestSinRutaValida:
    def test_avisa_que_lo_votado_no_es_alcanzable(self, catalogo_rampa, politica_rampa):
        # se borra el género puente: ya no hay forma de bajar de "b" a "d"
        catalogo_sin_puente = Catalogo(p for p in catalogo_rampa if p.genero != "c")
        arranque = catalogo_sin_puente.get("a20")
        destino = catalogo_sin_puente.get("d02")

        plan = planificar(
            EstadoNoche(minuto=0.0, actual=arranque),
            catalogo_sin_puente,
            politica_rampa,
            GRAFO_RAMPA,
            Atractor(pistas={destino.id: 10.0}),
            config=Config(horizonte=8, ancho_haz=12),
        )
        assert not plan.alcanza_atractor
        assert plan.faltante is not None
        assert "no es alcanzable" in plan.faltante

    def test_cae_a_la_tanda_de_emergencia(self, politica_rampa):
        # un catálogo de un solo tema no puede llenar ningún horizonte
        unico = pista("solo", genero="a", bpm=130.0)
        respaldo = [pista(f"e{i}", genero="a", bpm=130.0, artista=f"e{i}") for i in range(4)]
        plan = planificar(
            EstadoNoche(minuto=0.0, actual=unico),
            Catalogo([unico]),
            politica_rampa,
            GRAFO_RAMPA,
            emergencia={"unica": respaldo},
            config=Config(horizonte=4),
        )
        assert plan.emergencia
        assert len(plan) == 4

    def test_sin_emergencia_devuelve_plan_vacio(self, politica_rampa):
        unico = pista("solo", genero="a", bpm=130.0)
        plan = planificar(
            EstadoNoche(minuto=0.0, actual=unico),
            Catalogo([unico]),
            politica_rampa,
            GRAFO_RAMPA,
            config=Config(horizonte=4),
        )
        assert not plan
        assert len(plan) == 0


class TestArranqueDeNoche:
    def test_el_primer_tema_arranca_cerca_del_objetivo_de_la_fase(
        self, catalogo, politica, grafo, senales
    ):
        plan = planificar(
            EstadoNoche(),
            catalogo,
            politica,
            grafo,
            senales=senales,
            config=Config(horizonte=3),
        )
        primera = plan.pasos[0].pista
        objetivo = politica.fases[0].bpm_objetivo
        assert abs(primera.bpm - objetivo) / objetivo <= 0.08


class TestNocheCompleta:
    def test_genera_una_noche_de_cuatro_horas(self, catalogo, politica, grafo, senales, emergencia):
        pasos = generar_noche(
            catalogo,
            politica,
            grafo,
            duracion_min=240.0,
            senales=senales,
            emergencia=emergencia,
        )
        assert len(pasos) > 55  # ~3,5 min por tema
        assert pasos[-1].minuto_inicio >= 230.0

    def test_no_cae_a_emergencia_con_un_catalogo_normal(
        self, catalogo, politica, grafo, senales, emergencia
    ):
        pasos = generar_noche(
            catalogo,
            politica,
            grafo,
            duracion_min=240.0,
            senales=senales,
            emergencia=emergencia,
        )
        # si el motor necesita el plan B con 1200 temas, algo está mal en el motor.
        # Ojo: hay que mirar el flag, no si el tema figura en la tanda — la tanda se
        # arma con temas del catálogo normal, así que el planificador los elige solo.
        usados = [p for p in pasos if p.emergencia]
        assert not usados, f"cayó a emergencia {len(usados)} veces de {len(pasos)}"

    def test_recorre_varios_generos(self, catalogo, politica, grafo, senales, emergencia):
        pasos = generar_noche(
            catalogo, politica, grafo, duracion_min=240.0, senales=senales, emergencia=emergencia
        )
        assert len({p.pista.genero for p in pasos}) >= 3

    def test_el_pico_es_mas_rapido_que_la_apertura(
        self, catalogo, politica, grafo, senales, emergencia
    ):
        pasos = generar_noche(
            catalogo, politica, grafo, duracion_min=360.0, senales=senales, emergencia=emergencia
        )
        apertura = [p.pista.bpm for p in pasos if p.fase == "apertura"]
        pico = [p.pista.bpm for p in pasos if p.fase == "pico"]
        assert apertura and pico
        assert sum(pico) / len(pico) > sum(apertura) / len(apertura)


class TestRendimiento:
    def test_planificar_es_rapido(self, catalogo, politica, grafo, senales):
        import time

        estado = EstadoNoche(minuto=100.0, actual=catalogo.pistas[0])
        arranque = time.perf_counter()
        planificar(estado, catalogo, politica, grafo, senales=senales)
        transcurrido = time.perf_counter() - arranque
        # se replanifica a cada tema en vivo: tiene que ser cómodamente sub-segundo
        assert transcurrido < 1.0, f"tardó {transcurrido:.2f}s"

"""Catálogo sintético de un boliche argentino, para ejercitar y testear el motor.

No reemplaza al catálogo real: reemplaza a *no tener ninguno* mientras el analizador
de biblioteca no exista. Los rangos de BPM salen de las tablas de referencia del
diseño y hay que recalibrarlos contra el catálogo real de un cliente.

Todo es determinista con la misma semilla: los tests dependen de eso.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .dominio import Atractor, Fase, GrafoGeneros, Pista, PoliticaNoche
from .deseabilidad import Senales
from .planificador import Catalogo


@dataclass(frozen=True, slots=True)
class _PerfilGenero:
    nombre: str
    bpm_min: float
    bpm_max: float
    energia_min: float
    energia_max: float
    #: Proporción de temas que el analizador no puede costurar con confianza
    #: (grabaciones viejas, tempo que respira, banda en vivo).
    proporcion_no_costurable: float


PERFILES: tuple[_PerfilGenero, ...] = (
    _PerfilGenero("cumbia", 92, 104, 3, 7, 0.35),
    _PerfilGenero("cumbia_420", 95, 108, 4, 8, 0.20),
    _PerfilGenero("reggaeton", 88, 100, 5, 8, 0.08),
    _PerfilGenero("perreo", 95, 106, 6, 9, 0.05),
    _PerfilGenero("dembow", 110, 125, 7, 10, 0.05),
    _PerfilGenero("pop_latino", 100, 120, 4, 8, 0.10),
    _PerfilGenero("cuarteto", 120, 138, 6, 9, 0.30),
    _PerfilGenero("latin_house", 120, 126, 6, 9, 0.02),
    _PerfilGenero("tech_house", 124, 128, 7, 10, 0.02),
    _PerfilGenero("techno", 128, 140, 8, 10, 0.02),
)


#: El grafo de un boliche argentino. Es cultural, no universal: `cumbia → techno` no
#: existe acá, y ésa es exactamente la arista que el DJ malo toma de la nada.
ARISTAS_BOLICHE: dict[tuple[str, str], float] = {
    ("cumbia", "cumbia_420"): 0.10,
    ("cumbia_420", "cumbia"): 0.10,
    ("cumbia", "cuarteto"): 0.35,
    ("cuarteto", "cumbia"): 0.35,
    ("cumbia_420", "reggaeton"): 0.30,
    ("reggaeton", "cumbia_420"): 0.30,
    ("reggaeton", "perreo"): 0.10,
    ("perreo", "reggaeton"): 0.10,
    ("reggaeton", "dembow"): 0.25,
    ("dembow", "reggaeton"): 0.25,
    # Sin estas dos aristas el grafo tiene una trampa de tempo: para subir de 105 a 120
    # había que pasar por reggaetón, que está más abajo, y la curva castigaba el pozo.
    # El motor se quedaba clavado en cumbia_420 toda la fase de build. La falla no era
    # del planificador sino del mapa que le dimos.
    ("cumbia_420", "dembow"): 0.35,
    ("dembow", "cumbia_420"): 0.35,
    ("pop_latino", "dembow"): 0.30,
    ("dembow", "pop_latino"): 0.30,
    ("perreo", "dembow"): 0.20,
    ("dembow", "perreo"): 0.20,
    ("reggaeton", "pop_latino"): 0.30,
    ("pop_latino", "reggaeton"): 0.30,
    ("pop_latino", "cuarteto"): 0.45,
    ("cuarteto", "pop_latino"): 0.45,
    ("pop_latino", "latin_house"): 0.40,
    ("latin_house", "pop_latino"): 0.40,
    ("dembow", "latin_house"): 0.50,
    ("latin_house", "dembow"): 0.50,
    ("latin_house", "tech_house"): 0.20,
    ("tech_house", "latin_house"): 0.20,
    ("tech_house", "techno"): 0.15,
    ("techno", "tech_house"): 0.15,
}

_NUMEROS_CAMELOT = tuple(f"{n}{letra}" for n in range(1, 13) for letra in ("A", "B"))


def grafo_boliche() -> GrafoGeneros:
    return GrafoGeneros(aristas=dict(ARISTAS_BOLICHE))


def politica_boliche() -> PoliticaNoche:
    """Seis horas: abre tranquila pero bailable, sube, pega el pico, y baja al cierre."""
    return PoliticaNoche(
        nombre="sabado_boliche",
        fases=(
            Fase("apertura", 0, 96, 4.0, es_build=False),
            Fase("calentando", 60, 104, 6.0, es_build=True),
            Fase("build", 120, 116, 7.5, es_build=True),
            Fase(
                "pico",
                180,
                126,
                9.0,
                permite_bajar_bpm=False,
                es_build=True,
            ),
            Fase("meseta", 270, 124, 8.0),
            Fase("cierre", 330, 108, 6.0),
        ),
        cooldown_tema_min=240.0,
        cooldown_artista_min=45.0,
        max_por_artista_por_hora=2,
        max_concesiones_voto_por_hora=4,
    )


def catalogo_demo(cantidad: int = 1200, semilla: int = 17) -> Catalogo:
    """Catálogo sintético reproducible.

    El reparto imita una biblioteca real de boliche: mucha cumbia y reggaetón, poca
    electrónica, y una cola de temas viejos que el analizador no puede costurar.
    """
    rng = random.Random(semilla)
    # El reparto no es solo "qué escucha la gente": tiene que sostener cada fase de la
    # política. Un primer reparto con 3% de tech house y 5% de latin house dejaba al
    # motor sin material para 90 minutos de pico a 126 BPM, y el planificador caía a la
    # tanda de emergencia. El cuello de botella de un catálogo no es su tamaño total
    # sino su profundidad por fase.
    reparto = {
        "cumbia": 0.18,
        "cumbia_420": 0.10,
        "reggaeton": 0.17,
        "perreo": 0.12,
        "dembow": 0.08,
        "pop_latino": 0.07,
        "cuarteto": 0.12,
        "latin_house": 0.08,
        "tech_house": 0.05,
        "techno": 0.03,
    }
    por_nombre = {p.nombre: p for p in PERFILES}

    pistas: list[Pista] = []
    indice = 0
    for nombre, proporcion in reparto.items():
        perfil = por_nombre[nombre]
        for _ in range(max(1, round(cantidad * proporcion))):
            indice += 1
            bpm = rng.uniform(perfil.bpm_min, perfil.bpm_max)
            posicion = (bpm - perfil.bpm_min) / max(1e-6, perfil.bpm_max - perfil.bpm_min)
            energia = perfil.energia_min + posicion * (perfil.energia_max - perfil.energia_min)
            energia = min(10.0, max(1.0, energia + rng.uniform(-1.0, 1.0)))

            costurable = rng.random() >= perfil.proporcion_no_costurable
            confianza_bpm = rng.uniform(0.85, 1.0) if costurable else rng.uniform(0.2, 0.5)
            confianza_tono = rng.uniform(0.7, 1.0) if costurable else rng.uniform(0.1, 0.6)

            pistas.append(
                Pista(
                    id=f"t{indice:05d}",
                    titulo=f"{nombre.replace('_', ' ').title()} {indice}",
                    artista=f"Artista {indice % 140:03d}",
                    genero=nombre,
                    bpm=round(bpm, 1),
                    duracion_s=rng.uniform(170, 240),
                    camelot=rng.choice(_NUMEROS_CAMELOT),
                    energia=round(energia, 1),
                    isrc=f"AR{indice:08d}",
                    bpm_confianza=round(confianza_bpm, 2),
                    camelot_confianza=round(confianza_tono, 2),
                    apta_para_costura=costurable,
                )
            )

    rng.shuffle(pistas)
    return Catalogo(pistas)


def senales_demo(catalogo: Catalogo, semilla: int = 17) -> Senales:
    """Tendencia y rotación simuladas. El rendimiento local arranca vacío: un local
    nuevo todavía no tiene histórico propio, y ése es el arranque en frío real."""
    rng = random.Random(semilla + 1)
    return Senales(
        tendencia={p.id: round(rng.betavariate(2, 5), 3) for p in catalogo},
        rotacion={p.id: round(rng.random(), 3) for p in catalogo},
        rendimiento_local={},
    )


def emergencia_demo(catalogo: Catalogo, politica: PoliticaNoche) -> dict[str, list[Pista]]:
    """Tanda de emergencia por fase: la playlist que el cliente aprueba en el onboarding.

    Se arma con temas de **todos** los géneros, no solo del que mejor pega con el tempo
    de la fase. Si la tanda cubriera un solo género, el plan B quedaría inalcanzable
    desde cualquier otro punto del grafo, que es justo cuando se lo necesita.
    """
    tandas: dict[str, list[Pista]] = {}
    por_genero: dict[str, list[Pista]] = {}
    for pista in catalogo:
        if pista.apta_para_costura:
            por_genero.setdefault(pista.genero, []).append(pista)

    for fase in politica.fases:
        tanda: list[Pista] = []
        for pistas in por_genero.values():
            cercanas = sorted(pistas, key=lambda p: abs(p.bpm - fase.bpm_objetivo))
            tanda.extend(cercanas[:6])
        tandas[fase.nombre] = tanda
    return tandas


def atractor_demo(catalogo: Catalogo, genero: str = "cumbia", votos: int = 3) -> Atractor:
    """Simula el caso difícil del diseño: la gente vota temas que bajan el tempo."""
    elegidas = [p for p in catalogo if p.genero == genero and p.apta_para_costura][:votos]
    pesos = {p.id: float(votos - i) for i, p in enumerate(elegidas)}
    return Atractor(pistas=pesos, genero=genero, delta_energia=-0.5)

"""El planificador: busca la ruta, no el próximo tema.

Un jukebox pregunta "¿qué pongo ahora?". Este motor pregunta "¿cuál es el camino de
acá a donde la pista quiere ir?".

Formalmente es una búsqueda de ruta en un grafo: los nodos son temas, las aristas son
transiciones y cada arista tiene un costo. Si el tema más votado está a 20 BPM y dos
géneros de distancia, el planificador **encuentra la escalera solo** — no hay que
programarla.

Se usa beam search y no A*: más simple, más fácil de depurar, y para 6-8 pasos sobre
un catálogo de miles de temas corre en milisegundos.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, replace
from typing import Iterable, Mapping, Sequence

from .costos import Pesos, evaluar_transicion
from .deseabilidad import Deseabilidad, PesosDeseabilidad, Senales
from .dominio import (
    Atractor,
    Desglose,
    EstadoNoche,
    Fase,
    GrafoGeneros,
    Pista,
    PoliticaNoche,
    TipoTransicion,
)
from .restricciones import ORDEN_RELAJACION, evaluar, relajaciones_hasta
from .tempo import diferencia_relativa, equivalente_octava


@dataclass(frozen=True, slots=True)
class Config:
    horizonte: int = 6
    ancho_haz: int = 8
    por_deseabilidad: int = 30
    por_tempo: int = 30
    por_atractor: int = 20
    #: Cuánto tempo se puede mover como mucho en un paso. Define la pendiente de la
    #: rampa y, con ella, cuántos temas hace falta para llegar a lo votado.
    max_cambio_bpm_por_paso: float = 4.0
    #: Ventana de tempo aceptable para el primer tema de la noche.
    tolerancia_arranque: float = 0.08


@dataclass(frozen=True, slots=True)
class PasoPlan:
    pista: Pista
    minuto_inicio: float
    transicion: TipoTransicion
    desglose: Desglose
    fase: str
    cedio_al_voto: bool = False
    hacia: str | None = None  # id del tema votado al que apunta la ruta
    paso_de: tuple[int, int] | None = None  # (2, 4) = "paso 2 de 4 hacia X"
    #: Viene de la tanda de emergencia. Un tramo de emergencia sacrifica lo óptimo
    #: (cooldowns, curva) pero nunca lo que rompe el ambiente: género sin puente,
    #: costura imposible, lista negra o bajar el tempo en el pico.
    emergencia: bool = False

    def motivo(self, anterior: Pista | None) -> str:
        texto = self.desglose.como_texto(anterior, self.pista)
        if self.paso_de is not None:
            texto += f" · paso {self.paso_de[0]} de {self.paso_de[1]} hacia lo votado"
        return texto


@dataclass(frozen=True, slots=True)
class Plan:
    pasos: tuple[PasoPlan, ...]
    costo: float
    relajaciones: frozenset[str] = frozenset()
    emergencia: bool = False
    alcanza_atractor: bool = False
    faltante: str | None = None

    def __len__(self) -> int:
        return len(self.pasos)

    def __bool__(self) -> bool:
        return bool(self.pasos)

    @property
    def duracion_min(self) -> float:
        return sum(p.pista.duracion_min for p in self.pasos)


class Catalogo:
    """La biblioteca del establecimiento, con índices por id y por género.

    El índice por género es lo que hace viable la replanificación en vivo: desde un
    tema solo se puede ir a su propio género o a los que tienen arista, así que no
    hace falta mirar el catálogo entero en cada expansión del haz.
    """

    __slots__ = ("pistas", "_por_id", "_por_genero")

    def __init__(self, pistas: Iterable[Pista]) -> None:
        self.pistas: tuple[Pista, ...] = tuple(pistas)
        self._por_id: dict[str, Pista] = {p.id: p for p in self.pistas}
        self._por_genero: dict[str, list[Pista]] = {}
        for pista in self.pistas:
            self._por_genero.setdefault(pista.genero, []).append(pista)

    def __len__(self) -> int:
        return len(self.pistas)

    def __iter__(self):
        return iter(self.pistas)

    def get(self, id_pista: str) -> Pista | None:
        return self._por_id.get(id_pista)

    def de_generos(self, generos: Iterable[str]) -> list[Pista]:
        alcanzables: list[Pista] = []
        for genero in dict.fromkeys(generos):
            alcanzables.extend(self._por_genero.get(genero, ()))
        return alcanzables


@dataclass(frozen=True, slots=True)
class _Ruta:
    estado: EstadoNoche
    pasos: tuple[PasoPlan, ...]
    costo: float
    alcanzo_destino: bool


# ------------------------------------------------------------- objetivo de la curva


def objetivo_bpm(
    fase: Fase, destino: Pista | None, atractor: Atractor, politica: PoliticaNoche
) -> float:
    """El tempo al que la fase quiere estar, ya corregido por lo votado.

    El voto puede correr el objetivo, pero nunca más allá de `max_desvio_voto`: ése es
    el techo declarado de "un voto tuerce el rumbo, no lo manda". Y en una fase que no
    permite bajar el BPM, no puede tirarlo para abajo en absoluto.
    """
    base = fase.bpm_objetivo + atractor.delta_bpm
    objetivo = base
    if destino is not None:
        equivalente = equivalente_octava(base, destino.bpm)
        margen = base * politica.max_desvio_voto
        objetivo = min(base + margen, max(base - margen, equivalente))
    if not fase.permite_bajar_bpm:
        objetivo = max(objetivo, fase.bpm_objetivo)
    return objetivo


# ------------------------------------------------------------------------ heurística


def _distancia_al_destino(
    estado: EstadoNoche,
    destino: Pista | None,
    atractor: Atractor,
    grafo: GrafoGeneros,
    config: Config,
) -> float:
    """Cuántos pasos faltan, más o menos, para llegar a lo votado.

    Se usa solo para ordenar el haz. No entra en el costo acumulado del plan, así que
    no distorsiona la explicación de cada transición.
    """
    actual = estado.actual
    if actual is None:
        return 0.0

    if destino is not None:
        equivalente = equivalente_octava(actual.bpm, destino.bpm)
        pasos_bpm = abs(equivalente - actual.bpm) / config.max_cambio_bpm_por_paso
        saltos = grafo.saltos(actual.genero, destino.genero)
        saltos_genero = 4 if saltos is None else saltos
        return (pasos_bpm + 1.5 * saltos_genero) / 10.0

    distancia = 0.0
    if atractor.genero is not None:
        saltos = grafo.saltos(actual.genero, atractor.genero)
        distancia += 0.15 * (4 if saltos is None else saltos)
    if atractor.delta_energia:
        objetivo = actual.energia + atractor.delta_energia
        distancia += abs(objetivo - actual.energia) / 20.0
    return distancia


# -------------------------------------------------------------- generación de candidatos


def _candidatos(
    estado: EstadoNoche,
    catalogo: Catalogo,
    politica: PoliticaNoche,
    fase: Fase,
    grafo: GrafoGeneros,
    atractor: Atractor,
    deseabilidad: Deseabilidad,
    destino: Pista | None,
    config: Config,
    relajaciones: frozenset[str],
) -> list[Pista]:
    """Candidatos diversos, no solo los más deseables.

    Se toman tres tops y se unen: por deseabilidad, por cercanía de tempo y por
    cercanía al destino votado. Quedarse solo con los más deseables perdería justo el
    tema puente —poco atractivo por sí mismo— que hace posible la escalera.
    """
    actual = estado.actual
    if actual is None:
        universo: list[Pista] | tuple[Pista, ...] = catalogo.pistas
    else:
        universo = catalogo.de_generos((actual.genero, *grafo.vecinos(actual.genero)))

    validos: list[tuple[Pista, float, float, float]] = []

    for pista in universo:
        if evaluar(
            pista,
            estado,
            politica,
            fase,
            grafo,
            cede_al_voto=atractor.peso(pista.id) > 0,
            relajaciones=relajaciones,
        ) is not None:
            continue

        if actual is None:
            distancia_arranque = abs(pista.bpm - fase.bpm_objetivo) / fase.bpm_objetivo
            if distancia_arranque > config.tolerancia_arranque:
                continue
            tempo = distancia_arranque
        else:
            tempo = abs(diferencia_relativa(actual.bpm, pista.bpm))

        atraccion = 0.0
        if destino is not None:
            atraccion = abs(diferencia_relativa(pista.bpm, destino.bpm))
            saltos = grafo.saltos(pista.genero, destino.genero)
            atraccion += 0.1 * (4 if saltos is None else saltos)

        validos.append((pista, deseabilidad.para(pista), tempo, atraccion))

    if not validos:
        return []

    elegidos: dict[str, Pista] = {}

    for pista, _, _, _ in heapq.nlargest(config.por_deseabilidad, validos, key=lambda v: v[1]):
        elegidos[pista.id] = pista
    for pista, _, _, _ in heapq.nsmallest(config.por_tempo, validos, key=lambda v: v[2]):
        elegidos[pista.id] = pista
    if destino is not None:
        for pista, _, _, _ in heapq.nsmallest(
            config.por_atractor, validos, key=lambda v: v[3]
        ):
            elegidos[pista.id] = pista

    return list(elegidos.values())


# ------------------------------------------------------------------------ beam search


def _buscar(
    estado_inicial: EstadoNoche,
    catalogo: Catalogo,
    politica: PoliticaNoche,
    grafo: GrafoGeneros,
    atractor: Atractor,
    deseabilidad: Deseabilidad,
    pesos: Pesos,
    config: Config,
    relajaciones: frozenset[str],
    pasos_pedidos: int,
) -> _Ruta | None:
    destino_id = atractor.destino_principal()
    destino = catalogo.get(destino_id) if destino_id else None

    ignorar_energia = "energia" in relajaciones
    ignorar_tonal = "tonal" in relajaciones

    rutas = [_Ruta(estado_inicial, (), 0.0, False)]

    for _ in range(pasos_pedidos):
        expandidas: list[_Ruta] = []

        for ruta in rutas:
            fase = politica.fase_en(ruta.estado.minuto)
            energia_objetivo = min(
                10.0, max(1.0, fase.energia_objetivo + atractor.delta_energia)
            )
            bpm_objetivo = objetivo_bpm(
                fase, None if ruta.alcanzo_destino else destino, atractor, politica
            )

            for pista in _candidatos(
                ruta.estado,
                catalogo,
                politica,
                fase,
                grafo,
                atractor,
                deseabilidad,
                None if ruta.alcanzo_destino else destino,
                config,
                relajaciones,
            ):
                tipo, desglose = evaluar_transicion(
                    ruta.estado.actual,
                    pista,
                    grafo=grafo,
                    energia_objetivo=energia_objetivo,
                    bpm_objetivo=bpm_objetivo,
                    es_build=fase.es_build,
                    pesos=pesos,
                    deseabilidad=deseabilidad.para(pista),
                    ignorar_tonal=ignorar_tonal,
                    ignorar_energia=ignorar_energia,
                )

                cedio = atractor.peso(pista.id) > 0
                paso = PasoPlan(
                    pista=pista,
                    minuto_inicio=ruta.estado.minuto,
                    transicion=tipo,
                    desglose=desglose,
                    fase=fase.nombre,
                    cedio_al_voto=cedio,
                )
                expandidas.append(
                    _Ruta(
                        estado=ruta.estado.avanzar(pista, cedio_al_voto=cedio),
                        pasos=ruta.pasos + (paso,),
                        costo=ruta.costo + desglose.costo_total,
                        alcanzo_destino=ruta.alcanzo_destino or pista.id == destino_id,
                    )
                )

        if not expandidas:
            break

        def clave(ruta: _Ruta) -> float:
            if ruta.alcanzo_destino:
                heuristica = 0.0
            else:
                heuristica = _distancia_al_destino(
                    ruta.estado, destino, atractor, grafo, config
                )
            return ruta.costo + pesos.atractor * heuristica

        expandidas.sort(key=clave)
        rutas = expandidas[: config.ancho_haz]

    mejor = rutas[0] if rutas and rutas[0].pasos else None
    return mejor


def _etiquetar_ruta(pasos: tuple[PasoPlan, ...], destino_id: str | None) -> tuple[PasoPlan, ...]:
    """Marca los pasos que forman la escalera hacia lo votado.

    Es lo que le permite a la web decirle a la gente "vamos bajando hacia tu tema,
    quedan 3" — y eso convierte la espera en anticipación en vez de frustración.
    """
    if destino_id is None:
        return pasos
    indice = next((i for i, p in enumerate(pasos) if p.pista.id == destino_id), None)
    if indice is None:
        return pasos
    total = indice + 1
    return tuple(
        replace(p, hacia=destino_id, paso_de=(i + 1, total)) if i <= indice else p
        for i, p in enumerate(pasos)
    )


def _diagnostico_faltante(
    estado: EstadoNoche, destino: Pista | None, config: Config
) -> str | None:
    """Cuando lo votado no es alcanzable, decirlo con precisión.

    Ese mensaje es, además, la lista de compras del record pool.
    """
    if destino is None or estado.actual is None:
        return None
    actual = estado.actual
    equivalente = equivalente_octava(actual.bpm, destino.bpm)
    bajo, alto = sorted((actual.bpm, equivalente))
    return (
        f"lo más votado ({destino.titulo}) no es alcanzable desde acá: "
        f"faltan temas de {destino.genero} entre {bajo:.0f} y {alto:.0f} BPM"
    )


def _plan_emergencia(
    estado: EstadoNoche,
    politica: PoliticaNoche,
    grafo: GrafoGeneros,
    emergencia: Mapping[str, Sequence[Pista]],
    pasos_pedidos: int,
) -> Plan:
    """La tanda que el propio cliente aprobó en el onboarding.

    Sacrifica lo óptimo —puede repetir un tema antes de tiempo o machacar un artista—
    porque el silencio es el único fracaso inaceptable. Lo que **no** sacrifica nunca
    es lo que rompe el ambiente: la lista negra, el salto de género sin puente y la
    regla de no bajar el tempo en el pico se siguen respetando acá adentro.
    """
    pasos: list[PasoPlan] = []
    simulado = estado

    for _ in range(pasos_pedidos):
        fase = politica.fase_en(simulado.minuto)
        actual = simulado.actual
        tanda = [
            p
            for p in emergencia.get(fase.nombre, ())
            if p.id not in politica.lista_negra
            and (p.isrc is None or p.isrc not in politica.lista_negra)
            and (actual is None or grafo.hay_arista(actual.genero, p.genero))
            and (
                actual is None
                or fase.permite_bajar_bpm
                or equivalente_octava(actual.bpm, p.bpm) >= actual.bpm - politica.margen_bajada_bpm
            )
        ]
        if not tanda:
            break

        # entre las que quedan, la que hace menos daño: primero la que hace más que no
        # suena, después la más cercana al tempo objetivo de la fase
        def dano(p: Pista) -> tuple[float, float]:
            desde = simulado.minutos_desde(p.id)
            antiguedad = -(desde if desde is not None else 1e9)
            return (antiguedad, abs(p.bpm - fase.bpm_objetivo))

        pista = min(tanda, key=dano)
        pasos.append(
            PasoPlan(
                pista=pista,
                minuto_inicio=simulado.minuto,
                transicion=TipoTransicion.CORTE_BREAK,
                desglose=Desglose(
                    costo_total=0.0,
                    tempo=0.0,
                    tonal=0.0,
                    genero=0.0,
                    energia=0.0,
                    costura=0.0,
                    deseabilidad=0.0,
                    diferencia_tempo_rel=0.0,
                    bpm_equivalente=pista.bpm,
                ),
                fase=fase.nombre,
                emergencia=True,
            )
        )
        simulado = simulado.avanzar(pista)

    return Plan(pasos=tuple(pasos), costo=0.0, emergencia=True)


# ------------------------------------------------------------------------------ API


def planificar(
    estado: EstadoNoche,
    catalogo: Catalogo,
    politica: PoliticaNoche,
    grafo: GrafoGeneros,
    atractor: Atractor | None = None,
    *,
    senales: Senales | None = None,
    pesos: Pesos | None = None,
    pesos_deseabilidad: PesosDeseabilidad | None = None,
    config: Config | None = None,
    emergencia: Mapping[str, Sequence[Pista]] | None = None,
    pasos: int | None = None,
) -> Plan:
    """Devuelve el plan de los próximos temas desde `estado`.

    Si no encuentra ninguna ruta válida, relaja las restricciones **blandas** en el
    orden declarado (cooldown de artista → energía → tonal) y reintenta. Nunca relaja
    la lista negra ni el salto de género sin arista. Si aun así no hay ruta, cae a la
    tanda de emergencia.
    """
    atractor = atractor if atractor is not None else Atractor()
    pesos = pesos if pesos is not None else Pesos()
    config = config if config is not None else Config()
    pasos_pedidos = pasos if pasos is not None else config.horizonte

    deseabilidad = Deseabilidad(atractor, senales, pesos_deseabilidad)
    destino_id = atractor.destino_principal()
    destino = catalogo.get(destino_id) if destino_id else None

    for nivel in range(len(ORDEN_RELAJACION) + 1):
        relajaciones = relajaciones_hasta(nivel)
        mejor = _buscar(
            estado,
            catalogo,
            politica,
            grafo,
            atractor,
            deseabilidad,
            pesos,
            config,
            relajaciones,
            pasos_pedidos,
        )
        if mejor is None or len(mejor.pasos) < pasos_pedidos:
            continue

        etiquetados = _etiquetar_ruta(mejor.pasos, destino_id)
        faltante = None if mejor.alcanzo_destino else _diagnostico_faltante(estado, destino, config)
        return Plan(
            pasos=etiquetados,
            costo=mejor.costo,
            relajaciones=relajaciones,
            alcanza_atractor=mejor.alcanzo_destino,
            faltante=faltante,
        )

    if emergencia:
        return _plan_emergencia(estado, politica, grafo, emergencia, pasos_pedidos)

    return Plan(pasos=(), costo=0.0, faltante=_diagnostico_faltante(estado, destino, config))


def generar_noche(
    catalogo: Catalogo,
    politica: PoliticaNoche,
    grafo: GrafoGeneros,
    *,
    duracion_min: float = 240.0,
    atractor: Atractor | None = None,
    senales: Senales | None = None,
    pesos: Pesos | None = None,
    config: Config | None = None,
    emergencia: Mapping[str, Sequence[Pista]] | None = None,
    comprometidos: int = 2,
) -> tuple[PasoPlan, ...]:
    """Genera una noche entera replanificando cada `comprometidos` temas.

    Es el modo "en seco" del diseño: sin reproductor, sin audio, sin nube. Sirve para
    auditar un set completo y para correrle encima los tests de propiedad.

    `comprometidos=2` no es una optimización: es el compromiso del diseño. Los próximos
    dos temas ya están pre-decodificados y ya se le anunciaron al público, así que no
    se tocan aunque entre un voto nuevo. Cambiar lo anunciado es peor que un plan
    subóptimo: rompe la confianza, que es lo único que hace que la gente siga votando.
    """
    estado = EstadoNoche()
    reproducidos: list[PasoPlan] = []

    while estado.minuto < duracion_min:
        plan = planificar(
            estado,
            catalogo,
            politica,
            grafo,
            atractor,
            senales=senales,
            pesos=pesos,
            config=config,
            emergencia=emergencia,
        )
        if not plan:
            break
        for paso in plan.pasos[:comprometidos]:
            if estado.minuto >= duracion_min:
                break
            # el minuto real puede diferir del planificado si se replanificó antes
            reproducidos.append(replace(paso, minuto_inicio=estado.minuto))
            estado = estado.avanzar(paso.pista, cedio_al_voto=paso.cedio_al_voto)

    return tuple(reproducidos)

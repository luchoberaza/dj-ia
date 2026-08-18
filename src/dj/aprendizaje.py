"""Nivel 2: aprender de lo que pasó, no de lo que alguien opina.

Este módulo existe por una objeción que resultó correcta: si los DJs y la música que
suenan alrededor son mediocres en promedio, **imitarlos codifica esa mediocridad**. Vale
igual para un DJ como oráculo que para el histórico de un local.

La salida no es dejar de usar esos datos: es usarlos de la otra manera.

    imitar  →  copiar lo que se tocó          → sirve solo si la fuente es buena
    medir   →  registrar qué pasó al tocarlo  → un DJ malo enseña MÁS

Para medir hacen falta **varianza y etiquetas**, no calidad. Un DJ excelente da
doscientas transiciones que funcionaron y ninguna que no; el malo da doscientas de cada
una, y el segundo conjunto es el que enseña.

Dos asimetrías deliberadas, las dos al servicio de "aburrido pero nunca mal":

1. **El sistema puede volverse más conservador solo, nunca más aventurero.** Encarece y
   saca aristas, jamás las agrega. Agregar una arista es una decisión de gusto y le
   corresponde a una persona; sacarla porque la pista se vació es una medición.
2. **Nada se toca con pocas observaciones.** Una mala noche no descalifica a nadie.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from .dominio import GrafoGeneros

#: Cuántas veces tiene que haberse usado una arista antes de que los datos puedan
#: opinar sobre ella. Mismo criterio que el umbral del destilador: una anécdota no es
#: una regla, ni para agregar ni para sacar.
MINIMO_USOS = 8

#: Puntaje medio a partir del cual una arista se encarece, y a partir del cual se saca.
UMBRAL_ENCARECER = -0.20
UMBRAL_REMOVER = -0.50

#: Techo al que se puede encarecer una arista sin llegar a sacarla.
COSTO_MAXIMO = 0.95

#: Cuántas observaciones hacen falta para creerle del todo al rendimiento de un tema.
MINIMO_MUESTRAS = 3

#: Peso de la observación nueva en la media móvil del rendimiento.
FACTOR_MEDIA_MOVIL = 0.30


@dataclass(frozen=True, slots=True)
class PesosResultado:
    """Cuánto pesa cada señal al puntuar qué pasó.

    La ocupación de la pista es la señal soberana cuando existe. Los votos y el salteo
    son los proxies que sí se tienen desde el día uno, porque contar gente requiere
    instrumentación que un local no trae puesta.
    """

    ocupacion: float = 1.00
    salteo: float = 0.60
    votos: float = 0.40


@dataclass(frozen=True, slots=True)
class Resultado:
    """Qué pasó cuando sonó un tema.

    `salteada` es un juicio sobre **el tema**; `transicion_marcada_mala` es un juicio
    sobre **la unión** con el anterior. Mezclarlos haría que un mal empalme condenara a
    un tema que no tiene la culpa.
    """

    id_pista: str
    genero: str
    minuto: float = 0.0
    genero_anterior: str | None = None
    votos_a_favor: int = 0
    votos_en_contra: int = 0
    votantes_activos: int = 0
    salteada: bool = False
    transicion_marcada_mala: bool = False
    ocupacion_antes: float | None = None  # 0..1
    ocupacion_despues: float | None = None

    def puntaje(self, pesos: PesosResultado | None = None) -> float:
        """Qué tan bien salió, en -1..1. Positivo = la pista lo agradeció."""
        p = pesos if pesos is not None else PesosResultado()
        terminos: list[tuple[float, float]] = []

        if self.ocupacion_antes is not None and self.ocupacion_despues is not None:
            delta = self.ocupacion_despues - self.ocupacion_antes
            terminos.append((p.ocupacion, max(-1.0, min(1.0, delta * 3.0))))

        if self.salteada:
            terminos.append((p.salteo, -1.0))

        if self.votantes_activos > 0:
            balance = (self.votos_a_favor - self.votos_en_contra) / self.votantes_activos
            terminos.append((p.votos, max(-1.0, min(1.0, balance))))

        if not terminos:
            return 0.0

        total_peso = sum(peso for peso, _ in terminos)
        return sum(peso * valor for peso, valor in terminos) / total_peso

    @property
    def cambio_de_genero(self) -> tuple[str, str] | None:
        if self.genero_anterior is None or self.genero_anterior == self.genero:
            return None
        return (self.genero_anterior, self.genero)


@dataclass(frozen=True, slots=True)
class Ajuste:
    arista: tuple[str, str]
    accion: str  # "encarecida" | "removida"
    costo_previo: float
    costo_nuevo: float | None
    usos: int
    puntaje_medio: float

    def __str__(self) -> str:
        destino = "sacada del grafo" if self.accion == "removida" else f"{self.costo_nuevo:.2f}"
        return (
            f"{self.arista[0]} → {self.arista[1]}: {self.costo_previo:.2f} → {destino} "
            f"({self.usos} usos, puntaje medio {self.puntaje_medio:+.2f})"
        )


# ------------------------------------------------------------- rendimiento por tema


def actualizar_rendimiento(
    previo: Mapping[str, float],
    resultados: Iterable[Resultado],
    *,
    pesos: PesosResultado | None = None,
    factor: float = FACTOR_MEDIA_MOVIL,
    minimo_muestras: int = MINIMO_MUESTRAS,
) -> dict[str, float]:
    """Media móvil del rendimiento de cada tema en **este** local.

    A los seis meses esta señal vale más que la tendencia global y que cualquier
    corpus, y es la única que ningún competidor puede copiar.

    El valor se atenúa mientras haya pocas muestras: una mala noche no descalifica a un
    tema, solo lo empuja un poco.
    """
    acumulado = dict(previo)
    muestras: dict[str, int] = {}

    for resultado in resultados:
        puntaje = resultado.puntaje(pesos)
        anterior = acumulado.get(resultado.id_pista, 0.0)
        acumulado[resultado.id_pista] = anterior * (1 - factor) + puntaje * factor
        muestras[resultado.id_pista] = muestras.get(resultado.id_pista, 0) + 1

    for id_pista, cantidad in muestras.items():
        confianza = min(1.0, cantidad / minimo_muestras)
        acumulado[id_pista] = round(acumulado[id_pista] * confianza, 4)

    return acumulado


# ----------------------------------------------------------------- ajuste del grafo


def ajustar_grafo(
    grafo: GrafoGeneros,
    resultados: Sequence[Resultado],
    *,
    pesos: PesosResultado | None = None,
    minimo_usos: int = MINIMO_USOS,
    umbral_encarecer: float = UMBRAL_ENCARECER,
    umbral_remover: float = UMBRAL_REMOVER,
) -> tuple[GrafoGeneros, list[Ajuste]]:
    """Encarece o saca las aristas que la pista rechaza. **Nunca agrega ninguna.**

    Si vos pusiste una arista a mano y cada vez que el motor la toma la gente se va, el
    dato te la saca. Al revés no: que una transición no exista en el grafo no genera
    evidencia de que debería existir, porque el motor nunca la prueba. Descubrir
    aristas nuevas es una decisión de gusto y le corresponde a una persona.
    """
    puntajes: dict[tuple[str, str], list[float]] = {}

    for resultado in resultados:
        arista = resultado.cambio_de_genero
        if arista is None or not grafo.hay_arista(*arista):
            continue
        # una transición marcada como mala por el encargado es un juicio directo sobre
        # la unión, así que pesa como el peor resultado posible
        puntaje = -1.0 if resultado.transicion_marcada_mala else resultado.puntaje(pesos)
        puntajes.setdefault(arista, []).append(puntaje)

    aristas = dict(grafo.aristas)
    ajustes: list[Ajuste] = []

    for arista, valores in puntajes.items():
        if len(valores) < minimo_usos:
            continue
        medio = sum(valores) / len(valores)
        if medio > umbral_encarecer:
            continue

        previo = aristas[arista]
        if medio <= umbral_remover:
            del aristas[arista]
            ajustes.append(Ajuste(arista, "removida", previo, None, len(valores), medio))
        else:
            # cuanto peor el puntaje, más cerca del techo queda el costo
            severidad = (umbral_encarecer - medio) / (umbral_encarecer - umbral_remover)
            nuevo = round(min(COSTO_MAXIMO, previo + (COSTO_MAXIMO - previo) * severidad), 3)
            if nuevo > previo:
                aristas[arista] = nuevo
                ajustes.append(
                    Ajuste(arista, "encarecida", previo, nuevo, len(valores), medio)
                )

    ajustes.sort(key=lambda a: a.puntaje_medio)
    return GrafoGeneros(aristas), ajustes


# ------------------------------------------------------------------- usar la cola


def mejores_tramos(
    resultados: Sequence[Resultado],
    *,
    largo: int = 8,
    proporcion: float = 0.2,
    pesos: PesosResultado | None = None,
) -> list[list[Resultado]]:
    """Los tramos que mejor funcionaron, no el promedio.

    Que un local pase mala música **en promedio** no lo vuelve inservible: significa que
    hay que quedarse con la cola. Un boliche donde el 80% de las noches son flojas sirve
    igual, siempre que se pueda identificar el 20%.

    Y el filtro es el resultado, no el criterio de nadie: por eso esto no hereda el
    gusto de quien programó esas noches.
    """
    if largo <= 0 or len(resultados) < largo:
        return []

    ventanas: list[tuple[float, int]] = []
    for inicio in range(len(resultados) - largo + 1):
        tramo = resultados[inicio : inicio + largo]
        ventanas.append((sum(r.puntaje(pesos) for r in tramo) / largo, inicio))

    ventanas.sort(key=lambda v: -v[0])
    cuantas = max(1, int(len(ventanas) * proporcion))

    elegidos: list[list[Resultado]] = []
    usados: set[int] = set()
    for _, inicio in ventanas:
        if len(elegidos) >= cuantas:
            break
        if any(i in usados for i in range(inicio, inicio + largo)):
            continue  # sin solapamiento: dos ventanas corridas no son dos evidencias
        usados.update(range(inicio, inicio + largo))
        elegidos.append(list(resultados[inicio : inicio + largo]))

    return elegidos

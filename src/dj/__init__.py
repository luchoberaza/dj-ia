"""Núcleo de decisión: programa la música de una noche sin romper el ambiente.

Es una librería pura, sin audio, sin red y sin base de datos. Corre igual en la nube y
en el agente del local — ésa es la decisión que hace que el modo sin internet sea
trivial en vez de un proyecto aparte.
"""

from .aprendizaje import (
    Ajuste,
    PesosResultado,
    Resultado,
    actualizar_rendimiento,
    ajustar_grafo,
    mejores_tramos,
)
from .auditoria import Advertencia, auditar, ruta_monotona
from .corpus import Corpus, SetGrabado, TemaDeSet
from .costos import Pesos, evaluar_transicion
from .deseabilidad import Deseabilidad, PesosDeseabilidad, Senales
from .destilacion import Destilado, DistribucionSaltos, destilar
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
from .invariantes import Infraccion, verificar
from .planificador import Catalogo, Config, Plan, PasoPlan, generar_noche, planificar
from .restricciones import Violacion

__all__ = [
    "Advertencia",
    "Ajuste",
    "Atractor",
    "Catalogo",
    "Config",
    "Corpus",
    "Deseabilidad",
    "Desglose",
    "Destilado",
    "DistribucionSaltos",
    "EstadoNoche",
    "Fase",
    "GrafoGeneros",
    "Infraccion",
    "PasoPlan",
    "Pesos",
    "PesosDeseabilidad",
    "PesosResultado",
    "Pista",
    "Plan",
    "PoliticaNoche",
    "Resultado",
    "Senales",
    "SetGrabado",
    "TemaDeSet",
    "TipoTransicion",
    "Violacion",
    "actualizar_rendimiento",
    "ajustar_grafo",
    "auditar",
    "destilar",
    "mejores_tramos",
    "evaluar_transicion",
    "generar_noche",
    "planificar",
    "ruta_monotona",
    "verificar",
]

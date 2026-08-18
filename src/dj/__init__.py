"""Núcleo de decisión: programa la música de una noche sin romper el ambiente.

Es una librería pura, sin audio, sin red y sin base de datos. Corre igual en la nube y
en el agente del local — ésa es la decisión que hace que el modo sin internet sea
trivial en vez de un proyecto aparte.
"""

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
from .invariantes import Infraccion, verificar
from .planificador import Catalogo, Config, Plan, PasoPlan, generar_noche, planificar
from .restricciones import Violacion

__all__ = [
    "Atractor",
    "Catalogo",
    "Config",
    "Deseabilidad",
    "Desglose",
    "EstadoNoche",
    "Fase",
    "GrafoGeneros",
    "Infraccion",
    "PasoPlan",
    "Pesos",
    "PesosDeseabilidad",
    "Pista",
    "Plan",
    "PoliticaNoche",
    "Senales",
    "TipoTransicion",
    "Violacion",
    "evaluar_transicion",
    "generar_noche",
    "planificar",
    "verificar",
]

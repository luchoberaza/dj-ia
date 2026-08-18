from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from dj.catalogo_demo import (  # noqa: E402
    catalogo_demo,
    emergencia_demo,
    grafo_boliche,
    politica_boliche,
    senales_demo,
)
from dj.dominio import Fase, GrafoGeneros, PoliticaNoche  # noqa: E402


@pytest.fixture(scope="session")
def grafo():
    return grafo_boliche()


@pytest.fixture(scope="session")
def politica():
    return politica_boliche()


@pytest.fixture(scope="session")
def catalogo():
    return catalogo_demo(1200, semilla=17)


@pytest.fixture(scope="session")
def senales(catalogo):
    return senales_demo(catalogo, semilla=17)


@pytest.fixture(scope="session")
def emergencia(catalogo, politica):
    return emergencia_demo(catalogo, politica)


@pytest.fixture
def grafo_simple() -> GrafoGeneros:
    return GrafoGeneros({("a", "b"): 0.2, ("b", "a"): 0.2, ("b", "c"): 0.6, ("c", "b"): 0.6})


@pytest.fixture
def politica_simple() -> PoliticaNoche:
    return PoliticaNoche(nombre="test", fases=(Fase("unica", 0, 120, 6.0),))

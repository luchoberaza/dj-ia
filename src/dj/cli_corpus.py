"""Herramientas del nivel 1: destilar un corpus y auditar una configuración.

    python -m dj.cli_corpus destilar datos/corpus-ejemplo.json
    python -m dj.cli_corpus auditar
    python -m dj.cli_corpus auditar --sin-puentes   # reproduce la trampa de tempo (H2)
"""

from __future__ import annotations

import argparse
import sys

from .auditoria import auditar
from .catalogo_demo import ARISTAS_BOLICHE, catalogo_demo, grafo_boliche, politica_boliche
from .corpus import cargar
from .destilacion import destilar
from .dominio import GrafoGeneros

#: Los cuatro puentes cuya ausencia produjo el hallazgo H2.
_PUENTES_DEMBOW = {
    ("cumbia_420", "dembow"),
    ("dembow", "cumbia_420"),
    ("pop_latino", "dembow"),
    ("dembow", "pop_latino"),
}


def _destilar(args: argparse.Namespace) -> int:
    corpus = cargar(args.archivo)
    if args.escena:
        corpus = corpus.de_escena(args.escena)
        if not len(corpus):
            print(f"No hay sets de la escena {args.escena!r}", file=sys.stderr)
            return 1

    print(f"Escenas en el archivo: {cargar(args.archivo).escenas()}\n")
    destilado = destilar(
        corpus, minimo_apariciones=args.minimo, proporcion_minima=args.proporcion
    )
    print(destilado.informe())

    if destilado.grafo.aristas:
        print("\nAristas destiladas (costo · veces vista):")
        for (desde, hacia), costo in sorted(
            destilado.grafo.aristas.items(), key=lambda par: par[1]
        ):
            veces = destilado.transiciones_genero[(desde, hacia)]
            print(f"  {desde:>14} → {hacia:<14} {costo:.2f}  ({veces})")

    if destilado.aristas_descartadas:
        print("\nDescartadas por umbral (no se vuelven regla del motor):")
        for (desde, hacia), veces in sorted(
            destilado.aristas_descartadas.items(), key=lambda par: -par[1]
        ):
            print(f"  {desde:>14} → {hacia:<14} ({veces})")

    return 0


def _auditar(args: argparse.Namespace) -> int:
    catalogo = catalogo_demo(args.catalogo, args.semilla)
    politica = politica_boliche()

    if args.sin_puentes:
        aristas = {p: c for p, c in ARISTAS_BOLICHE.items() if p not in _PUENTES_DEMBOW}
        grafo = GrafoGeneros(aristas)
        print("Auditando con el grafo SIN los puentes hacia dembow (reproduce H2)\n")
    else:
        grafo = grafo_boliche()

    advertencias = auditar(
        list(catalogo), politica, grafo, duracion_noche_min=args.duracion
    )

    print(
        f"Catálogo: {len(catalogo)} temas · política: {politica.nombre} · "
        f"noche de {args.duracion:.0f} min"
    )
    print(f"Grafo: {len(grafo.aristas)} aristas sobre {len(grafo.generos())} géneros\n")

    if not advertencias:
        print("✓ sin advertencias: el catálogo y el grafo sostienen esta política")
        return 0

    bloqueantes = [a for a in advertencias if a.gravedad == "bloqueante"]
    for advertencia in advertencias:
        print(advertencia)

    print(f"\n{len(bloqueantes)} bloqueantes · {len(advertencias) - len(bloqueantes)} avisos")
    return 1 if bloqueantes else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dj-corpus", description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)

    d = sub.add_parser("destilar", help="extraer reglas de un corpus de sets reales")
    d.add_argument("archivo")
    d.add_argument("--escena", default=None, help="destilar solo una escena")
    d.add_argument("--minimo", type=int, default=3, help="apariciones mínimas para una arista")
    d.add_argument("--proporcion", type=float, default=0.01)
    d.set_defaults(funcion=_destilar)

    a = sub.add_parser("auditar", help="chequear catálogo y grafo contra la política")
    a.add_argument("--catalogo", type=int, default=1200)
    a.add_argument("--semilla", type=int, default=17)
    a.add_argument("--duracion", type=float, default=360.0)
    a.add_argument(
        "--sin-puentes",
        action="store_true",
        help="quitar los puentes hacia dembow para reproducir la trampa de tempo",
    )
    a.set_defaults(funcion=_auditar)

    args = parser.parse_args(argv)
    return args.funcion(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

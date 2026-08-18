"""Generación en seco de una noche entera: sin audio, sin nube, sin reproductor.

Es el modo que decide el proyecto. Si el motor programa mal, se descubre acá — antes
de haber escrito una sola línea del reproductor.

    generar-noche --duracion 240 --votos cumbia
"""

from __future__ import annotations

import argparse
import sys
import time

from .catalogo_demo import (
    atractor_demo,
    catalogo_demo,
    emergencia_demo,
    grafo_boliche,
    politica_boliche,
    senales_demo,
)
from .invariantes import verificar
from .planificador import generar_noche

_SIMBOLO = {
    "costura_larga": "≈≈",
    "costura_corta": "≈ ",
    "corte_break": "| ",
    "corte_puente": "‖ ",
}


def _formato_reloj(minuto: float) -> str:
    return f"{int(minuto) // 60:02d}:{int(minuto) % 60:02d}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="generar-noche",
        description="Genera una noche entera en seco y le corre las invariantes.",
    )
    parser.add_argument("--duracion", type=float, default=240.0, help="minutos de noche")
    parser.add_argument("--catalogo", type=int, default=1200, help="tamaño del catálogo")
    parser.add_argument("--semilla", type=int, default=17)
    parser.add_argument(
        "--votos",
        default=None,
        help="género que el público vota (simula el caso difícil: bajar el tempo)",
    )
    parser.add_argument("--motivos", action="store_true", help="mostrar el desglose de costos")
    args = parser.parse_args(argv)

    catalogo = catalogo_demo(args.catalogo, args.semilla)
    politica = politica_boliche()
    grafo = grafo_boliche()
    senales = senales_demo(catalogo, args.semilla)
    emergencia = emergencia_demo(catalogo, politica)
    atractor = atractor_demo(catalogo, args.votos) if args.votos else None

    print(f"Catálogo: {len(catalogo)} temas · política: {politica.nombre}")
    if atractor is not None:
        votadas = [catalogo.get(i) for i in atractor.pistas]
        print("Votado:  " + ", ".join(f"{p.titulo} ({p.bpm:.0f})" for p in votadas if p))
    print()

    arranque = time.perf_counter()
    pasos = generar_noche(
        catalogo,
        politica,
        grafo,
        duracion_min=args.duracion,
        atractor=atractor,
        senales=senales,
        emergencia=emergencia,
    )
    transcurrido = time.perf_counter() - arranque

    fase_previa = None
    anterior = None
    for paso in pasos:
        if paso.fase != fase_previa:
            fase = politica.fase_en(paso.minuto_inicio)
            print(
                f"\n── {paso.fase.upper()} "
                f"(objetivo {fase.bpm_objetivo:.0f} BPM · energía {fase.energia_objetivo:.0f}"
                f"{' · no baja BPM' if not fase.permite_bajar_bpm else ''}) ──"
            )
            fase_previa = paso.fase

        marca = "★" if paso.cedio_al_voto else " "
        ruta = ""
        if paso.paso_de is not None:
            ruta = f"  → paso {paso.paso_de[0]}/{paso.paso_de[1]} hacia lo votado"
        print(
            f"{_formato_reloj(paso.minuto_inicio)} "
            f"{_SIMBOLO.get(paso.transicion.value, '  ')}{marca} "
            f"{paso.pista.bpm:5.1f}  {paso.pista.camelot:>3}  "
            f"E{paso.pista.energia:<4.1f} {paso.pista.genero:<12} "
            f"{paso.pista.titulo}{ruta}"
        )
        if args.motivos:
            print(f"          {paso.motivo(anterior)}")
        anterior = paso.pista

    infracciones = verificar(pasos, politica, grafo)

    print()
    print("─" * 72)
    costuras = sum(1 for p in pasos if p.transicion.es_costura)
    generos = len({p.pista.genero for p in pasos})
    concesiones = sum(1 for p in pasos if p.cedio_al_voto)
    print(
        f"{len(pasos)} temas · {costuras} costuras / {len(pasos) - costuras} cortes · "
        f"{generos} géneros · {concesiones} concesiones al voto · "
        f"planificado en {transcurrido:.2f}s"
    )

    if infracciones:
        print(f"\n✗ {len(infracciones)} INFRACCIONES:")
        for falla in infracciones:
            print(f"  {falla}")
        return 1

    print("\n✓ sin infracciones: ninguna invariante del nivel 0 fue violada")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

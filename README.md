# Motor de programación musical

Programa la música de una noche de baile sin romper el ambiente: mantiene coherencia de
tempo, tonalidad, género y energía, e incorpora lo que el público vota **sin que el voto
rompa la noche**.

> El problema que resuelve, en las palabras que lo originaron: *"la mayoría te pone
> buenos temas pero de la nada te cambia completamente de género sin ningún corte, y eso
> te mata el ambiente"*.
>
> No es la selección de temas. Es la **programación del set**. Y eso es lógica y datos,
> que es justo donde el software le gana al DJ promedio.

Diseño completo: [`docs/superpowers/specs/2026-08-17-dj-ia-diseno.md`](docs/superpowers/specs/2026-08-17-dj-ia-diseno.md)
Hallazgos de la implementación: [`docs/hallazgos-etapa-1.md`](docs/hallazgos-etapa-1.md)

## Estado

Construida la **etapa 1**: el núcleo de decisión y sus tests de propiedad. Es la pieza
que decide si el proyecto sirve, y se valida **en seco** — sin audio, sin reproductor,
sin nube.

| Etapa | Estado |
|---|---|
| 1. Núcleo de decisión + invariantes | ✅ construido |
| 2. Destilador de corpus + auditoría de configuración | ✅ construido — **falta el corpus real** (ver abajo) |
| 3. Analizador de biblioteca (Essentia + madmom) | pendiente |
| 4. Auditoría de sets generados sobre catálogo real | pendiente (necesita 2 y 3) |
| 5. Nube + votación | pendiente |
| 6. Agente reproductor y costura | pendiente |
| 7. Modo degradado y observabilidad | pendiente |

**La etapa 2 está construida pero sin alimentar.** La maquinaria que convierte sets
reales en reglas del motor funciona y está testeada; lo que falta es el corpus, y está
bloqueado por el riesgo **R2** (términos de servicio de las fuentes). Ver
[`docs/formato-corpus.md`](docs/formato-corpus.md). El archivo de ejemplo que viene en
`datos/` es sintético y lo generó el propio motor: **sirve para demostrar el formato y
nada más** — calibrar con él sería circular.

Lo construido es una **librería pura**: sin audio, sin red, sin base de datos. Corre
igual en la nube y en el agente del local, que es lo que hace trivial el modo sin
internet.

## Probarlo

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"

# generar una noche de 6 horas y auditarla
.venv/Scripts/python -m dj.cli --duracion 360

# lo mismo, pero con el público votando cumbia (el caso difícil: baja el tempo)
.venv/Scripts/python -m dj.cli --duracion 360 --votos cumbia --motivos

.venv/Scripts/python -m pytest
```

La salida marca cada transición: `≈≈` costura larga · `≈` costura corta · `|` corte en
break · `‖` corte con puente · `★` cedió al voto.

## Qué hace, medido

Curva de una noche de 6 horas sobre el catálogo sintético de 1200 temas:

| Fase | Objetivo | Logrado | Género dominante | Energía |
|---|---|---|---|---|
| apertura | 96 | **96.2** | cumbia | 4.4 |
| calentando | 104 | **104.1** | cumbia_420 | 7.2 |
| build | 116 | **116.1** | dembow | 8.2 |
| pico | 126 | **125.7** | tech_house | 9.1 |
| meseta | 124 | **123.2** | latin_house | 7.7 |
| cierre | 108 | **108.2** | pop_latino | 5.8 |

Con el público votando cumbia, la misma noche **se dobla sin romperse**: el pico sigue a
126 (la regla dura aguanta) pero migra a cuarteto en vez de tech house, la meseta baja a
113 —dentro del ±10% declarado— y el cierre vuelve a cumbia. El voto torció el rumbo; no
lo rompió.

## Cómo está armado

```
dominio.py       Pista, GrafoGeneros, PoliticaNoche, EstadoNoche, Atractor, Desglose
tempo.py         distancia de tempo módulo octava (95 y 190 son el mismo pulso)
tonalidad.py     rueda Camelot y compatibilidad armónica
costos.py        cuánto cuesta una transición y de qué tipo es
deseabilidad.py  qué tan bueno es un tema ahora (votos, tendencia, histórico local)
restricciones.py las reglas duras: no son costo, son ley
planificador.py  beam search: busca la ruta, no el próximo tema
invariantes.py   nivel 0 de validación: audita PLANES — corre en tests Y en producción
corpus.py        sets reales: el formato de ingesta del nivel 1
destilacion.py   convierte sets reales en el grafo, la tolerancia y las curvas
auditoria.py     audita la CONFIGURACIÓN: trampas de tempo y profundidad por fase
aprendizaje.py   nivel 2: corregirse con lo que se mide, no con lo que se opina
catalogo_demo.py catálogo sintético de boliche argentino, reproducible
cli.py           generación en seco de una noche entera
cli_corpus.py    destilar un corpus · auditar catálogo y grafo
```

Las dos ideas que sostienen todo:

**El voto es un destino, no una instrucción.** Si lo más votado está a 20 BPM y dos
géneros de distancia, el planificador devuelve la escalera de 4 temas que llega. Eso es
lo que convierte la votación de jukebox —que vacía pistas— en navegación.

**El salto de género sin puente es estructuralmente imposible.** No es que el motor
"trate de evitarlo": si no hay arista en el grafo, esa transición no existe como opción.

## Imitar no es lo mismo que medir

La distinción que ordena de dónde puede salir cada regla, y por qué el sistema funciona
aunque lo que suene alrededor sea mediocre:

|  | Qué es | Cuándo sirve |
|---|---|---|
| **Imitar** (nivel 1) | Copiar lo que se tocó | Solo si la fuente es buena. Con material mediocre, basura entra y basura sale |
| **Medir** (nivel 2) | Registrar qué pasó al tocarlo | **Siempre** — y un DJ malo enseña *más*, porque produce ejemplos negativos |

Para medir hacen falta **varianza y etiquetas**, no calidad. Por eso `aprendizaje.py`
tiene dos asimetrías deliberadas:

- **El motor se vuelve más conservador solo, nunca más aventurero.** Encarece y saca
  aristas; jamás las agrega. Sacar una porque la pista se vació es una medición; agregar
  una es una decisión de gusto, y le corresponde a una persona.
- **Nada se toca con pocas observaciones.** Una mala noche no descalifica a nadie.

Y que un local pase mala música *en promedio* no lo vuelve inservible: `mejores_tramos`
se queda con la cola, no con la media. El filtro es el resultado, no el criterio de
nadie.

## Las invariantes

`invariantes.py` audita cualquier plan sin que nadie opine nada:

- ninguna costura supera el 6% de diferencia de tempo (módulo octava)
- no se costura material que el análisis marcó como no costurable
- no hay saltos de género sin puente en el grafo
- no se repite artista consecutivo ni más de N por hora
- no se repite un tema dentro del cooldown
- el tempo nunca baja durante el pico
- el BPM promedio de cada fase cae dentro de su objetivo
- nada de la lista negra suena

Un tramo de **emergencia** puede sacrificar las tres del medio —el silencio es el único
fracaso inaceptable— pero nunca las que rompen el ambiente. Eso está codificado en
`TOLERADAS_EN_EMERGENCIA` y testeado.

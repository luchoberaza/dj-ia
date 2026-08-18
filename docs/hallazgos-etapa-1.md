# Hallazgos de la etapa 1 — construcción del núcleo de decisión

**Fecha:** 17 de agosto de 2026
**Alcance:** lo que la implementación reveló y el diseño no había previsto.

El diseño (`specs/2026-08-17-dj-ia-diseno.md`) no se reescribe. Esto lo corrige y lo
completa.

---

## H1 — Faltaba un término de costo: la curva

**El diseño tenía un hueco.** El modelo de costos original —tempo, tonal, género,
energía, costura— hace que cada transición sea coherente **con la anterior**, pero nada
tiraba del tempo hacia el objetivo de la fase. Resultado: cada transición individual es
correcta y **el set entero deriva**. La curva de la noche existía en la política y no
tenía ningún mecanismo que la hiciera cumplirse.

Se agregó `costo_curva(bpm, bpm_objetivo)` con peso propio.

**Corolario, y costó dos iteraciones descubrirlo:** el término **no puede saturar**
dentro del rango útil. Con un techo a 15% de desvío, un set que está 25% lejos del
objetivo paga lo mismo que uno que está 15% lejos, así que **no tiene ningún incentivo
para acercarse** — el motor se quedaba clavado 20 BPM abajo del pico porque moverse
costaba más que quedarse. La escala también tiene que ser chica (0.08, no 0.15) para
vencer a la inercia del término de tempo.

---

## H2 — El grafo de géneros puede tener trampas de tempo

Con el grafo inicial, la fase de build se quedaba 8% abajo de su objetivo. **No era una
falla del planificador: era el mapa que le dimos.**

El único camino desde el clúster de cumbia (95-108 BPM) hacia arriba pasaba por
reggaetón, que está *más abajo* (88-100). Para subir había que bajar primero, y la curva
—correctamente— castigaba el pozo. El motor se quedaba quieto.

Se agregaron las aristas `cumbia_420 ↔ dembow` y `pop_latino ↔ dembow`. Con eso la fase
de build da exactamente en el objetivo.

**Esto generaliza y es importante para la etapa 2:** un grafo de géneros curado a mano
puede estar topológicamente bien y ser inservible, porque la conectividad no garantiza
que exista una ruta **monótona en tempo**. Cuando se destile el grafo del corpus de sets
reales hay que auditarlo con este criterio, no solo con "¿estos dos géneros van juntos?".

Herramienta pendiente: un chequeo que, para cada par de fases consecutivas de una
política, verifique que existe una ruta en el grafo cuyo tempo sube de forma monótona.

---

## H3 — El plan de emergencia rompía justo lo que no puede romper

La primera versión de la tanda de emergencia ciclaba una lista fija ignorando todo. Los
tests de propiedad la agarraron enseguida: saltos de género sin puente, temas repetidos
a los 13 minutos, y bajadas de tempo en pleno pico.

Quedó formalizado contra la escala de prioridades del diseño:

```
1. Que suene música             ← nunca se sacrifica
2. Que no rompa el ambiente     ← la emergencia TAMPOCO lo sacrifica
3. Que la decisión sea óptima   ← esto sí
4. Que la votación esté viva
```

Un tramo de emergencia puede repetir un tema, machacar un artista y salirse de la curva.
**No puede** saltar de género sin puente, tocar algo de la lista negra, bajar el tempo en
el pico ni costurar material no apto. Está en `TOLERADAS_EN_EMERGENCIA` y tiene tests que
verifican las dos mitades: que tolere lo que debe tolerar y que **no** tolere lo demás.

También se corrigió la tanda: si cubre un solo género queda inalcanzable desde cualquier
otro punto del grafo, que es exactamente cuando se la necesita. Ahora se arma con temas
de todos los géneros y se navega respetando las aristas.

---

## H4 — El mínimo de catálogo del diseño estaba mal planteado

El diseño decía «mínimo operativo ~800 temas» y lo etiquetaba como **Supuesto**. La
implementación muestra que **la métrica está equivocada de raíz**.

Un catálogo de 900 temas dejaba al motor sin material en el pico y lo hacía caer a la
tanda de emergencia, porque solo el 10% del catálogo estaba arriba de 120 BPM. El total
no es el cuello de botella: **lo es la profundidad por fase**.

Formulación correcta, para reemplazar la del diseño:

> Para cada fase, el catálogo necesita al menos `duración_de_la_fase / duración_media` ×
> `factor_de_cooldown` temas cuyo tempo y energía sirvan a esa fase, repartidos en al
> menos dos géneros conectados.

Para el pico de 90 minutos de la política de ejemplo: ~26 temas por noche, y con el
cooldown de artista y la variedad esperada, no menos de ~150 temas aptos de pico. Sobre
un catálogo de 1200, eso es 12%.

**Esto se convierte en una función del onboarding**, no en una nota al pie: el sistema
tiene que auditar el catálogo del cliente contra su política y decirle qué le falta,
**por fase**. Y se conecta directo con la lista de compras del record pool.

---

## H5 — Rendimiento: dos índices hicieron la diferencia

La primera versión tardaba tanto que la suite de tests no terminaba en 10 minutos. Dos
cambios la bajaron a ~0,2 s por replanificación sobre 1200 temas:

1. **Distancias entre géneros precomputadas** (BFS todos-contra-todos al construir el
   grafo). Antes se recorrían todas las aristas por candidato, dentro del bucle interno
   del beam search. Era el cuello de botella dominante.
2. **Índice del catálogo por género.** Desde un tema solo se puede ir a su propio género
   o a los que tienen arista, así que no hace falta mirar el catálogo entero en cada
   expansión del haz.

Más: caché de deseabilidad por plan (no depende del estado) y `heapq.nsmallest` en vez
de ordenar listas completas.

**Nota de diseño, no de optimización:** `generar_noche` consume 2 pasos por
replanificación porque ése es el compromiso declarado en el diseño —los próximos dos
temas ya están pre-decodificados y anunciados al público—. Que además reduzca a la mitad
el costo de planificación es una consecuencia, no el motivo.

---

## H6 — Detalles que quedaron mejor de lo diseñado

- **Frescura y fatiga** estaban listadas como señales separadas en el diseño. Son los dos
  extremos del mismo eje y contarlas dos veces sesga el puntaje. Se unificaron en
  `rotacion`.
- **El techo del voto quedó declarado en la política** (`max_desvio_voto`, 10%) en vez de
  ser una constante escondida en el planificador. Tiene que ser menor que la tolerancia
  con la que se audita el promedio de la fase (15%), y ahora esa relación es visible y
  configurable por establecimiento.
- **`Desglose` guarda el desvío firmado y el objetivo de la fase**, así que la
  explicación de cada decisión incluye hacia dónde iba la curva, no solo de dónde venía.

---

## Lo que sigue

La etapa 1 demuestra que el motor **no puede** cometer las fallas del problema. Lo que
todavía **no** demuestra es que sus decisiones tengan buen gusto: eso lo dan las etapas 2
(corpus) y 4 (auditoría sobre catálogo real). El catálogo con el que se probó es
sintético, y sus rangos de BPM salen de tablas de referencia, no de música real.

# Formato del corpus de sets reales

El corpus es la fuente de verdad del **nivel 1** de validación: sets que alguien tocó de
verdad ante una pista de verdad. De ahí sale el grafo de géneros, la distribución real
de saltos de tempo y la forma de la curva — medidos, no opinados.

## El archivo

JSON. Un objeto con `sets`, o directamente una lista de sets.

```json
{
  "sets": [
    {
      "id": "br-2019-06-29-kettama",
      "fuente": "1001tracklists",
      "escena": "edm",
      "url": "https://...",
      "temas": [
        { "posicion": 1, "artista": "...", "titulo": "...",
          "genero": "tech_house", "bpm": 126.0, "camelot": "8A", "energia": 7 },
        { "posicion": 2, "artista": "...", "titulo": "..." }
      ]
    }
  ]
}
```

### Campos

| Campo | Nivel | Obligatorio | Nota |
|---|---|---|---|
| `id` | set | no | se genera si falta |
| `fuente` | set | no | de dónde salió: `1001tracklists`, `radio`, `local`… |
| `escena` | set | **sí en la práctica** | ver abajo |
| `url` | set | no | para poder volver al original |
| `posicion` | tema | no | se infiere del orden |
| `artista`, `titulo`, `isrc` | tema | no | identificación |
| `genero` | tema | para el grafo | |
| `bpm` | tema | para la distribución de saltos | |
| `camelot` | tema | para los movimientos armónicos | |
| `energia` | tema | para la curva de energía | 1-10 |

**Casi todo es opcional a propósito.** Un tracklist real trae artista y título, nada
más. El resto llega después, enriqueciendo contra Deezer por ISRC y contra el analizador
de biblioteca. Muchas veces no llega.

Por eso el destilado **reporta la cobertura de cada campo**: un corpus de 500 sets con
30% de cobertura de BPM da una distribución de saltos basada en el 30%, y decir "500
sets" a secas sería mentir por omisión.

### La escena no es opcional en los hechos

El gusto no es universal. `cumbia → reggaetón → perreo → cuarteto` es una ruta
perfectamente válida en un boliche argentino y no significa nada en Berlín. Destilar las
dos escenas juntas produce un promedio que no le sirve a ninguna de las dos.

Etiquetá cada set con su escena y destilá una por vez:

```bash
python -m dj.cli_corpus destilar corpus.json --escena boliche_ar
```

## Fuentes, y en qué estado está cada una

> ### Antes de elegir una fuente: imitar no es lo mismo que medir
>
> Un corpus se puede usar de dos maneras completamente distintas, y confundirlas es el
> error que casi cometemos.
>
> **Imitar** — copiar lo que se tocó, aprender "esto va después de esto porque acá lo
> hacen así". Sirve **solo** si la fuente es buena. Con material mediocre, basura entra
> y basura sale.
>
> **Medir** — registrar qué pasó *cuando* se tocó. Acá la lógica se da vuelta: **un DJ
> malo es un mejor maestro que uno bueno**, porque produce muchos ejemplos negativos.
> No hace falta calidad, hacen falta **varianza y etiquetas**. Un DJ excelente da 200
> transiciones que funcionaron y ninguna que no; el malo da 200 de cada una, y el
> segundo conjunto enseña más.
>
> **Este archivo documenta la ingesta para IMITAR (nivel 1).** Todo lo que se destile de
> acá sale de suponer que la fuente sabe lo que hace. Los datos del propio local son
> otra cosa —nivel 2, medición— y no entran por este formato.

| Fuente | Cobertura | Estado |
|---|---|---|
| **1001Tracklists** | Muy buena en electrónica: Boiler Room, Essential Mix, festivales | ⚠️ **Bloqueado por R2**: hay que resolver los términos de servicio antes de escribir el ingestor |
| **Reconstrucción por huella acústica** de mixes publicados | La única vía razonable para lo latino | ⚠️ **Bloqueado por R2**: descargar de Mixcloud/SoundCloud probablemente viola sus términos |
| **Airplay de radio** | Programación musical profesional, con curva. La programan programadores musicales, no el DJ del boliche: es otro oficio y otro nivel | Vía limpia, pendiente de explorar. **La mejor candidata para lo latino** |
| **Grafo curado a mano** | 10 géneros y ~30 aristas: es poquísimo conocimiento | Disponible ya. Ver abajo |

### El grafo curado a mano no es un plan B

~~El histórico de un local que funciona era la mejor fuente.~~ **Corregido:** el
histórico del local **no es una fuente de imitación**, porque la música que suena en un
local promedio es promedio. Es un conjunto de datos de nivel 2 —medición— y ahí su valor
está intacto: no se copia lo que se tocó, se mide qué vació la pista.

Para lo único genuinamente cultural —qué género puede seguir a cuál— no hacen falta
miles de sets. Son unas treinta preguntas del tipo "¿de cumbia se puede saltar a
cuarteto?", y las puede contestar **una** persona con criterio.

El grafo curado arranca el sistema sin depender de ningún corpus ni de ningún DJ.
Después el nivel 2 lo corrige con datos: si una arista curada a mano vacía la pista cada
vez que el motor la toma, el dato la saca.

`dj/catalogo_demo.py::ARISTAS_BOLICHE` es un grafo curado de ejemplo, y
`dj.cli_corpus auditar` verifica que cualquier grafo curado sostenga la política antes
de que llegue a producción.

**No hay ningún ingestor escrito todavía, y es deliberado.** El destilador
(`dj/destilacion.py`) está construido y testeado contra corpus de prueba; los
adaptadores de fuente se escriben cuando cada fuente esté resuelta legalmente. El punto
de entrada para cualquiera de ellos es `dj.corpus.desde_diccionarios`.

## Qué sale del destilado

```bash
python -m dj.cli_corpus destilar datos/corpus-ejemplo.json
```

- **El grafo de géneros** con el costo de cada arista sacado de su frecuencia. Una
  transición que aparece menos de 3 veces **no** se convierte en arista: un DJ haciendo
  algo raro una noche no puede volverse una regla del motor. Lo descartado se reporta.
- **La distribución de saltos de tempo**, con un veredicto explícito sobre el ±6% del
  diseño: si el p95 real está en 4%, la tolerancia es generosa; si está en 9%, el motor
  es más conservador que los DJs que dice imitar.
- **Los movimientos de Camelot** que se usan de verdad, contra los del manual.
- **La forma de la curva** de tempo (relativa al promedio de cada set) y de energía.

## Después de destilar: auditar

Un grafo destilado puede estar perfectamente conectado y ser inservible. Antes de usarlo:

```bash
python -m dj.cli_corpus auditar
python -m dj.cli_corpus auditar --sin-puentes   # reproduce la trampa de tempo de H2
```

La auditoría chequea que exista una ruta con tempo monótono entre fases consecutivas y
que el catálogo tenga profundidad suficiente **por fase**. Ver `hallazgos-etapa-1.md`
(H2 y H4).

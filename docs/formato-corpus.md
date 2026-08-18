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

| Fuente | Cobertura | Estado |
|---|---|---|
| **1001Tracklists** | Muy buena en electrónica: Boiler Room, Essential Mix, festivales | ⚠️ **Bloqueado por R2**: hay que resolver los términos de servicio antes de escribir el ingestor |
| **Reconstrucción por huella acústica** de mixes publicados | La única vía razonable para lo latino | ⚠️ **Bloqueado por R2**: descargar de Mixcloud/SoundCloud probablemente viola sus términos |
| **Airplay de radio** | Programación musical profesional, con curva | Vía limpia, pendiente de explorar |
| **Histórico de un local que funciona** | **La mejor de todas** para lo latino | Requiere un local piloto. Un mes de registro es el corpus que no existe en internet |

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

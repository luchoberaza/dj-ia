# Diseño — Sistema de programación musical automática para pistas de baile

**Fecha:** 17 de agosto de 2026
**Estado:** diseño aprobado, sin implementación
**Ruta:** arquitectónica (proyecto nuevo)

---

## 1. Qué es esto

Un sistema que programa y reproduce la música de un local bailable (boliche, bar, evento),
manteniendo coherencia de tempo, tonalidad, género y energía a lo largo de la noche, e
incorporando lo que el público vota **sin que el voto rompa la noche**.

Funciona en dos modos sobre el mismo motor:

- **Autónomo** — el sistema reproduce y costura las transiciones. Reemplaza al DJ.
- **Copiloto** — el sistema sugiere el próximo tema y la ruta; el DJ decide. Lo complementa.

## 2. El problema real que resuelve

> *"Es raro encontrar buenos DJ. La mayoría te pone buenos temas pero de la nada te cambia
> completamente de género sin ningún corte ni nada, y eso te mata el ambiente."*

Esa frase es la especificación del producto. Traducida:

**El problema no es la selección de temas. Es la programación del set.** Los temas eran buenos;
falló el orden y la costura entre uno y otro.

De las tres habilidades de un DJ:

| Habilidad | ¿Automatizable? |
|---|---|
| Leer la pista (mirar a la gente, sentir el clima) | Muy difícil |
| Técnica de mezcla (beatmatch, EQ, efectos en vivo) | Sí, resuelto hace años |
| **Programación del set** (qué va después de qué, cómo se construye la curva) | **Sí, y es donde una máquina gana** |

El producto ataca la tercera, que es donde el software es estructuralmente superior al DJ promedio:
nunca se olvida de que venía a 128, nunca salta de género porque se acordó de un tema que le gusta,
nunca se distrae.

## 3. Posicionamiento

**No es "un DJ con IA".** Esa promesa es imposible de cumplir y genera rechazo en el DJ, que
tiene que ser aliado, no enemigo.

> **Es un sistema que garantiza que la transición nunca te rompa el ambiente.**

Vende **consistencia**, no genialidad. Un DJ bueno tiene picos más altos que el sistema, y eso está
bien: no competimos ahí. El sistema no tiene valles.

**El benchmark no es el mejor DJ del mundo — es el DJ que está disponible.** Si los DJs disponibles
fueran excelentes, el producto no tendría mercado.

De ahí el principio de diseño que gobierna todos los pesos del motor:

> **Aburrido pero nunca mal, antes que brillante con riesgo de catástrofe.**

Para un boliche, una hora arruinada cuesta más de lo que rinden diez horas geniales. Ante empate,
gana la opción conservadora.

**Métrica de éxito:** no "¿suena lindo?" sino **cuántas veces por noche se vació la pista**.

## 4. Decisiones tomadas

| # | Decisión | Motivo |
|---|---|---|
| D1 | Dos modos (autónomo + copiloto) sobre **un solo motor** | El núcleo de decisión es idéntico; solo cambia la salida |
| D2 | **Enfoque híbrido**: nube + agente local | La votación necesita alcance público; la reproducción necesita estar en el local |
| D3 | El **núcleo de decisión corre en los dos lados** | Hace que el modo sin internet sea trivial en vez de un proyecto aparte |
| D4 | Audio = **archivos del establecimiento** (record pool / compra) | Único camino legalmente limpio y musicalmente viable |
| D5 | Metadata = **catálogo abierto** (Deezer + MusicBrainz + Last.fm), unido por **ISRC** | Spotify cerró sus endpoints; el ISRC une todo sin depender de nombres de archivo |
| D6 | Análisis de audio **local con Essentia + madmom**, no API externa | Sin cuotas, sin huecos de cobertura, con downbeats |
| D7 | Transición = **costura musical inteligente**, no beatmatch en vivo | ~20% del trabajo, ~90% del resultado; y no se rompe con música de tempo variable |
| D8 | El motor arranca con **reglas explícitas**, no con machine learning | Un motor inexplicable es invendible a un dueño de local |
| D9 | El voto es un **destino**, no una instrucción | Es la diferencia entre este producto y un jukebox |
| D10 | El gusto se aprende de **corpus de sets reales**, no de un DJ local | Ver §11 |

## 5. Arquitectura general

```
┌─────────────────── NUBE ────────────────────┐
│  Catálogo universal (Deezer / MusicBrainz)  │
│  Cuentas · configuración por establecimiento│
│  Votación en vivo (WebSockets)              │
│  Tendencias (Last.fm / charts)              │
│  Analytics · panel de salud                 │
│  ► núcleo de decisión (copia informada)     │
└──────────────────┬──────────────────────────┘
                   │ plan + política (bajada anticipada)
                   │ eventos + heartbeat (subida)
┌──────────────────▼─────── LOCAL ────────────┐
│  Biblioteca de archivos + análisis          │
│  ► núcleo de decisión (copia autónoma)      │
│  Agente reproductor (2 decks + costura)     │
└─────────────────────────────────────────────┘

           ┌─── PÚBLICO ───┐        ┌─── ENCARGADO / DJ ───┐
           │ web por QR    │        │ panel de control     │
           │ vota y ve la  │        │ saltear · vetar      │
           │ ruta          │        │ empujar fase         │
           └───────────────┘        └──────────────────────┘
```

### Stack

| Pieza | Elección | Motivo |
|---|---|---|
| Análisis + núcleo de decisión | **Python** | Essentia, madmom y librosa son Python; el ecosistema MIR entero está ahí |
| Nube | **FastAPI + PostgreSQL** | Mismo lenguaje que el núcleo — el motor se comparte literalmente |
| Votación en vivo | **WebSockets** | Votos y "sonando en ~X min" se mueven solos |
| Web de votación | **Mobile-first ultraliviana** | Se abre por QR con datos móviles en un sótano; cada 100 ms son votantes perdidos |
| Agente reproductor | **Python + `sounddevice` + `numpy`** | Dos decks con ganancia, filtro y rampa de tempo son ~400 líneas de numpy |

**Riesgo de audio en Python** (una pausa del recolector de basura = hueco audible): se neutraliza con
buffer grande (~2048 muestras, ~46 ms — irrelevante porque no hay performance en vivo) y
**pre-decodificando el próximo tema completo a RAM** antes de la transición. El callback de audio
solo suma arrays ya listos.

---

## 6. Modelo de datos y las dos capas

**El ISRC es la columna vertebral.** Cada grabación comercial tiene uno, único e internacional. Es
lo que permite afirmar que el archivo del disco del local **es** el mismo tema que la gente vota en
la web, sin depender de cómo esté escrito el nombre.

### Capa Catálogo (nube, compartida entre todos los locales)

```
grabacion        isrc (PK) · titulo · artista · album · anio · duracion_ms
                 generos[] · deezer_id · mbid · preview_url
senal_tendencia  isrc → fuente (lastfm|chart) · valor · fecha
                 (histórico, no snapshot: permite ver si un tema sube o baja)
```

Se comparte entre clientes. Un tema analizado o corregido una vez sirve para todos.

### Capa Biblioteca (por establecimiento)

```
establecimiento  nombre · zona_horaria · config
pista            archivo · isrc (nullable) · establecimiento
                 ── análisis ──
                 bpm · bpm_confianza · bpm_octava_ambigua (bool)
                 camelot · camelot_confianza
                 energia (1-10) · loudness_lufs
                 grilla_beats[] · downbeats[]
                 ── puntos de mezcla ──
                 mix_in_ms · mix_out_ms · es_extended
                 ── control ──
                 genero_asignado · estado_analisis · revisada_por_humano
                 apta_para_costura (bool)
```

Dos campos que parecen menores y son los que evitan que el sistema se rompa:

**`*_confianza`** — el análisis devuelve un valor **y** qué tan seguro está. BPM con confianza baja
(cumbia vieja, grabación en vivo, tempo que respira) ⇒ `apta_para_costura = false`. El tema **no se
descarta**: se programa igual, pero entra por corte limpio en break. Esto es lo que evita que el
~20% del catálogo latino haga explotar al motor.

**`mix_in_ms` / `mix_out_ms`** — dónde termina la intro y dónde arranca el outro. Es el corazón de
la costura. Se detectan solos y se corrigen a mano en segundos desde el panel.

### Configuración y grafo (por establecimiento, con default global)

```
genero           nombre canónico (vocabulario del cliente, en español)
arista_genero    desde → hacia · costo (0-1) · establecimiento (nullable = global)
politica_noche   fases: [{ desde_hora, bpm_objetivo, energia_objetivo,
                           generos_permitidos[], voto_puede_bajar_bpm }]
lista_negra      isrc/pista que nunca suena en este local
```

El grafo arranca con un **default global** curado (ver §11) y cada local lo pisa donde quiera. El
grafo de un boliche de cumbia y el de un after no son el mismo grafo. **Es cultural, no universal.**

### Operación (histórico — el activo a largo plazo)

```
sesion_noche         establecimiento · inicio · fin · politica_aplicada
evento_reproduccion  sesion · pista · hora · tipo_transicion · motivo_decision
                     votos_recibidos_durante · saltada_por (nullable)
voto                 sesion · dispositivo_hash · tipo (cancion|genero)
                     objetivo · peso · timestamp
```

`motivo_decision` no es un lujo: es **por qué el motor eligió ese tema**. Sirve para depurar una
mala noche, para convencer al DJ escéptico y para responderle al dueño.

### La brecha entre capas es una función vendible

La gente vota sobre el catálogo universal; el local solo tiene una parte. Ese hueco genera:

> *"Tu público votó 47 veces temas que no tenés. Acá está la lista, están todos en tu record pool."*

El sistema le dice al local qué música comprar según lo que su propia pista pide. Nadie lo hace.

---

## 7. El analizador de biblioteca

Corre **en el local**, una vez por archivo, sin apuro (la primera pasada puede tardar horas: se hace
un martes a la tarde, no un sábado a las 2).

**Pipeline por archivo:**

1. **Identificar** — leer tags. Sin ISRC → huella acústica (Chromaprint/AcoustID) → MusicBrainz →
   ISRC → enriquecer contra Deezer. Si no resuelve: queda con la metadata del archivo, marcado para
   revisión.
2. **Analizar** — `madmom` para beats y downbeats; `Essentia` para tonalidad, loudness, danceability
   y descriptores. Cada resultado sale con su confianza.
3. **Resolver la octava** — 87 vs 174 BPM. Se desambigua contra el género esperado y la densidad de
   onsets. Si sigue ambiguo → `bpm_octava_ambigua = true` y a la cola de revisión.
4. **Encontrar los puntos de mezcla** — primer elemento percusivo sostenido (fin de intro) y punto
   donde el final se vacía (inicio de outro), alineados al downbeat más cercano. Con ediciones
   extended de record pool sale casi perfecto.
5. **Decidir si es costurable** — confianza de BPM baja, o tempo que varía más del umbral, o sin
   outro usable ⇒ `apta_para_costura = false`.

**Cola de revisión** (parte del producto, no un parche): pantalla donde el encargado ve los temas
dudosos **ordenados por cuánto importan** (los más votados primero), escucha 10 segundos y confirma
o corrige. Con 30 minutos sobre los 200 temas que más suenan, el sistema queda afinado.

El resultado se sube al **catálogo compartido por ISRC**: el próximo cliente que tenga ese tema ya
lo recibe analizado y corregido. El sistema mejora solo con cada local que se suma.

---

## 8. El núcleo de decisión

Es la pieza que define si el producto sirve. Todo lo demás es plomería.

### No elige el próximo tema: planifica una ruta

Un jukebox pregunta *"¿qué pongo ahora?"*. Este motor pregunta *"¿cuál es el camino de acá a donde
la pista quiere ir?"*. Mantiene un **plan de 6 a 8 temas hacia adelante** y lo recalcula cuando
entra información nueva.

Es formalmente un **problema de búsqueda de ruta en un grafo**: nodos = temas, aristas =
transiciones posibles, cada arista con costo. El planificador **encuentra la rampa solo**.

### Dos preguntas distintas que no hay que mezclar

```
puntaje(candidato B) = deseabilidad(B)  −  costo_transicion(A → B)
                       ¿qué tan bueno       ¿cuánto cuesta llegar
                        es este tema         hasta él desde lo que
                        ahora mismo?         está sonando?
```

#### Deseabilidad

| Señal | Fuente |
|---|---|
| Votos directos | La gente lo pidió, ahora |
| Tendencia global | Last.fm playcounts + charts |
| **Rendimiento en ESTE local** | Histórico propio: cuando sonó, ¿la pista aguantó? |
| Frescura | Hace cuánto no suena |
| Fatiga | Penalización por haber sonado mucho últimamente |

El tercero, a los seis meses, vale más que todos los demás juntos, y **es el único que ningún
competidor puede copiar**.

#### Costo de transición

```
costo(A,B) = w_tempo·tempo + w_tonal·tonal + w_genero·genero
           + w_energia·energia + w_costura·costura
```

**Tempo** — diferencia **módulo octava** (95 y 190 = distancia cero), normalizada como porcentaje
del tempo de A. Costo 0 hasta ±3 BPM, sube suave hasta 6%, y más allá del 6% se vuelve prohibitivo
*para costura* pero sigue permitido *por corte*. El motor no descarta el tema: cambia el tipo de
transición.

**Tonal** — Camelot: 0 mismo código; bajo para ±1 misma letra y para A↔B mismo número; medio para
+2; alto para el resto. **Si alguno tiene confianza tonal baja, el término se neutraliza en vez de
castigar.** No se penaliza por un dato que no se conoce.

**Género** — costo de la arista del grafo. **Sin arista ⇒ infinito para costura.** Acá vive
literalmente la queja original: *"de la nada te cambia de género"* es, en este modelo, una arista
que no existe. El motor no puede tomarla — no es que "trata de evitarlo".

**Energía** — distancia a la energía **objetivo de la fase**, no a la del tema anterior. Asimétrico:
bajar energía durante el build cuesta mucho más que subirla.

**Costura** — si alguno no es `apta_para_costura`, el costo sube y la transición se marca como corte.

### Restricciones duras (no son costo: son ley)

No se negocian con ningún peso ni ningún voto:

- Cooldown por tema (no se repite en X horas) y por artista (nunca dos seguidos, máximo N por hora)
- Lista negra del establecimiento
- **En fase de pico, el voto no puede bajar el BPM**
- Cupo máximo de concesiones al voto por hora
- No salir de los géneros permitidos de la fase

> Un voto puede torcer el rumbo. No puede romper la noche.

### El planificador

**Beam search** (mantener las K mejores rutas parciales, expandir, podar). Más simple que A\*, más
fácil de depurar, y para 6-8 pasos sobre un catálogo de miles de temas corre en milisegundos.

- **Estado:** tema actual, BPM, Camelot, género, energía, hora, historial reciente
- **Objetivo:** un **atractor** (no un tema): lo más votado con sus pesos + el punto de la curva de
  la noche donde deberíamos estar
- **Expansión:** candidatos que pasan las restricciones duras, ordenados por puntaje
- **Poda:** rutas que no acercan al atractor dentro del horizonte

Si el tema más votado está a 20 BPM y dos géneros de distancia, devuelve la escalera de 4 temas que
llega. Si **no existe ruta válida**, lo dice explícitamente: *"lo más votado no es alcanzable desde
acá; faltan temas de X entre 105 y 115 BPM"* — y eso alimenta la lista de compras del record pool.

### Replanificación y compromiso

Se recalcula ante cualquier voto que mueva el atractor, un salteo manual o un cambio de fase.
**Pero los próximos 2 temas quedan congelados**: ya están pre-decodificados y ya se anunciaron al
público. Cambiar lo anunciado es peor que un plan subóptimo — rompe la confianza, que es lo único
que hace que la gente siga votando.

### Explicabilidad (no es opcional)

Cada decisión guarda su desglose:

> *"Elegí **Tema X**: tempo 124→126 (+1.6%, costo 0.08) · Camelot 8A→9A (0.12) · mismo género (0) ·
> energía 7 vs objetivo 7 (0) · **paso 2 de 4 hacia «Tema Votado» (312 votos)**"*

Sirve para depurar, para convencer al DJ y —lo más importante— **para responderle al dueño**. Por lo
mismo el motor arranca con reglas explícitas, no con ML. Recién con meses de `evento_reproduccion`
acumulado tiene sentido ajustar pesos automáticamente por local, y aun ahí **sobre** las reglas, no
reemplazándolas.

---

## 9. Votación y anti-abuso

**Mucha influencia, cero control.**

### Entrada: fricción cero

QR en mesas, barra, baños y pantallas → URL corta → se vota. Sin app, sin registro, sin login.
Sesión anónima con cookie. Debe cargar en menos de un segundo con dos rayas de señal en un sótano.

El QR es **por local y por noche, y rota**. El voto no persiste entre noches ni se emite desde afuera.

### Dos carriles

| Carril | Qué es | Quién lo usa |
|---|---|---|
| **Vibra** | 4-5 botones de un toque: *más cumbia · más reggaetón · subir · bajar un cambio* | El 90% de la gente |
| **Canción** | Buscador sobre el catálogo completo de Deezer | La minoría con un tema en la cabeza |

El carril de vibra mueve la noche de verdad. El de canción se ve mejor en la demo. No confundirlos.

En el buscador cada resultado se marca **✅ está en el local** o **⏳ no lo tienen**. Los ⏳ se
registran igual: son la lista de compras.

### Anti-abuso, por capas

1. **Presupuesto de votos** (créditos por hora que se recargan lento), no votos ilimitados.
2. **Peso decreciente por votante** ← la capa que realmente resuelve el problema.
   1.0 · 0.6 · 0.36 · 0.22 …
   → 8 amigos × 10 votos ≈ **19 puntos** · 40 personas × 1 voto = **40 puntos**.
   El grupito no le gana a la pista, y nadie ve un mensaje de error.
3. **Detección de coordinación** — dispositivos conectados en la misma ventana de 2 minutos votando
   todos lo mismo se agrupan como cluster con peso conjunto. Es el patrón de "la mesa de la esquina".
4. **Anclaje al lugar** — el QR proyectado cambia cada pocos minutos: hay que estar ahí para votar.
   Mejor que atar al WiFi, porque no exige que nadie se conecte a nada.
5. **Rate limit + fingerprint liviano** contra scripts obvios.

**Honestidad:** nada de esto aguanta a un atacante técnico decidido, y está bien — ése no es el
enemigo. El enemigo es la mesa de ocho que quiere su tema. Un anti-fraude real exige login, y el
login mata la participación, que es el activo del producto.

6. **El techo real no es criptográfico, es musical.** Aunque se rompieran todas las capas
   anteriores, el cupo de concesiones por hora y las restricciones duras siguen intactos.
   **Un voto perfectamente manipulado sigue sin poder romper la noche.**

### Cómo entra el voto al motor

No es una cola. Alimenta el atractor:

- **Vibra** → mueve el objetivo de género y energía de la fase, dentro de lo que la política permita
- **Canción** → suma a `deseabilidad`; el más fuerte se vuelve destino de ruta
- **Decaimiento temporal** → un voto de hace 40 minutos pesa una fracción de uno de hace 3

### Voto negativo: señal, no control

Se registra pero **no ejecuta**. Alimenta el histórico del local y baja la deseabilidad futura de
ese tema ahí.

**Única excepción:** si el rechazo supera un umbral alto en poco tiempo (orden del 40% de los
dispositivos activos en 30 segundos), eso ya no es opinión, es **la pista vaciándose en vivo**. Ahí
el motor acorta el tema y adelanta la transición. Es la única intervención en tiempo real, y es
justo la situación que el producto existe para evitar.

### El feedback: la parte que decide si el sistema funciona

Si votás y no pasa nada visible, no votás más, y el motor se queda ciego.

- **"Sonando en ~8 min"** con el tema y su lugar en la fila. Es la frase que define el producto: no
  promete *ahora*, promete *un momento*, y cumple.
- **La ruta visible** — *"vamos bajando hacia tu tema, quedan 3"*. La gente ve que la escucharon
  **y entiende por qué no es inmediato**. Convierte la espera en anticipación. Ningún competidor lo
  hace, porque ninguno planifica rutas.
- **Aviso cuando suena.**
- **Pantalla en el local** con el top y el próximo: vuelve la votación social y se contagia.

### Lo que la gente nunca puede hacer

Saltear el tema actual · votar algo de la lista negra · forzar un tema fuera de fase · bajar el BPM
en el pico.

### Panel del encargado

Para usar a oscuras: pausar votación · saltear · vetar en el momento · empujar fase (*pico ya* /
*bajemos*) · **modo evento** (cumpleaños, tanda especial: sale de la política normal por N minutos).

---

## 10. El agente reproductor y la costura

### Regla de arquitectura: el audio no depende de nada que pueda trabarse

| Hilo | Hace | Tiene prohibido |
|---|---|---|
| **Audio** (prioridad alta) | Sumar arrays ya decodificados, aplicar ganancias y filtros | Tocar disco, red, base de datos o reservar memoria |
| **Control** (normal) | Hablar con la nube, decidir, pre-decodificar, preparar buffers | Bloquear al hilo de audio |

Comunicación por doble buffer sin locks. Una caída de internet, una consulta lenta o una pausa del
GC no producen huecos audibles.

### Máquina de estados de los decks

Dos decks alternando: `vacío → cargando → listo → sonando → costurando → terminando → vacío`.

**Un tema no entra en `listo` hasta estar 100% decodificado en RAM.** ~50 MB por tema; tres en
memoria son 150 MB. Cuando arranca la costura no hay disco de por medio.

### Anatomía de una costura

Al llegar A a su `mix_out_ms`, cinco cosas — las cinco importan:

1. **Alineación de frase** — el arranque de B se alinea al **downbeat** de A. Sin esto la costura
   suena corrida aunque los BPM coincidan. Es la diferencia entre sonar a DJ y sonar a reproductor
   de escritorio.
2. **Rampa de tempo** — dentro del 6%, A se lleva suavemente hasta el tempo de B a lo largo de 16-32
   tiempos, con key-lock. Repartido así, nadie lo percibe. (Se puede hacer al revés; el motor elige
   según hacia dónde va la curva.)
3. **Crossfade de potencia constante** (coseno/seno, no lineal). El crossfade lineal produce un
   bache de volumen en el medio: es el error más común y el más audible.
4. **Filtro en la unión** — pasa-altos que sube sobre A mientras baja su volumen; B entra con sus
   graves enteros. Evita el barro de dos bombos y dos bajos encima. **Es lo que hace un DJ con la
   perilla de graves, y es la mitad de por qué una mezcla suena limpia.**
5. **Normalización de sonoridad** por LUFS. Sin esto, un máster de 2004 entra 6 dB más bajo que uno
   de 2024 y la pista lo siente como un bajón de energía que no existe.

### Cuatro tipos de transición

| Tipo | Cuándo | Qué hace |
|---|---|---|
| **Costura larga** | Ambos aptos, <3% de tempo, género y tonalidad compatibles | 32 tiempos de crossfade con filtro |
| **Costura corta** | Aptos, con más distancia | 8-16 tiempos, filtro más agresivo |
| **Corte en break** | Alguno no apto, o salto grande | A termina en su último downbeat de frase; B entra limpio (barrido o impacto opcional) |
| **Corte con puente** | Cambio de bloque, fin de tanda | Silencio muy breve o efecto |

> **El corte no es el fracaso.** Un corte al final de una frase de 8 o 16 compases suena
> **intencional**. Lo que suena a error es el corte arbitrario, a mitad de frase.

Por eso el catálogo con análisis dudoso no queda afuera: entra por corte limpio y suena bien.
**Nunca se intenta una costura que no se puede sostener.** Ése es todo el truco.

### Detalles que parecen chicos y no lo son

- **Salteo manual:** no corta seco. Busca el próximo downbeat (un par de segundos como mucho),
  filtra la salida y entra el siguiente. Se siente como decisión, no como error.
- **Archivo roto o faltante al tocar:** pasa al siguiente del plan sin que nadie se entere y reporta
  el incidente. **Nunca hay silencio.**
- **Perfil de EQ del local:** configurable una vez.
- **Limitador de techo:** nada clipea, nunca.

### Reporte a la nube

Qué sonó, cuándo, con qué transición, si se desvió del plan y por qué. Más salud: ocupación de
buffers y **cualquier hueco de audio (underrun)**. Un underrun dispara alerta, no una línea de log.

### Hardware

Una PC modesta. Lo pesado es el análisis inicial, que corre de día. En vivo: sumar arrays y aplicar
biquads. Salida por la placa del local, idealmente una interfaz USB decente.

### Modo copiloto

El mismo agente con la salida de audio apagada: muestra el próximo tema, la ruta hacia lo más votado
y el motivo de cada decisión. **Es exactamente la misma pieza de software** — no hay una segunda
base de código para el modo "complementar al DJ".

---

## 11. Validación: de dónde sale el "gusto"

Cuatro niveles. **El DJ humano está en el nivel 3, no en el 1** — un DJ mediocre como fuente de
verdad codificaría su mediocridad, y además el DJ que cambia de género sin corte *no se da cuenta de
que lo hace*, así que tampoco lo marcaría al revisar un plan. Es un oráculo roto.

### Nivel 0 — Invariantes mecánicas (cero gusto humano)

La queja original **no es una opinión de gusto**: es un defecto mecánicamente detectable.

| Falla | Cómo se detecta sin opinar |
|---|---|
| Salto de género sin puente | No existe arista en el grafo |
| Salto de tempo brutal | >6% módulo octava, sin corte declarado |
| Corte seco a mitad de frase | No cae en downbeat ni en `mix_out` |
| Bajón de energía en el pico | Energía < objetivo de fase |
| Machaque del mismo artista | Ventana de cooldown |

Se verifican como **tests de propiedad** sobre *cualquier* plan que el motor genere. Es la red de
seguridad que permite tocar los pesos durante meses sin romper nada. **Este nivel solo ya pone al
sistema por encima del DJ del problema.**

### Nivel 1 — Corpus de sets reales (el gusto destilado en datos)

Los sets buenos ya fueron tocados y son datos públicos.

**Electrónica:** [1001Tracklists](https://www.1001tracklists.com/) — Boiler Room, Essential Mix de
BBC Radio 1, festivales, clubes. Miles de secuencias ordenadas de temas reales tocados ante pistas
reales. Hay librerías Python no oficiales para extraerlos.

500 sets → resolver cada tema a ISRC → analizar → **decenas de miles de transiciones validadas por
el mercado**. De ahí salen, medidos y no inventados:

- la distribución real de saltos de BPM entre temas consecutivos (¿el 6% es correcto? el dato lo dice)
- **el grafo de géneros aprendido**: qué pares aparecen adyacentes y con qué frecuencia — las aristas
  pasan de ser opinión a ser estadística
- la forma real de la curva de energía a lo largo de 3 horas
- qué movimientos de Camelot se usan de verdad y cuáles son teoría de manual

**Problema honesto con lo latino:** 1001Tracklists está fuertemente sesgada a EDM; cumbia, cuarteto
y reggaetón de boliche están mal cubiertos. Tres alternativas, por calidad:

1. **Reconstruir tracklists por huella acústica** sobre mixes latinos publicados (fingerprinting por
   ventanas de 30 s). Es lo que 1001TL hace a mano.
   ⚠️ **Duda abierta:** descargar de Mixcloud/SoundCloud probablemente viola sus términos. Resolver
   antes de hacerlo, no después.
2. **Airplay de radio** — las radios publican qué pasaron y en qué orden. Es programación musical
   profesional, con curva.
3. **La mejor: el histórico de un local que ya funciona.** Un boliche lleno todos los sábados es un
   oráculo infinitamente mejor que un DJ opinando. Un mes de registro = el corpus latino que no
   existe en internet.

### Nivel 2 — La pista misma

En producción todo lo anterior queda subordinado a esto: **skips, votos, permanencia**. Si el motor
programó una transición que el corpus avala y en ese local la gente se fue, **la pista gana**.

### Nivel 3 — El DJ humano

Revisor de casos raros. Uno solo, elegido, y solo donde el dato no alcanza. No entrena: desempata.

### Arranque en frío

El nivel 1 se destila **una vez y viaja con el producto**. El primer cliente recibe el grafo de
géneros y los pesos aprendidos del corpus, y después se adapta con el nivel 2. **Nadie entrena nada
a mano en cada instalación.**

---

## 12. Modo degradado y fallas en vivo

> **El silencio es el único fracaso inaceptable.** Todo lo demás es degradación tolerable.

```
1. Que suene música                    ← nunca se sacrifica
2. Que no rompa el ambiente
3. Que la decisión sea óptima
4. Que la votación esté viva           ← lo primero que se cae
```

Se sacrifica **de abajo hacia arriba, nunca al revés**.

### Modos

**① Normal** — nube + agente, todo vivo.

**② Sin internet** *(el escenario más probable)* — el agente ya tiene en disco el catálogo
analizado, la política, el grafo, los pesos y **el motor completo** (decisión D3). Sigue
planificando y tocando exactamente igual; solo se congela la entrada de votos nuevos, y los últimos
recibidos siguen pesando con su decaimiento normal. Nadie en la pista se entera. La web muestra
*"sin conexión con el local — tus votos se envían cuando vuelva"* y los encola en el celular.

**③ Sin plan válido** — se relajan las restricciones **blandas en orden fijo y declarado**: primero
cooldown de artista, después tolerancia de energía, después tolerancia tonal. **Nunca** se relajan la
lista negra ni el salto de género sin arista. Si aun así no hay ruta: **tanda de emergencia**, una
playlist curada por fase que el local define en el onboarding. Suena bien y es segura; no es
aleatoria: es el plan B que el cliente aprobó.

**④ Cae el proceso de control** — el hilo de audio sigue con el tema actual y el siguiente ya
decodificados en RAM: varios minutos de aire. Watchdog reinicia el control, que retoma desde el
estado persistido en disco. En el mejor caso nadie escucha nada raro.

**⑤ Muere la PC** — software no salva. **El manual de instalación exige una salida de respaldo
física**: un reproductor común (celular, USB) en otra entrada de la consola. Es parte del producto,
no un descuido.

### Observabilidad (se vende, no se esconde)

Heartbeat cada pocos segundos. Si un local deja de reportar en horario de operación, **la alerta va
a nosotros, no al cliente**. Panel de salud por local: underruns, archivos faltantes, planes vacíos,
cortes de red. Argumento comercial: *"nosotros nos enteramos antes que vos"*.

### Al volver la conexión

El agente sincroniza los eventos encolados: nada del histórico se pierde. Los votos encolados en los
celulares entran con su timestamp original y decaimiento aplicado, y **si son muy viejos se
descartan** — aplicar un voto de hace 40 minutos como nuevo es peor que perderlo.

### Fallas blandas (las que más van a pasar)

**Transición que suena mal por análisis errado** → botón *"esta transición estuvo mal"* en el panel
del encargado: marca el par, lo penaliza en ese local y manda el tema a revisión. El feedback más
barato y más valioso del sistema.

**Catálogo insuficiente** → se avisa **en el onboarding, no en la primera noche**:

- **Mínimo operativo:** ~800 temas analizados y aptos
- **Cómodo:** 2.000+
- Desagregado **por fase**: de nada sirven 2.000 temas si 1.900 son de peak time y no hay con qué abrir

> ⚠️ **Corregido en implementación (17-ago-2026).** El total no es el cuello de botella:
> lo es la profundidad **por fase**. Un catálogo de 900 temas dejó al motor sin material
> en el pico. La formulación correcta está en
> [`docs/hallazgos-etapa-1.md`](../../hallazgos-etapa-1.md) (H4), y deja de ser una nota
> al pie para convertirse en una auditoría del onboarding.

---

## 13. Orden de construcción

El riesgo número uno **no es técnico**: es si el motor programa bien un set o programa como un DJ
malo. Todo lo demás es trabajo conocido. Y ese riesgo se mata **en seco, sin escribir una línea de
reproductor**.

| # | Etapa | Qué prueba |
|---|---|---|
| 1 | **Núcleo de decisión aislado** + tests de propiedad (nivel 0) | Que el motor no pueda romper la noche |
| 2 | **Destilación del corpus** (nivel 1) → grafo de géneros y pesos | Que las reglas salgan de datos, no de opinión |
| 3 | **Analizador de biblioteca** | Que el catálogo real se pueda leer, incluida la música difícil |
| 4 | **Generación en seco de 4 horas** sobre un crate real | Que un set completo aguante lectura |
| 5 | **Nube + votación** | Que el atractor y el anti-abuso funcionen |
| 6 | **Agente reproductor y costura** | Que suene |
| 7 | **Modo degradado y observabilidad** | Que aguante un sábado |

Etapas 1-4 son el 80% del riesgo y el 20% del costo. **El modo copiloto sale gratis al terminar la
4**: es el mismo motor con otra salida, y ya es vendible.

---

## 14. Riesgos y dudas abiertas

| # | Tema | Estado |
|---|---|---|
| R1 | Licencia de record pool para uso automatizado del establecimiento (la licencia suele ser personal del DJ) | **Duda abierta — bloqueante comercial.** Verificar con los pools antes de vender |
| R2 | Descarga de mixes de Mixcloud/SoundCloud para destilar corpus latino | **Duda abierta.** Probablemente contra sus términos. Resolver antes de construir |
| R3 | Detección de BPM y tonalidad en cumbia, cuarteto y folclore | **Riesgo conocido, mitigado** por `apta_para_costura` + cola de revisión. No eliminado |
| R4 | Cobertura de corpus latino en 1001Tracklists | **Confirmado flojo.** Requiere las fuentes alternativas de §11 |
| R5 | El DJ como comprador incómodo (el sistema puede leerse como amenaza) | Mitigado por el posicionamiento (§3) y el modo copiloto |
| R6 | Competencia con votación ya instalada (EvolveDJ, PSLY, mixody, PartyVote, Songvote, CrowdDrop) | Todos fuertes en votación, débiles en musicalidad. El diferencial es el planificador de ruta |
| R7 | Sin local piloto, el nivel 2 de validación no arranca | Conseguir un local antes de la etapa 6 |

### Etiquetas de certeza sobre los datos de investigación

- **Confirmado** — Spotify deprecó `audio-features`/`audio-analysis` el 27-nov-2024 (403 permanente,
  sin reemplazo) y restringió `popularity` en febrero 2026.
- **Confirmado** — la API pública de Deezer no requiere key, cubre 100M+ tracks y devuelve ISRC.
- **Confirmado** — AcousticBrainz cerró en 2022; el dump de junio-2022 (7,5M grabaciones) sigue
  descargable.
- **Confirmado** — los record pools (BPM Supreme/Latino, DJcity, DJ Extended, Latinurbano, DJ
  Latino, Unlimited Latin, VRP) entregan MP3 320k legales con ediciones extended.
- **Confirmado** — ±6% es el rango de mezcla cómoda citado consistentemente; 1-2 BPM por transición
  es la técnica de build estándar.
- **Inferido** — que las ediciones extended de record pool hacen la costura sustancialmente más
  fácil que las versiones de streaming (se sigue de que tienen intro/outro; no medido).
- ~~**Supuesto** — el mínimo de ~800 temas.~~ **Refutado en implementación**: la métrica
  estaba mal planteada. Ver `docs/hallazgos-etapa-1.md` (H4).

### Correcciones que trajo la construcción de la etapa 1

El diseño se mantiene, con cinco enmiendas registradas en
[`docs/hallazgos-etapa-1.md`](../../hallazgos-etapa-1.md):

| # | Qué | Impacto |
|---|---|---|
| H1 | Faltaba el término de costo de **curva** | Sin él cada transición es correcta y el set entero deriva |
| H2 | El grafo de géneros puede tener **trampas de tempo** | Afecta cómo hay que auditar el grafo destilado en la etapa 2 |
| H3 | El plan de emergencia rompía las innegociables | Formalizado: sacrifica el nivel 3, nunca el nivel 2 |
| H4 | El mínimo de catálogo se mide **por fase**, no en total | Se convierte en función del onboarding |
| H5 | Dos índices precomputados (grafo y catálogo) hacen viable la replanificación en vivo | ~0,2 s sobre 1200 temas |

---

## 15. Fuera de alcance (YAGNI explícito)

- Beatmatch cuadrado en vivo con corrección continua de fase → se decidió costura, no sincronía dura
- Machine learning para la decisión → primero reglas explicables; ML solo sobre los pesos, y después
- Integración con servicios de streaming (Beatport LINK, Beatsource) → SDK cerrado, se descarta por ahora
- Aplicación nativa para el público → la web por QR es mejor y no tiene fricción de instalación
- Reconocimiento de video / conteo de gente por cámara → interesante para el nivel 2, no en v1
- Efectos de DJ (loops, hot cues, scratch) → no aportan al problema que resuelve el producto

---

## 16. Fuentes de la investigación

**Metadata y catálogo**
- [Spotify Web API Changelog — febrero 2026](https://developer.spotify.com/documentation/web-api/references/changes/february-2026)
- [Spotify Audio Features Is Dead — What to Use Instead in 2026](https://freqblog.com/blog/spotify-audio-features-replacement-2026/)
- [AcousticBrainz Downloads](https://acousticbrainz.org/download) · [GetSongBPM API](https://getsongbpm.com/api) · [TuneBat API](https://tunebat.com/API)

**Teoría de mezcla**
- [Camelot Wheel — Mixed In Key](https://mixedinkey.com/camelot-wheel/)
- [Camelot Wheel Explained: The 3 Mixing Rules](https://vibesdj.io/learn/techniques/camelot-wheel)
- [The DJ's Guide to Harmonic Mixing](https://lowendcandy.com/blog/harmonic-mixing-guide/)
- [DJ Set Energy Flow — Control Your Dance Floor with BPM](https://www.harmonyset.com/guides/dj-set-energy-flow)
- [How to Build Energy in a DJ Set](https://www.setflow.app/blog/dj-set-energy-flow)
- [BPM by Genre: The Complete DJ Tempo Chart](https://www.setflow.app/blog/bpm-by-genre-dj-tempo-chart)

**Herramientas y referencia técnica**
- [Mixxx — Free Open-Source DJ Software](https://mixxx.org/) · [Automix (fork de madmom)](https://github.com/MZehren/Automix) · [Auto-DJ for EDM](https://github.com/ddman1101/Auto-DJ)
- [1001Tracklists](https://www.1001tracklists.com/)

**Audio y licencias**
- [BPM Supreme](https://bpmmusic.io/supreme) · [DJ Extended](https://djextended.net/es/contenido) · [Latinurbano](https://www.latinurbano.com/) · [DJ Latino](https://www.djlatino.com/) · [Unlimited Latin](https://unlimitedlatin.com/)
- [Beatport Streaming](https://stream.beatport.com/) · [Beatport LINK vs Beatsource LINK](https://wearecrossfader.co.uk/blog/beatport-link-vs-beatsource-link/)
- [SADAIC y AADI-CAPIF: qué se paga](https://jbbabogados.com.ar/sadaic-y-aadi-capif-que-impuestos-debo-pagar-por-reproducir-musica-y-o-videos-en-publico/) · [Música en tu local: qué se paga hoy](https://www.derechoenzapatillas.com/2026/musica-en-tu-local-que-se-paga-hoy-a-quien-cuando-y-cuanto/)

**Competencia**
- [EvolveDJ](https://evolvedj.com/) · [PSLY (Mixmag)](https://mixmag.net/read/nightclub-app-crowd-vote-on-the-djs-next-track-news) · [CrowdDrop](https://crowd-drop.com/) · [PartyVote](https://www.partyvote.app/) · [Songvote](https://www.songvote.club/)

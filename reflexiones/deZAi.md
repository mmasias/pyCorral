# Reflexiones sobre pyCorral y miRUP

## Premisa de fondo: mecanismo y procedimiento

pyCorral y miRUP son capas ortogonales que no compiten entre sí.

- **pyCorral es mecanismo puro.** Expone CLIs LLM externos como herramientas MCP invocables por Claude Code. Es deliberadamente agnóstico al procedimiento: no prescribe cuándo delegar, a quién, con qué pausas ni con qué criterios de aceptación. Ese cierre de scope es una decisión de diseño, no una carencia.
- **miRUP es procedimiento concreto.** Formaliza una iteración RUP (derivada del método de Luis Fernández Muñoz) en reglas explícitas de entrada/salida, pausas arquitectónicas y milestones. Es una respuesta responsable al problema que el mercado vende como "vibecoding": delegar generación a un LLM sin criterio de cierre, sin atribución de defectos, sin puertas entre fases. El vibecoding es la forma irresponsable de la delegación agéntica; miRUP es la formalización que la hace auditable.

La combinación es la unidad funcional completa: pyCorral provee el *cómo* de la invocación; miRUP provee el *cuándo* y el *para qué*. La crítica "pyCorral no dice cuándo delegar" no aplica porque no es su trabajo; es trabajo del procedimiento que se monte encima.

---

## pyCorral: capa mecánica

### Lo que está bien

1. **Idea central correcta y mínima.** "Agente como herramienta MCP" resuelve el problema sin inventar framework. Usa el mecanismo nativo de extensión de Claude Code. Es la solución más pequeña posible al silo entre CLIs.

2. **Control plane / data plane bien trazado.** Un solo coordinador con criterio; los agentes ejecutan sin saber que están orquestados. Evita el anti-pattern de CrewAI/AutoGen donde los "agentes" conversan dentro del mismo proceso Python.

3. **Filesystem como bus de datos.** Decisión pragmática: verificación con Glob/Read/Grep, no parseo de texto volátil. Es la filosofía Unix aplicada a agentes.

4. **Código pequeño y auditable.** ~140 líneas por server, los 4 casi idénticos. Cualquiera lo lee en una sentada.

5. **Documentación honesta.** El README reconoce sus propias limitaciones (sin retry, sin observabilidad, jobs volátiles). Eso es madurez de ingeniería, no marketing.

6. **Agnosticismo procedimental como decisión.** No acoplar el mecanismo a un procedimiento (miRUP u otro) permite reutilizarlo en flujos ad hoc, en otros marcos metodológicos, o en experimentación pura. La alternativa - meter políticas de delegación en el MCP server - habría contaminado la capa mecánica con decisiones que no le corresponden.

### Lo que está flojo

Todas las críticas siguientes son sobre la **implementación del mecanismo**, no sobre la ausencia de procedimiento (que es cierre de scope consciente).

1. **DRY ausente.** Los 4 servers son ~90% idénticos. Cualquier fix en el patrón sync/async/done debe replicarse en 4 sitios (`gemini_mcp.py`, `opencode_mcp.py`, `ollama_mcp.py`, `kiro_mcp.py`). Falta una clase base `BaseAgentMCP` con el esqueleto y un hook `_invoke(prompt, workdir)`. Sería ~80 líneas de base + ~30 por agente. Es el refactor con mayor ROI del repo.

2. **`_jobs` efímero es la limitación más seria.** Reinicias Claude Code y pierdes todos los `job_id` activos. Persistir en `/tmp/corral_<agent>_jobs.json` es trivial y resolvería el 80% del problema. Bajo cualquier procedimiento que requiera trazabilidad (miRUP la requiere: cada ramillete, pausa y milestone debe poder reconstruirse), esta volatilidad es más dolorosa que en uso ad hoc.

3. **Async sin timeout ni cancelación.** Si un job async cuelga, `_done` devuelve "pendiente" eternamente y no hay API para matarlo. El sync tiene timeout (120s/300s); el async no tiene nada.

4. **`output.md` fijo colisiona en paralelo.** El README lo prohíbe ("nunca enviar a dos agentes a escribir el mismo fichero en paralelo"), pero eso cercena patrones útiles (un agente hace `frontend.md`, otro `backend.md` en el mismo workdir). Permitir `output_path` como parámetro lo resuelve sin coste. Esto es relevante para cualquier procedimiento que prescriba fan-out + convergencia: bajo miRUP, A2/D2/I3 son fan-out por caso de uso, y forzar un único `output.md` por workdir obliga a un workdir distinto por becario, lo cual es una restricción arbitraria del mecanismo que se filtra al procedimiento.

5. **La descripción de las tools miente para Gemini/Kiro.** Dice "la respuesta se escribe en output.md dentro de workdir" (`gemini_mcp.py:41`), pero el comportamiento real del CLI decide qué escribe: puede no escribir nada, o escribir otro nombre. Solo OpenCode (via wrapper) y Ollama garantizan `output.md`. La tool description debería decir "el agente puede escribir ficheros en workdir".

6. **Detección del binario en import time.** `GEMINI_BIN = _find_gemini()` al inicio del módulo (`gemini_mcp.py:28`). Si el binario no está, el server no arranca y `claude mcp list` da "failed to connect" sin contexto. Lazy o error explícito en handshake MCP sería más usable.

7. **`opencode-wrapper.sh:10` borra el prompt.** `rm -f "$1"` antes de saber si la invocación va a funcionar. Side-effect frágil: si opencode falla al arranque, el input se pierde. Mejor stdin o no borrar hasta el final.

8. **`setup.sh` no es idempotente.** `claude mcp add` falla ruidosamente si el server ya está registrado. Segunda ejecución del setup se rompe. Falta un guard `claude mcp list | grep -q` antes de añadir.

9. **Sin tests.** Defendible para infra personal, pero cualquier refactor del patrón base (punto 1) debería ir con smoke tests. Mínimo: lanzar cada server contra un mock del CLI y verificar el trío de tools.

### Veredicto de pyCorral

POC sólido de la tesis "agente como herramienta", correctamente documentado, honesto con sus límites, y deliberadamente agnóstico al procedimiento. Las dos mejoras con mayor retorno son: (a) abstraer el patrón repetido para dejar de mantener 4 copias, y (b) persistir `_jobs` a disco. El resto son pulidos. El riesgo de mantener el estado actual es que cualquier mejora futura se bifurca cuatro veces, lo que erosionará la ventaja de "código pequeño y auditable" que hoy es su principal activo.

---

## miRUP: capa metodológica

### Lo sólido

1. **Formaliza lo tácito sin traicionarlo.** Convertir el "instinto del director" en reglas con criterios de entrada/salida y contraindicaciones explícitas es lo que diferencia un método transmisible de uno que muere con su autor. La estructura ¿qué produces / desde dónde derivas / hacia quién traza / cuándo cierras? en cada disciplina es la unidad mínima y correcta.

2. **El patrón de delegabilidad es la pieza de mayor valor.** La distinción esqueleto/integración (no delegable) vs relleno (delegable) es generalizable más allá de RUP. Cualquier disciplina con esqueleto + fan-out + fan-in cabe en él. Es un esquema reutilizable.

3. **`decisiones-descartadas.md` es madurez de ingeniería aplicada a metodología.** Documentar no solo qué se eligió sino qué se consideró y se descartó (con razón) evita la rediscusión eterna. Es el equivalente metodológico de un archivo de ADRs bien llevado.

4. **El principio de no persistir derivados.** Región y riesgo se recalculan por replay, no cacheados. Evita dos fuentes de verdad y el coste de mantener cachés obsoletas. Coste nulo (5 valores por ramillete). Es la decisión correcta.

5. **La divergencia humano/CORRAL explícita en tres puntos.** No fingir que el método es idéntico en ambos modos; acotar dónde divergen y por qué (monotonía, ramillete-iteración uno-a-varios, ejecución de la pausa). Es honestidad operacional, no marketing.

6. **La tesis contra el vibecoding es correcta.** El vibecoding delega sin pausas, sin atribución y sin criterio de cierre; el resultado es software que el operador no puede justificar. miRUP ataca exactamente los tres puntos: puertas discretas entre fases (pausa arquitectónica), atribución de defectos al origen aguas arriba (regla de validación entre disciplinas), y cierre validado por milestone ternario. Es una respuesta arquitectónica al problema, no un parche.

### Lo cuestionable

1. **Es un documento, no un sistema.** No hay registry, no hay tooling que verifique "esta pausa está en región X, este ramillete acumula riesgo Y". Hoy el protocolo vive en la cabeza del lector (humano o LLM) y se aplica por disciplina. Para uso recurrente falta una encarnación verificable: un registry CORRAL-RUP con slots `{fase}/{iteracion}/{disciplina}/{artefacto}` y un comprobador que lea los frontmatters de pausa y valide la transición de región. Sin eso, la sofisticación de las reglas (herencia monótona de riesgo, residencia_min, anti-colapso) se aplica de oído y se erosiona.

2. **La "banda como área difusa" es elegante en abstracto, pero toda pausa concreta se resuelve discreta.** En cada pausa, el orquestador está en una región operativa concreta (retiene / propone / delega). Decir "es un área" describe el espacio de diseño, no la ejecución. Útil como advertencia contra falsa precisión, pero operationally cada pausa es un punto. La distinción conceptual no se traduce en procedimiento verificable sin un criterio de clasificación adicional.

3. **La sofisticación de la regla de transición puede ser desproporcionada al uso real.** Tres regiones, herencia monótona de riesgo, residencia_min = {1,2,3}, anti-colapso con suelo absoluto en uno, replay path-dependent sobre milestones limpios, distinción entre madurez de proyecto y riesgo de ramillete. Es un modelo formal rico. La pregunta es: ¿esta complejidad se paga en mejor delegación, o un esquema más simple (contador lineal de milestones limpios + umbral por disciplina) captura el 90% del beneficio? Conviene aplicarlo a 3-4 ramilletes reales y ver si las distinciones finas discriminan.

4. **Gestión de configuración y gestión de proyecto quedan fuera sin tratamiento.** El comentario final del `protocolo-iteracion.md` lo admite. Son las dos disciplinas de soporte de RUP y son las que más fricción tienen con el modo agéntico: quién commitea, cómo se versionan los artefactos transversales consolidados, qué hace el orquestador cuando dos ramilletes tocan el mismo diagrama de clases de diseño. Es el punto abierto más relevante.

5. **`GEMINI.md` vacío.** Si la intención es que Gemini CLI (como becario) cargue contexto de proyecto al ser invocado desde un workdir miRUP, este fichero no puede estar vacío. Como mínimo necesita un extracto del patrón de delegabilidad y el formato de los artefactos que se espera que produzca. Hoy un becario entra al proyecto sin brújula.

### Veredicto de miRUP

Spec metodológico ambicioso, internamente coherente, con una tesis clara contra el vibecoding. Su debilidad estructural no es de contenido sino de encarnación: hasta que no tenga un registry verificable y 3-4 ramilletes reales que lo ejerciten de punta a punta, sigue siendo una propuesta elegante sin evidencia de que las distinciones finas (banda vs línea, tres regiones, residencia_min) discriminan mejor que un esquema más simple. La prioridad debe ser aplicarlo, no seguir refinándolo.

---

## Contraste y complementariedad

| Dimensión | pyCorral | miRUP |
|---|---|---|
| Tipo de capa | Mecanismo | Procedimiento |
| Scope | Agnóstico al método | Específico de RUP bajo orquestación |
| Cómo se valida | Smoke tests del trío de tools | Aplicación a ramilletes reales |
| Riesgo principal | Erosión por mantenimiento de 4 copias | Erosión por aplicación de oído sin tooling |
| Evolución natural | Refactor DRY + persistencia de `_jobs` | Registry verificable + protocolo de GC/GP |

pyCorral es la condición necesaria pero no suficiente. Sin un procedimiento encima, el orquestador de pyCorral delega por intuición, que es exactamente la forma diluida del vibecoding. miRUP es uno de los procedimientos posibles (el más elaborado que conozco en este repositorio); pueden montarse otros más simples o más específicos sin tocar pyCorral.

Las fricciones entre ambas capas son las que cabe resolver en el corto plazo:

- pyCorral fuerza `output.md` único; miRUP prescribe fan-out + convergencia con tantos artefactos como casos de uso.
- pyCorral pierde `job_id` al reiniciar; miRUP necesita trazabilidad de cada delegación para reconstruir el historial de milestones.
- pyCorral no distingue espacio de producto de espacio de gobierno; miRUP los separa físicamente en el filesystem.

Estas fricciones no son fallos de diseño de ninguna de las dos partes: son la interfaz entre dos capas ortogonales que aún no han convergido. Resolverlas es el siguiente trabajo de fondo.

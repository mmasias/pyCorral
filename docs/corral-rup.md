# CORRAL-RUP

## ¿Por qué?

Los proyectos con ciclo de vida, trazabilidad hacia atrás y mapeo contra especificación externa producen artefactos que dependen unos de otros a través del tiempo. Un orquestador que despacha tareas en paralelo sin memoria de proceso no puede responder: ¿qué produjo cada agente en cada iteración? ¿Qué artefactos han sido validados? ¿El diseño responde realmente a los requisitos, o solo lo declara?

CORRAL-RUP extiende CORRAL con estructura de proceso basada en RUP para que esas preguntas tengan respuesta verificable.

## ¿Qué?

CORRAL-RUP organiza el trabajo en dos capas ortogonales:

- **RUP** gobierna el esqueleto temporal: fases (Inception, Elaboración, Construcción, Transición), iteraciones dentro de cada fase, y milestones de cierre de fase con revisión humana.
- **Topología** governa cada nodo hoja: cómo se ejecutan los agentes dentro de un par iteración-disciplina concreto (`none` / fan-out paralelo, `chain`, `converge`, `cycle`). La topología no se hereda de la fase ni se deriva de RUP; se declara por tarea. Subespecificar este nivel produce slots hoja sin topología definida.

Las dos capas coexisten. Ninguna sustituye a la otra.

### Principio transversal

Ningún estado derivable se persiste. Esto aplica a `estado_actual` del milestone (proyectado del historial de evaluaciones), al estado de promoción de un artefacto (derivado de su presencia en la lista `promovidos` de algún milestone aprobado), y a `pendiente` como estado del milestone (proyección, nunca valor almacenado). Persistir un derivado crea dos fuentes de verdad y es el origen de toda deriva.

### Modelo de tres espacios

Dentro del repo del proyecto conviven tres espacios con propósitos distintos:

| Espacio | Ruta | Propósito |
|---|---|---|
| Proceso | `corral-rup/{fase}/{iteracion}/{disciplina}/{artefacto}` | Seguimiento, traza por iteración, autoría, topología. El registry vive aquí. |
| Entregables validados | `rup/0N-disciplina/{artefactos}` | Producto RUP organizado por disciplina numerada. |
| Producto funcional | `frontend/`, `backend/`, `src/` | Rutas convencionales, ajenas al proceso. |

La asimetría de nombres entre `corral-rup/` y `rup/` es intencional: lo que debe sobrevivir a la desaparición de CORRAL no lleva su nombre (el entregable en `rup/`); lo que es proceso gestionado por CORRAL-RUP sí lo lleva (`corral-rup/`).

## ¿Para qué?

- Hacer verificable si el diseño responde a los requisitos, no solo si lo declara.
- Registrar el proceso, no solo el resultado: cuántas iteraciones requirió un milestone, qué artefactos se rechazaron, qué se promovió y cuándo.
- Mantener al humano como auditor de coherencia semántica en los puntos de decisión (milestones), sin requerir que lea todos los artefactos producidos.
- Permitir que los LLMs produzcan en paralelo dentro de cada fase-disciplina, con el orquestador preparando la evidencia y el humano aprobando la transición de fase.

## ¿Cómo?

### Contrato 1: Esquema de slots

El registry y los slots viven dentro del repo del proyecto, así que el repo es el proyecto. El prefijo `corral-rup/` distingue el espacio de proceso del resto del repo.

```
corral-rup/{fase}/{iteracion}/{disciplina}/{artefacto}
```

| Nivel | Valores canónicos | Sentinela |
|---|---|---|
| `fase` | `inception` · `elaboracion` · `construccion` · `transicion` | `_` |
| `iteracion` | `i1`, `i2`, ... o identificador nominal | `_` |
| `disciplina` | `requisitos` · `analisis-diseno` · `implementacion` · `pruebas` · `gestion-config` · `gestion-proyecto` | `_` |
| `artefacto` | nombre del fichero sin extensión | nunca |

**Regla de sentinela:** `fase → iteracion → disciplina` forman cadena de contención. Sentinela en un nivel fuerza sentinela en todos los subordinados de esa cadena. El caso degenerado (tarea puntual sin estructura RUP) produce la ruta `corral-rup/_/_/_/{artefacto}`: los tres niveles intermedios son sentinela, y la distinción temporal entre ejecuciones vive en el nombre del artefacto. Una tarea degenerada no genera entrada en el registry porque no hay proceso que documentar; solo existe la ruta del slot como espacio de trabajo.

### Contrato 2: Objeto milestone

El milestone es un objeto de gobierno en el registry, no un artefacto en el árbol de slots. Cuelga de la fase que cierra (`fases.{fase}.milestone`), no de ninguna iteración.

```yaml
milestone:
  id_rup: lco | lca | ioc | pr
  responsable: humano       # invariante — nunca el orquestador
  evaluaciones:             # lista ordenada, nunca vacía
    - tipo: creacion        # exactamente una, siempre la primera, escrita por el sistema
      fecha: ISO 8601
    - tipo: evaluacion      # escritas por el humano, todas las demás
      fecha: ISO 8601
      veredicto: aprobado | rechazado-con-observaciones
      observaciones: obligatorio si veredicto = rechazado-con-observaciones
      promovidos:           # solo presente y no vacía si veredicto = aprobado
        - identificador-artefacto
```

`estado_actual` es proyección de lectura, nunca se persiste:
- `pendiente` → la lista solo tiene entrada de creación, o el último veredicto es `rechazado-con-observaciones`
- `aprobado` → el último veredicto es `aprobado`

La puerta tiene dos posiciones: abierta (`aprobado`) o cerrada (todo lo demás). `rechazado-con-observaciones` existe únicamente como valor de `veredicto` en una entrada del historial, nunca como valor de `estado_actual`.

**Invariante de escritura:** el sistema escribe exactamente una entrada (creación). El humano escribe todos los veredictos. `pendiente` nunca lo escribe nadie.

**Regla de bloqueo:** el orquestador no ejecuta transición de fase hasta `estado_actual == aprobado`.

**Regla de rechazo:** un rechazo es una entrada de evaluación humana con `veredicto: rechazado-con-observaciones`. No genera ninguna entrada adicional. `estado_actual` proyecta `pendiente` hasta la siguiente evaluación humana.

**Regla de no-retroceso:** un rechazo añade iteración de corrección a la fase actual. No retrocede de fase.

### Promoción

`rup/0N-disciplina/` admite dos vías de entrada, no una:

**Vía 1 - Promoción desde iteración:** la aprobación de un milestone copia (no mueve) cada artefacto de su lista `promovidos`, en su última versión, al contenedor `rup/0N-disciplina/` correspondiente a la disciplina del artefacto. Es el caso general para artefactos producidos durante el proceso.

**Vía 2 - Entrada directa como prerequisito:** un artefacto que existe antes de que el proceso empiece entra directamente en `rup/` sin haber pasado por una iteración ni un milestone. No se exige que todo lo que esté en `rup/` haya sido promovido. Un prerequisito puede entrar directo.

El caso paradigmático es el **modelo del dominio**: es condición de entrada al proceso, no producto de una iteración, porque los becarios producen casos de uso a partir de él (la heurística CRUD parte del modelo del dominio). Si está a medias, los candidatos salen a medias. Por eso debe existir, lo más completo posible, antes de la primera iteración. También entran por esta vía otras entradas externas que preexisten al proceso: una especificación recibida, un documento normativo de referencia.

La mecánica posterior es uniforme: una vez en `rup/`, si una iteración ajusta ese artefacto (por ejemplo, el modelo del dominio cuando aparece una entidad que faltaba), el ajuste se trabaja en su slot de iteración (`corral-rup/{fase}/{iteracion}/requisitos/modelo-dominio`) y se promueve por su milestone, actualizando la versión en `rup/`. La primera versión entra por la vía 2; todos sus ajustes posteriores entran por la vía 1. A partir del primer ajuste se comporta como cualquier artefacto que evoluciona a través del tiempo.

Reglas comunes a ambas vías:
- El milestone decide *cuándo* se promueve (vía 1); la disciplina del artefacto decide *adónde* (su contenedor numerado), tanto en vía 1 como en vía 2.
- La copia preserva la traza: el original en `corral-rup/` (vía 1) o en su ubicación de origen (vía 2) no se elimina.
- Un artefacto no promovido puede cruzar milestones sin promoverse y continúa como trabajo en las fases e iteraciones siguientes.
- El estado de promoción se *deriva* de la presencia del artefacto en `rup/` (por cualquiera de las dos vías). Nunca se persiste en el artefacto.

### Esquema del registry

Un registry por proyecto, viviendo en `corral-rup/registry.md` dentro del repo. Markdown con frontmatter YAML.

- **Frontmatter YAML** — lo que el orquestador parsea: árbol de fases → iteraciones → disciplinas → artefactos, topología declarada por par iteración-disciplina, e historial de evaluaciones del milestone con su lista `promovidos`. No persistir derivados: `estado_actual`, `pendiente` y el estado de promoción de un artefacto nunca son campos del frontmatter.
- **Cuerpo Markdown** — para el auditor humano: narrativa de proceso que el frontmatter no captura.
- La topología sí se persiste: es declarada por tarea, no derivada.
- La topología es propiedad del par iteración-disciplina. La misma disciplina puede tener topología distinta en iteraciones distintas.

#### Ejemplo trabajado: pySigHor

```markdown
---
proyecto: pySigHor
fases:
  elaboracion:
    milestone:
      id_rup: lca
      responsable: manuel
      evaluaciones:
        - tipo: creacion
          fecha: "2026-05-10"
        - tipo: evaluacion
          fecha: "2026-05-15"
          veredicto: rechazado-con-observaciones
          observaciones: "CU-07 y CU-08 sin precondiciones. Especificación insuficiente para iniciar diseño."
        - tipo: evaluacion
          fecha: "2026-05-20"
          veredicto: aprobado
          promovidos:
            - cu-01-iniciar-sesion
            - cu-02-gestionar-aulas
            - cu-03-gestionar-edificios
    iteraciones:
      i1:
        disciplinas:
          requisitos:
            topologia: none
            artefactos:
              - cu-01-iniciar-sesion
              - cu-02-gestionar-aulas
              - cu-03-gestionar-edificios
              - cu-07-generar-horario
              - cu-08-consultar-horario
          analisis-diseno:
            topologia: chain
            artefactos:
              - arquitectura-mvc
              - diagrama-clases-dominio
---

# pySigHor — Registry CORRAL-RUP

## Elaboración / i1

### Requisitos (none — fan-out)
Cinco agentes en paralelo, uno por caso de uso. Sin dependencias entre sí.

### Análisis-diseño (chain)
`arquitectura-mvc` primero; `diagrama-clases-dominio` depende de su salida.

## Milestone LCA
Primera evaluación rechazada: CU-07 y CU-08 producidos pero sin precondiciones, insuficientes para iniciar diseño. Se abre iteración de corrección en Elaboración.
Segunda evaluación aprobada. Promovidos a `rup/01-requisitos/`: CU-01, CU-02, CU-03. CU-07 y CU-08 no promovidos: continúan como trabajo pendiente en la fase.
```

CU-07 y CU-08 ilustran el caso de artefacto producido pero no promovido: aparecen en la lista de artefactos de `requisitos/i1` (existen como trabajo), no aparecen en `promovidos` del milestone LCA aprobado (no han superado la validación semántica), y continúan como trabajo en iteraciones siguientes de Elaboración o en Construcción.

#### Caso degenerado

Para una tarea puntual sin estructura RUP (por ejemplo, un fan-out de generación de contenido), el slot es `corral-rup/_/_/_/{artefacto}`. No hay entrada de registry: no existe proceso que documentar. Solo existe la ruta de slot como espacio de trabajo efímero.

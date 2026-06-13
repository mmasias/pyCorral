# Checklist de calidad para skills de CORRAL-RUP

Un skill es un contrato de activación y ejecución para el LLM, no documentación. La documentación detallada vive en `docs/corral-rup.md` y en el registry. El skill solo contiene lo que el LLM necesita para activarse y ejecutar correctamente.

## Idioma

Los skills de CORRAL-RUP se escriben en español: triggers, hard rules, execution steps y output contract incluidos. Si un skill pertenece a un proyecto con convención de idioma distinta, sigue esa convención.

## Frontmatter

- [ ] Campos completos: `name`, `description`, `license`, `metadata.author`, `metadata.version`
- [ ] `description` es una sola línea física, entre comillas, YAML-safe
- [ ] `description` empieza con las palabras de trigger: `"Trigger: ... . {qué hace el skill}."`
- [ ] `description` tiene 160 chars o menos (máximo absoluto: 250)
- [ ] Sin sección `Keywords`

## Estructura (en este orden, ninguna omitida sin razón explícita)

- [ ] **Activation Contract** — cuándo y solo cuándo se carga este skill
- [ ] **Hard Rules** — constraints que el LLM no puede violar; cada una es observable o testable
- [ ] **Decision Gates** — tabla o bullets para bifurcaciones reales (no cobertura exhaustiva)
- [ ] **Execution Steps** — pasos operacionales ordenados, imperativos ("Leer X", "Verificar Y", "Escribir Z")
- [ ] **Output Contract** — qué devuelve el LLM al terminar (ver abajo)
- [ ] **References** — solo si hay ficheros locales de apoyo; sin URLs externas como referencia primaria

## Output Contract — doble dimensión

Los skills de CORRAL-RUP con efecto sobre el registry o la promoción de artefactos deben distinguir explícitamente:

- [ ] **Respuesta al usuario**: qué comunica el skill al terminar (confirmación, resumen, estado)
- [ ] **Efecto en sistema de ficheros**: qué escribe y dónde (entrada en registry, copia a `rup/0N-disciplina/`, slot en `corral-rup/`)

Un skill sin efecto en sistema de ficheros solo necesita la primera dimensión. Un skill de milestone o promoción necesita ambas.

## Presupuesto

- [ ] Cuerpo entre 180 y 450 tokens (objetivo); máximo 700 (recomendado); 1000 (absoluto)
- [ ] Todo lo que supere el presupuesto va a `assets/` o `references/`, no inline

## Estilo de escritura

- [ ] Instrucciones imperativas en runtime, no prosa explicativa
- [ ] Activation trigger y hard rules antes que cualquier ejemplo
- [ ] Ejemplos mínimos ejecutables
- [ ] Decision gates como tablas compactas, no prosa con ramas

## Anti-patrones — ninguno de estos debe aparecer

- [ ] Sin historia, motivación o contexto tutorial
- [ ] Sin duplicar documentación que vive en `docs/corral-rup.md` o en el registry
- [ ] Sin consejos genéricos que el LLM no puede ejecutar directamente
- [ ] Sin reglas críticas enterradas debajo de ejemplos
- [ ] Sin URLs externas como referencia primaria
- [ ] **Sin persistir estados derivables**: `estado_actual`, estado de promoción y `pendiente` se proyectan en runtime; ninguna regla del skill los escribe. Es el principio transversal del diseño aplicado al nivel de skill.

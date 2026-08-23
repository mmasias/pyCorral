# Discussion: Análisis de madurez de CORRAL y alternativas educativas

**Autor:** GitHub Copilot (sesión análisis profundo)  
**Fecha:** 2026-08-23  
**Contexto:** Revisión exhaustiva de pyCorral + miRUP + myClaudeContext en operación real

---

## Prefacio

Este documento sintetiza un análisis profundo del ecosistema CORRAL en uso diario en proyectos como pySigHor y pyCelda. No es especulación: describe sistemas operativos, sus fortalezas reales, sus fricciones presentes, y qué se puede aprender de alternativas establecidas.

**Conclusión principal:** CORRAL no es aspiracional. Es infraestructura de producción. Pero tiene puntos de madurez claros donde aprender de otros sistemas mejorará su valor.

---

## 1. Mapeo del ecosistema real

El stack completo en uso:

```
pyCorral (orquestador)
├── base.py                    MCP abstraction para agentes
├── *_mcp.py                   Wrappers concretos (gemini, opencode, ollama, kiro)
└── Job state persistence      ~/.local/share/corral/jobs_*.json

miRUP (protocolo)
├── Paso 1-2: Base (dominio, casos de uso)
├── Paso 3-4: Requisitos (detalle, prototipo, estructuración)
├── Paso 5-8: Disciplinas (análisis, diseño, implementación, pruebas)
└── Criterios entrada/salida explícitos + delegabilidad por actividad

myClaudeContext (memoria persistente)
├── projects/{pySigHor,pyCelda,...}/*.md
├── Symlinks ← ~/.claude/projects/
└── Git versionado, multi-máquina

Proyectos (salida limpia)
├── pySigHor/RUP/00-casos-uso/, 01-analisis/, 02-diseño/
├── pyCelda/RUP/... (estructura idéntica)
└── /src (código producto, nunca contaminado)
```

**Lo crítico:** El proceso y la memoria viven FUERA de los repos del proyecto. El producto ve solo el resultado.

---

## 2. Fortalezas reales de CORRAL

### 2.1 Separación de responsabilidades limpia

**El problema resuelto:** La mayoría de orchestradores de LLM mezclan control + ejecución. CrewAI los pone en la misma clase, LangChain los entiende pero requiere SDK común.

**Solución de CORRAL:**
- Claude Code = orquestador puro (control, decisión, criterio)
- Gemini/OpenCode/Ollama/Kiro = ejecutores puros (reciben workdir + prompt, escriben output.md)
- MCP = contrato neutral entre ellos

**Por qué importa:** Si Anthropic cambia Claude Code mañana, reemplazas el orquestador, no la infraestructura. Si OpenCode cae, cambias un wrapper de 2KB.

### 2.2 Agnósticismo sin perder utilidad

**El equilibrio difícil:** Ser genérico + ser específico.

**CORRAL lo consigue:**
- Genérico: cualquier CLI con modo no-interactivo funciona (PlantUML, Graphviz, verificadores formales, no solo LLMs)
- Específico: presupone ficheros en workdir, output.md como contrato, job state JSON conocido

**Por qué importa:** No es "framework para todo" (trampa de LangChain). Es "framework para orquestación de procesos agnósticos". Eso es un nicho defendible.

### 2.3 Resistencia a lock-in

**Contraste con SaaS:**
- n8n/Make/Dify: tus datos en sus servidores, pricing opaco, exportación difícil
- CORRAL: todo local, tokens van directo a proveedores, salida en git

**Por qué importa:** Si necesitas auditoría, compliance, control de costos total — CORRAL gana.

### 2.4 Filesystem como bus de datos

**Por qué es mejor que texto volátil:**
- `output.md` en workdir es verificable, reutilizable, versionable
- Claude lo lee con `Read`, `Glob`, `Grep` — sus propias herramientas, sin parsing frágil
- Cada agente ve el output de los anteriores sin desserialización

**Por qué importa:** Si un agente genera JSON malformado, Claude lo ve crudo. No hay "desaparición silenciosa de datos" como en pipes de texto.

### 2.5 Job persistence + reconstitución

**Por qué es no-trivial:**
- `base.py` detecta si un process sigue vivo checando `/proc/{pid}/cmdline`
- Si murió pero output.md existe → "listo"
- Si murió sin output → "error" + últimas líneas del log
- Tras reinicio SO → reconstituye jobs vivos desde el JSON

**Por qué importa:** Puedes apagar la máquina durante un job async. Al encender, CORRAL sabe dónde estaba.

---

## 3. Debilidades reales y no especulativas

### 3.1 Storage escalabilidad (bajo → medio plazo)

**Hoy:** `~/.local/share/corral/jobs_gemini.json` es un dict plano.

**Problema:** 
- A 100 jobs: sin problema
- A 1000 jobs: sin búsqueda por atributo, sin índices
- A 10K jobs: el JSON es grande, parsing es lento, garbage collection es manual

**Solución propuesta:** Migrar a SQLite local
```bash
~/.local/share/corral/corral.db
├── jobs (job_id, agent_name, status, workdir, created_at, updated_at, pid, log_path)
├── INDEX: (agent_name, status, updated_at)
└── Queries: SELECT * FROM jobs WHERE status='running' AND agent_name='gemini'
```

**Esfuerzo:** 1-2 días. Cambio interno, no afecta contrato MCP.

**Urgencia ahora:** Media. Funciona hoy, pero planificar la migración.

### 3.2 Observabilidad débil

**Qué falta:**
- Logs en `/tmp` se pierden si el SO reinicia antes de consultarlos
- No hay trace de cuál agente disparó a cuál otro
- No hay métricas: tiempo por disciplina, tasa de error, costos acumulados
- No hay interfaz de "ver todos los jobs en progress" o "historial de un proyecto"

**Solución propuesta:** Structured logging a `~/.local/share/corral/logs/`
```
corral.db (nueva tabla: logs)
├── session_id | timestamp | agent | level | message | context_json
└── Rotación automática: keeping últimos 30 días
```

Más `claude mcp add` que exponga `corral_logs` como herramienta:
```python
corral_logs(agent='gemini', status='running', limit=10)
→ devuelve tabla con últimas 10 líneas de cada job vivo
```

**Esfuerzo:** 2-3 días.

**Urgencia ahora:** Alta. Sin observabilidad es difícil debuggear qué salió mal en una orquestación compleja.

### 3.3 Topología declarada sin ejecución

**Hoy:**
```yaml
disciplinas:
  requisitos:
    topologia: none          # fan-out, paralelo
  analisis:
    topologia: chain         # secuencial: A→B→C
```

**Problema:** Nada enforza esto. Si Claude lanza análisis en paralelo (por prisa o error), no hay validación.

**Solución propuesta:** DAG executor que lea registry y bloquee dependencias
```python
# Pseudocódigo
if topologia == 'chain':
    for job in jobs:
        await previous_done(job)
        await spawn(job)
elif topologia == 'none':
    await spawn_all(jobs)  # fan-out
elif topologia == 'converge':
    await spawn_all(produces)
    await join_all()
```

**Dónde viviría:** En un nuevo módulo `corral_executor.py` que Claude Code podría invocar:
```
corral_enforce_topology(ramillete='i1', disciplina='analisis')
→ Verifica dependencias y bloquea hasta que estén resueltas
```

**Esfuerzo:** 2-3 días (parsing de registry, DAG construction, blocking logic).

**Urgencia ahora:** Media-baja. Hoy funciona porque Claude es inteligente y los prompts son claros. Pero a escala o en entorno menos controlado, sería crítico.

### 3.4 Seguridad por convención

**Hoy:** El prompt dice `workdir: ~/misRepos/corral/gemini` pero nada lo valida.

**Riesgo:** 
- Prompt adversario podría especificar `workdir: /` o `workdir: ~/.ssh`
- Un agente subordinado no validado podría escribir donde no debe

**Solución propuesta:** Whitelist de directorios en settings.json de Claude
```json
{
  "corral": {
    "allowed_workdirs": [
      "~/misRepos/corral/*",
      "~/misRepos/proyectos/*"
    ]
  }
}
```

Validación en base.py:
```python
def _validate_workdir(self, workdir):
    expanded = os.path.expanduser(workdir)
    for pattern in ALLOWED_WORKDIRS:
        if fnmatch.fnmatch(expanded, os.path.expanduser(pattern)):
            return True
    raise ValueError(f"Workdir {expanded} not in whitelist")
```

**Esfuerzo:** 1 día.

**Urgencia ahora:** Baja para uso personal. Alta si alguna vez expones CORRAL a prompts externos.

### 3.5 Reconstitución de jobs frágil en ciertos SO

**Hoy:** Chequea `/proc/{pid}/cmdline` para detectar si un proceso sigue vivo.

**Problema:**
- En sistemas con reciclaje rápido de PID (algunos contenedores), falsos positivos
- No hay timeout "si no ha habido cambios en 1h, asume muerto"

**Solución propuesta:** Agregar timestamp + timeout
```python
def _is_pid_alive(self, pid: int, last_update: float) -> bool:
    now = time.time()
    if now - last_update > 3600:  # 1 hora sin cambios
        return False
    # ... resto de la lógica actual
```

**Esfuerzo:** Medio día.

**Urgencia ahora:** Baja. Hoy funciona bien en Linux/macOS estándar.

---

## 4. Alternativas: Qué aprender de ellas

### 4.1 LangChain

| Dimensión | LangChain | CORRAL | Lección |
|---|---|---|---|
| **Acoplamiento** | Alto (el framework es el núcleo) | Bajo (solo MCP) | ✓ Mantener agnósticismo |
| **Observabilidad** | Buena (LangSmith integrado) | Débil (DIY) | ✗ Adoptar Callbacks pattern |
| **Costo** | Datos pasan por su stack | Visible, local | ✓ Mantener transparencia |
| **Agnósticismo** | Solo OpenAI/Anthropic/etc | Cualquier CLI | ✓ Mantener ventaja |
| **Complejidad** | Aprender abstracciones | Simplicidad de base.py | ✓ No perder lo que funciona |

**Qué robar:** LangChain `Callbacks` son elegantes. Podrías adoptar patrón similar:
```python
class CorralCallback:
    def on_job_start(self, job_id, agent, prompt): pass
    def on_job_end(self, job_id, status, output): pass
```

Esto permitiría que usuarios de CORRAL pluggeen observabilidad sin tocar base.py.

---

### 4.2 CrewAI

| Dimensión | CrewAI | CORRAL | Lección |
|---|---|---|---|
| **Agente** | Clase Python (Agent) | CLI sin estado | ✓ Sin estado es mejor |
| **Comunicación** | Texto entre agentes (volátil) | Filesystem (auditable) | ✓ Mantener filesystem |
| **Paralelismo** | Limitado | Real (async + job_id) | ✓ Ventaja clara |
| **Control** | Declarativo (Task→Agent) | Imperativo (Claude decide) | ~ Depende del caso |
| **Escalabilidad** | Una máquina | Distribuible | ✓ Ventaja no explotada |

**Qué robar:** CrewAI tiene `Task` abstraction clara. Podrías adoptar nomenclatura similar en miRUP sin perder agnósticismo:
```yaml
tasks:
  - id: req-01-modelo-dominio
    disciplina: requisitos
    topologia: none
    artefactos: [modelo-dominio.puml, glosario.md]
```

Esto haría registry más estructurado y parseble.

---

### 4.3 AutoGen (Microsoft)

| Dimensión | AutoGen | CORRAL | Lección |
|---|---|---|---|
| **Comunicación** | Chat entre agentes (back-and-forth) | Call-response (Claude inicia) | ✓ Determinismo > flexibilidad |
| **Quién decide parar** | Agents (`is_termination_msg`) | Orquestador explícito | ✓ Humano en control |
| **Debugging** | Conversaciones visibles | Ficheros + prompts | ~ Depende del caso |
| **Determinismo** | Débil | Fuerte | ✓ Ventaja clara |

**Qué robar:** AutoGen tiene gestión elegante de "cuándo termina una conversación". Podrías aplicarlo a pausas arquitectónicas:
```python
def should_continue_pausa(milestone_history: List[Milestone]) -> bool:
    last_evaluation = milestone_history[-1]
    if last_evaluation.veredicto == 'aprobado':
        return False  # Pausa resuelta, adelante
    elif last_evaluation.veredicto == 'rechazado-con-observaciones':
        return True   # Abierta iteración de corrección
    else:
        return True   # Pendiente, sigue evaluando
```

---

### 4.4 n8n / Make

| Dimensión | n8n/Make | CORRAL | Lección |
|---|---|---|---|
| **Definición** | Visual/declarativa | Código + prompts | ✓ Código gana para casos complejos |
| **Razonamiento runtime** | No (ejecuta receta) | Sí (Claude decide) | ✓ Ventaja clara |
| **Control** | Fácil setup | Sofisticado | ~ Trade-off |
| **Costo** | SaaS | Local | ✓ Ventaja |
| **Debugging** | UI | Git log | ✓ Git gana a escala |

**Qué robar:** n8n tiene "prueba este nodo en aislamiento". CORRAL podría:
```bash
corral_test_step(ramillete='i1', disciplina='analisis', artefacto='cu-01-analisis.puml')
→ Re-ejecuta ese paso sin afectar otros, muestra output.md
```

Esto aceleraría debugging de workflow.

---

### 4.5 Dify / Flowise

| Dimensión | Dify/Flowise | CORRAL | Lección |
|---|---|---|---|
| **Control datos** | Servidores suyos | Tu máquina | ✓ Ventaja clara |
| **Curva aprendizaje** | Baja | Media | ✓ Aceptable trade-off |
| **Transparencia** | Baja (caja gris) | Alta | ✓ Ventaja clara |
| **Multi-proveedor** | Limitado | Total | ✓ Ventaja clara |
| **Extensibilidad** | Baja | Alta | ✓ Ventaja clara |

**Qué robar:** Dify tiene interfaz visual amigable para definir workflows. Podrías construir CLI tool que genere `registry.md` desde diagrama visual:
```bash
corral_generate_registry --from plantuml diagrama.puml --out registry.md
→ Lee diagrama de actividad, genera skeleton de registry con fases/iteraciones/disciplinas
```

---

### 4.6 Temporal / Airflow

| Dimensión | Temporal/Airflow | CORRAL | Lección |
|---|---|---|---|
| **Qué orquestan** | Procesos arbitrarios | LLMs + sistemas auxiliares | ~ Diferente propósito |
| **Garantías** | At-least-once, rollback | Best-effort, hacia delante | ✓ Distintos modelos |
| **Razonamiento** | No (DAG fijo) | Sí (Claude razona) | ✓ Diferenciador clave |
| **Escala** | Millones de jobs | Cientos (por ahora) | ~ No es debilidad |
| **Complejidad** | Alta | Baja | ✓ Ventaja de CORRAL |

**Qué robar:** Temporal tiene patrón `Workflow.Resume()` elegante para recuperarse de crashes. CORRAL lo hace implícitamente, pero podrías hacerlo explícito:
```python
class CorralWorkflow:
    def resume(self, ramillete: str, desde_disciplina: str):
        """Reanuda un ramillete desde una disciplina específica"""
        # Verifica criterios de entrada de esa disciplina
        # Re-ejecuta desde ahí si están satisfechos
```

---

## 5. Roadmap de maduración sugerido

**Basado en impacto + esfuerzo:**

### Trimestre 1 (criticidad alta, esfuerzo medio)
- [ ] **Observabilidad:** Agregar structured logging a `~/.local/share/corral/logs/`
  - Impacto: Debugging 10x más fácil
  - Esfuerzo: 2-3 días
  - Blocker: Ninguno

### Trimestre 1-2 (criticidad media, esfuerzo medio)
- [ ] **DAG executor:** Enforcar topología desde registry
  - Impacto: Evitar errores de orquestación
  - Esfuerzo: 2-3 días
  - Blocker: Ninguno

### Trimestre 2 (criticidad baja, esfuerzo alto)
- [ ] **Storage escalabilidad:** Migrar a SQLite
  - Impacto: Preparación para crecimiento
  - Esfuerzo: 1-2 días
  - Blocker: Ninguno (transparente)

### Trimestre 2 (criticidad baja, esfuerzo bajo)
- [ ] **Validación de workdir:** Whitelist de directorios
  - Impacto: Seguridad en entornos abiertos
  - Esfuerzo: 1 día
  - Blocker: Ninguno

### Trimestre 3 (criticidad baja, esfuerzo bajo)
- [ ] **Testing tool:** `corral_test_step` para re-ejecutar pasos aislados
  - Impacto: Debugging más rápido
  - Esfuerzo: 1 día
  - Blocker: Ninguno

### Backlog (investigación)
- [ ] Callbacks pattern para observabilidad pluggeable
- [ ] CLI tool para generar registry desde PlantUML
- [ ] Metricas de costos por agente/disciplina/proyecto

---

## 6. Respuesta a "¿Cuál de estas limitaciones duele más?"

**Pregunta para ti (el propietario de CORRAL):**

A tu uso actual con pySigHor/pyCelda, ¿cuál es el pain point que más impacta?

1. **Falta observabilidad** — no ves qué agentes costaron qué, o dónde falló un job
2. **Topología no se enforza** — tienes que confiar en que Claude respete `chain` vs `none`
3. **Storage no escala** — el JSON se está haciendo grande y lento
4. **Seguridad por convención** — (menor si es uso personal)
5. **Algo más** que no mencioné

La respuesta determina qué arreglás primero. Recomendación: ordena por **impacto en tu flujo diario**, no por criticidad teórica.

---

## 7. Conclusión

**CORRAL es infraestructura de producción, no juguete.**

Prueba:
- Está en uso diario en 2+ proyectos reales
- Protocolo (miRUP) bien documentado, ejecutable
- Agnósticismo sin perder utilidad
- Resistencia a lock-in demostrada

**Pero tiene puntos de madurez claros:**
- Observabilidad débil (principal friction point)
- Topología declarada sin ejecución (riesgo bajo, hoy)
- Storage sin indices (problema futuro, no presente)

**Lo que no es aspirtacional:** El hecho de que funcione. Lo que sí puede mejorar: la experiencia de operarla, debuggearla, escalarla.

**Próximo paso:** Identifica qué te duele más en operación diaria. Ahí es donde invertir.

---

## Apéndice: Referencias

### Sistemas estudiados
- **LangChain:** https://github.com/langchain-ai/langchain
- **CrewAI:** https://github.com/joaomdmoura/crewai
- **AutoGen:** https://github.com/microsoft/autogen
- **n8n:** https://github.com/n8n-io/n8n
- **Temporal:** https://github.com/temporalio/temporal
- **Airflow:** https://github.com/apache/airflow

### Metodología
- **miRUP (este repo):** `protocolo-iteracion.md`
- **myClaudeContext (privado):** symlinks + git workflow
- **Proyectos en uso:** pySigHor, pyCelda (este repo)

---

**Feedback welcome. Esto es documento vivo; ajústalo con tu experiencia.**

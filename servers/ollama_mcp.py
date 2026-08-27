import json
import os
import threading
import urllib.request

from base import BaseAgentMCP, run


OLLAMA_URL = os.environ.get("CORRAL_OLLAMA_URL", "http://127.0.0.1:11434")

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Escribe contenido en un archivo dentro del directorio de trabajo",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Nombre del archivo (relativo al workdir)"},
                    "content": {"type": "string", "description": "Contenido a escribir"},
                },
                "required": ["filename", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Lee el contenido de un archivo del directorio de trabajo",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Nombre del archivo (relativo al workdir)"},
                },
                "required": ["filename"],
            },
        },
    },
]


def _resolve_workdir_path(filename: str, workdir: str) -> str:
    # El modelo a veces pasa una ruta absoluta o con ~ en vez del nombre
    # relativo que pide la tool (ej. "~/misRepos/corral/ollama/x.md" en vez
    # de "x.md"). os.path.join no trata "~..." como absoluto, así que sin
    # esto se creaba un directorio literal "~" anidado dentro del workdir.
    expanded = os.path.expanduser(filename)
    if os.path.isabs(expanded):
        return expanded
    return os.path.join(workdir, expanded)


def _execute_tool(name: str, args: dict, workdir: str) -> str:
    if name == "write_file":
        path = _resolve_workdir_path(args["filename"], workdir)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w") as f:
            f.write(args["content"])
        return f"ok: '{args['filename']}' escrito."
    if name == "read_file":
        path = _resolve_workdir_path(args["filename"], workdir)
        try:
            with open(path) as f:
                return f.read()
        except FileNotFoundError:
            return f"error: '{args['filename']}' no existe."
    return f"error: herramienta '{name}' desconocida."


def _call_ollama(prompt: str, model: str, workdir: str, timeout: int = 600) -> str:
    messages = [{"role": "user", "content": prompt}]

    for _ in range(10):
        payload = json.dumps({
            "model": model,
            "messages": messages,
            "tools": _TOOLS,
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())

        message = data["message"]
        messages.append(message)

        tool_calls = message.get("tool_calls")
        if not tool_calls:
            return message.get("content", "")

        for tc in tool_calls:
            fn = tc["function"]
            args = fn.get("arguments", {})
            if isinstance(args, str):
                args = json.loads(args)
            result = _execute_tool(fn["name"], args, workdir)
            messages.append({"role": "tool", "content": result})

    return "error: límite de iteraciones alcanzado."


class OllamaAgentMCP(BaseAgentMCP):
    """Becario CORRAL respaldado por un modelo de Ollama.

    Clase genérica: cada becario por modelo (qwen, gemma, ollama) es una
    instancia con su agent_name, workdir y variable de entorno de modelo.
    El parámetro `model` de las tools permite sobreescribir el modelo por
    llamada en cualquiera de ellas.
    """

    def __init__(self, agent_name: str, server_name: str, default_workdir: str,
                 model_env_var: str, fallback_model: str):
        super().__init__(agent_name, server_name, default_workdir)
        self.model_env_var = model_env_var
        self.default_model = os.environ.get(model_env_var, fallback_model)

    def _descriptions(self):
        n = self.agent_name
        return (
            "Ejecuta una inferencia en Ollama de forma sincrona. La respuesta se escribe en output.md dentro de workdir.",
            "Ejecuta una inferencia en Ollama en segundo plano y devuelve un job_id. La respuesta se escribe en output.md "
            "(ultimo resultado, puede ser sobrescrito por otra invocacion concurrente al mismo workdir) y tambien en "
            "output-<job_id>.md (exclusivo de este job, usalo si puede haber invocaciones concurrentes).",
            f"Consulta el estado de un job lanzado con {n}_run_async.",
        )

    def _extra_schema_props(self) -> dict:
        return {
            "model": {
                "type": "string",
                "description": f"Modelo Ollama (default: {self.default_model}, configurable via {self.model_env_var})",
            }
        }

    def _extra_args(self, arguments: dict) -> dict:
        return {"model": arguments.get("model", self.default_model)}

    def _invoke_sync(self, prompt: str, workdir: str, **kwargs) -> str:
        model = kwargs.get("model", self.default_model)
        try:
            response = _call_ollama(prompt, model, workdir)
            if response.strip():
                with open(os.path.join(workdir, "output.md"), "w") as f:
                    f.write(response)
            return "ok"
        except Exception as e:
            return f"error: {e}"

    def _invoke_async(self, job_id: str, prompt: str, workdir: str, **kwargs) -> None:
        model = kwargs.get("model", self.default_model)
        log_path = f"/tmp/{self.agent_name}_job_{job_id}.log"

        def worker():
            try:
                response = _call_ollama(prompt, model, workdir, timeout=None)
                if response.strip():
                    # output-<job_id>.md es exclusivo de este job: dos invocaciones
                    # concurrentes al mismo workdir (misma sesion con 2 jobs, o dos
                    # sesiones CORRAL distintas) no pueden pisarse aqui. output.md
                    # fijo se mantiene ademas por compatibilidad con el mecanismo
                    # de reconstruccion de base.py tras un reinicio del servidor,
                    # pero puede ser sobrescrito por otra invocacion concurrente.
                    with open(os.path.join(workdir, f"output-{job_id}.md"), "w") as f:
                        f.write(response)
                    with open(os.path.join(workdir, "output.md"), "w") as f:
                        f.write(response)
                # A diferencia de gemini/opencode/kiro (que vuelcan su stdout al
                # log siempre), Ollama antes solo escribia log_path en el except.
                # Eso dejaba el panel de corral-tail sin nada que seguir en el
                # camino feliz: se escribe tambien aqui para que haya actividad
                # visible tanto en exito como en error.
                with open(log_path, "w") as f:
                    f.write(response if response.strip() else "(respuesta vacia)")
                self._jobs[job_id]["result"] = "listo"
                self._update_job_state(job_id, "done")
            except Exception as e:
                with open(log_path, "w") as f:
                    f.write(str(e))
                self._jobs[job_id]["result"] = f"error: {e}"
                self._update_job_state(job_id, "error")

        t = threading.Thread(target=worker, daemon=True)
        # pid: None porque Ollama usa threading, no subprocess
        self._jobs[job_id] = {"result": None, "log_path": log_path, "workdir": workdir, "thread": t, "pid": None}
        t.start()

    def _poll(self, job_id: str) -> str:
        entry = self._jobs.get(job_id)
        if entry is None:
            state = self._job_state.get(job_id)
            if state:
                return self._status_to_response(state["status"])
            return f"error: job {job_id} no encontrado"
        result = self._poll_reconstructed(job_id, entry)
        if result is not None:
            return result
        if entry["thread"].is_alive():
            return "pendiente"
        result = entry["result"] or "error: resultado desconocido"
        self._update_job_state(job_id, "done" if result == "listo" else "error")
        del self._jobs[job_id]
        return result


class OllamaMCP(OllamaAgentMCP):
    def __init__(self):
        super().__init__(
            "ollama",
            "ollama-mcp",
            os.path.expanduser("~/misRepos/corral/ollama"),
            "CORRAL_OLLAMA_MODEL",
            "qwen2.5:7b",
        )


if __name__ == "__main__":
    run(OllamaMCP())

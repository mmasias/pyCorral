import json
import os
import threading
import urllib.request

from base import BaseAgentMCP, run


OLLAMA_URL = os.environ.get("CORRAL_OLLAMA_URL", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("CORRAL_OLLAMA_MODEL", "qwen2.5:7b")

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


def _execute_tool(name: str, args: dict, workdir: str) -> str:
    if name == "write_file":
        path = os.path.join(workdir, args["filename"])
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w") as f:
            f.write(args["content"])
        return f"ok: '{args['filename']}' escrito."
    if name == "read_file":
        path = os.path.join(workdir, args["filename"])
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


class OllamaMCP(BaseAgentMCP):
    def __init__(self):
        super().__init__("ollama", "ollama-mcp", os.path.expanduser("~/misRepos/corral/ollama"))

    def _descriptions(self):
        n = self.agent_name
        return (
            f"Ejecuta una inferencia en Ollama de forma sincrona. La respuesta se escribe en output.md dentro de workdir.",
            f"Ejecuta una inferencia en Ollama en segundo plano y devuelve un job_id. La respuesta se escribe en output.md dentro de workdir.",
            f"Consulta el estado de un job lanzado con {n}_run_async.",
        )

    def _extra_schema_props(self) -> dict:
        return {
            "model": {
                "type": "string",
                "description": f"Modelo Ollama (default: {DEFAULT_MODEL}, configurable via CORRAL_OLLAMA_MODEL)",
            }
        }

    def _extra_args(self, arguments: dict) -> dict:
        return {"model": arguments.get("model", DEFAULT_MODEL)}

    def _invoke_sync(self, prompt: str, workdir: str, **kwargs) -> str:
        model = kwargs.get("model", DEFAULT_MODEL)
        try:
            response = _call_ollama(prompt, model, workdir)
            with open(os.path.join(workdir, "output.md"), "w") as f:
                f.write(response)
            return "ok"
        except Exception as e:
            return f"error: {e}"

    def _invoke_async(self, job_id: str, prompt: str, workdir: str, **kwargs) -> None:
        model = kwargs.get("model", DEFAULT_MODEL)
        log_path = f"/tmp/ollama_job_{job_id}.log"

        def worker():
            try:
                response = _call_ollama(prompt, model, workdir, timeout=None)
                with open(os.path.join(workdir, "output.md"), "w") as f:
                    f.write(response)
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
                return state["status"]
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


if __name__ == "__main__":
    run(OllamaMCP())

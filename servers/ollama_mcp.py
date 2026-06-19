import json
import os
import threading
import urllib.request

from base import BaseAgentMCP, run


OLLAMA_URL = os.environ.get("CORRAL_OLLAMA_URL", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("CORRAL_OLLAMA_MODEL", "qwen2.5:7b")


def _call_ollama(prompt: str, model: str, timeout: int = 600) -> str:
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return data["response"]


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
            response = _call_ollama(prompt, model)
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
                response = _call_ollama(prompt, model, timeout=None)
                with open(os.path.join(workdir, "output.md"), "w") as f:
                    f.write(response)
                self._jobs[job_id]["result"] = "listo"
            except Exception as e:
                with open(log_path, "w") as f:
                    f.write(str(e))
                self._jobs[job_id]["result"] = f"error: {e}"

        t = threading.Thread(target=worker, daemon=True)
        self._jobs[job_id] = {"result": None, "log_path": log_path, "thread": t}
        t.start()

    def _poll(self, job_id: str) -> str:
        entry = self._jobs.get(job_id)
        if entry is None:
            return f"error: job {job_id} no encontrado"
        if entry["thread"].is_alive():
            return "pendiente"
        result = entry["result"] or "error: resultado desconocido"
        del self._jobs[job_id]
        return result


if __name__ == "__main__":
    run(OllamaMCP())

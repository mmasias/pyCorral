import asyncio
import json
import os
import threading
import urllib.error
import urllib.request
import uuid

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


OLLAMA_URL = os.environ.get("CORRAL_OLLAMA_URL", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("CORRAL_OLLAMA_MODEL", "qwen2.5:14b")
DEFAULT_WORKDIR = os.path.expanduser("~/misRepos/corral/ollama")

_jobs: dict[str, dict] = {}

app = Server("ollama-mcp")


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


@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="ollama_run",
            description="Ejecuta una inferencia en Ollama de forma sincrona. La respuesta se escribe en output.md dentro de workdir.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "workdir": {
                        "type": "string",
                        "description": "Directorio de trabajo (default: ~/misRepos/corral/ollama)",
                    },
                    "model": {
                        "type": "string",
                        "description": f"Modelo Ollama (default: {DEFAULT_MODEL}, configurable via CORRAL_OLLAMA_MODEL)",
                    },
                },
                "required": ["prompt"],
            },
        ),
        Tool(
            name="ollama_run_async",
            description="Ejecuta una inferencia en Ollama en segundo plano y devuelve un job_id. La respuesta se escribe en output.md dentro de workdir.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "workdir": {
                        "type": "string",
                        "description": "Directorio de trabajo (default: ~/misRepos/corral/ollama)",
                    },
                    "model": {
                        "type": "string",
                        "description": f"Modelo Ollama (default: {DEFAULT_MODEL}, configurable via CORRAL_OLLAMA_MODEL)",
                    },
                },
                "required": ["prompt"],
            },
        ),
        Tool(
            name="ollama_done",
            description="Consulta el estado de un job lanzado con ollama_run_async.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                },
                "required": ["job_id"],
            },
        ),
    ]


def _async_worker(job_id: str, prompt: str, model: str, workdir: str, log_path: str):
    try:
        response = _call_ollama(prompt, model, timeout=None)
        with open(os.path.join(workdir, "output.md"), "w") as f:
            f.write(response)
        _jobs[job_id]["result"] = "listo"
    except Exception as e:
        with open(log_path, "w") as f:
            f.write(str(e))
        _jobs[job_id]["result"] = f"error: {e}"


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "ollama_run":
        workdir = arguments.get("workdir", DEFAULT_WORKDIR)
        model = arguments.get("model", DEFAULT_MODEL)
        os.makedirs(workdir, exist_ok=True)
        try:
            response = _call_ollama(arguments["prompt"], model)
            with open(os.path.join(workdir, "output.md"), "w") as f:
                f.write(response)
            return [TextContent(type="text", text="ok")]
        except Exception as e:
            return [TextContent(type="text", text=f"error: {e}")]

    if name == "ollama_run_async":
        job_id = uuid.uuid4().hex[:8]
        workdir = arguments.get("workdir", DEFAULT_WORKDIR)
        model = arguments.get("model", DEFAULT_MODEL)
        os.makedirs(workdir, exist_ok=True)
        log_path = f"/tmp/ollama_job_{job_id}.log"
        t = threading.Thread(
            target=_async_worker,
            args=(job_id, arguments["prompt"], model, workdir, log_path),
            daemon=True,
        )
        _jobs[job_id] = {"result": None, "log_path": log_path, "thread": t}
        t.start()
        return [TextContent(type="text", text=job_id)]

    if name == "ollama_done":
        job_id = arguments["job_id"]
        entry = _jobs.get(job_id)
        if entry is None:
            return [TextContent(type="text", text=f"error: job {job_id} no encontrado")]
        if entry["thread"].is_alive():
            return [TextContent(type="text", text="pendiente")]
        result = entry["result"] or "error: resultado desconocido"
        del _jobs[job_id]
        return [TextContent(type="text", text=result)]

    raise ValueError(f"Herramienta desconocida: {name}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

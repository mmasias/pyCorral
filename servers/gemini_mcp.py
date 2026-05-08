import asyncio
import glob
import os
import shutil
import subprocess
import uuid

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


def _find_gemini() -> str:
    gemini_bin = shutil.which("gemini")
    if gemini_bin:
        return gemini_bin
    candidates = sorted(
        glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/gemini")),
        reverse=True,
    )
    if candidates:
        return candidates[0]
    raise RuntimeError(
        "No se encontro el binario 'gemini'. Instala Gemini CLI o verifica PATH."
    )


GEMINI_BIN = _find_gemini()
DEFAULT_WORKDIR = os.path.expanduser("~/misRepos/corral/gemini")

_jobs: dict[str, tuple] = {}

app = Server("gemini-mcp")


@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="gemini_run",
            description="Ejecuta Gemini CLI de forma sincrona. La respuesta se escribe en output.md dentro de workdir.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "workdir": {"type": "string", "description": "Directorio de trabajo (default: ~/misRepos/corral/gemini)"},
                },
                "required": ["prompt"],
            },
        ),
        Tool(
            name="gemini_run_async",
            description="Ejecuta Gemini CLI en segundo plano y devuelve un job_id. La respuesta se escribe en output.md dentro de workdir.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "workdir": {"type": "string", "description": "Directorio de trabajo (default: ~/misRepos/corral/gemini)"},
                },
                "required": ["prompt"],
            },
        ),
        Tool(
            name="gemini_done",
            description="Consulta el estado de un job lanzado con gemini_run_async.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                },
                "required": ["job_id"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "gemini_run":
        workdir = arguments.get("workdir", DEFAULT_WORKDIR)
        os.makedirs(workdir, exist_ok=True)
        proc = subprocess.run(
            [GEMINI_BIN, "-y", "-p", arguments["prompt"]],
            cwd=workdir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=120,
        )
        if proc.returncode == 0:
            text = "ok"
        else:
            text = f"error (rc={proc.returncode}): {proc.stderr.decode(errors='replace')}"
        return [TextContent(type="text", text=text)]

    if name == "gemini_run_async":
        job_id = str(uuid.uuid4())[:8]
        workdir = arguments.get("workdir", DEFAULT_WORKDIR)
        os.makedirs(workdir, exist_ok=True)
        log_path = f"/tmp/gemini_job_{job_id}.log"
        log_file = open(log_path, "w")
        proc = subprocess.Popen(
            [GEMINI_BIN, "-y", "-p", arguments["prompt"]],
            cwd=workdir,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=log_file,
        )
        _jobs[job_id] = (proc, log_path)
        return [TextContent(type="text", text=job_id)]

    if name == "gemini_done":
        job_id = arguments["job_id"]
        entry = _jobs.get(job_id)
        if entry is None:
            return [TextContent(type="text", text=f"error: job {job_id} no encontrado")]
        proc, log_path = entry
        ret = proc.poll()
        if ret is None:
            return [TextContent(type="text", text="pendiente")]
        del _jobs[job_id]
        if ret == 0:
            return [TextContent(type="text", text="listo")]
        try:
            log = open(log_path).read()[-2000:]
        except Exception:
            log = "(sin log)"
        return [TextContent(type="text", text=f"error: rc={ret}\n{log}")]

    raise ValueError(f"Herramienta desconocida: {name}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

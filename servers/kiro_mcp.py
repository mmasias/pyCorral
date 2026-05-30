import asyncio
import os
import shutil
import subprocess
import uuid

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


def _find_kiro() -> str:
    kiro_bin = shutil.which("kiro-cli-chat")
    if kiro_bin:
        return kiro_bin
    candidate = os.path.expanduser("~/.local/bin/kiro-cli-chat")
    if os.path.isfile(candidate):
        return candidate
    raise RuntimeError(
        "No se encontro el binario 'kiro-cli-chat'. Instala Kiro CLI o verifica PATH."
    )


KIRO_BIN = _find_kiro()
DEFAULT_WORKDIR = os.path.expanduser("~/misRepos/corral/kiro")

_jobs: dict[str, tuple] = {}

app = Server("kiro-mcp")


@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="kiro_run",
            description="Ejecuta Kiro CLI de forma sincrona. Los ficheros generados se escriben en workdir.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "workdir": {"type": "string", "description": "Directorio de trabajo (default: ~/misRepos/corral/kiro)"},
                },
                "required": ["prompt"],
            },
        ),
        Tool(
            name="kiro_run_async",
            description="Ejecuta Kiro CLI en segundo plano y devuelve un job_id. Los ficheros generados se escriben en workdir.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "workdir": {"type": "string", "description": "Directorio de trabajo (default: ~/misRepos/corral/kiro)"},
                },
                "required": ["prompt"],
            },
        ),
        Tool(
            name="kiro_done",
            description="Consulta el estado de un job lanzado con kiro_run_async.",
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
    if name == "kiro_run":
        workdir = arguments.get("workdir", DEFAULT_WORKDIR)
        os.makedirs(workdir, exist_ok=True)
        proc = subprocess.run(
            [KIRO_BIN, "chat", "--no-interactive", "--trust-all-tools", arguments["prompt"]],
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

    if name == "kiro_run_async":
        job_id = str(uuid.uuid4())[:8]
        workdir = arguments.get("workdir", DEFAULT_WORKDIR)
        os.makedirs(workdir, exist_ok=True)
        log_path = f"/tmp/kiro_job_{job_id}.log"
        log_file = open(log_path, "w")
        proc = subprocess.Popen(
            [KIRO_BIN, "chat", "--no-interactive", "--trust-all-tools", arguments["prompt"]],
            cwd=workdir,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=log_file,
        )
        _jobs[job_id] = (proc, log_path)
        return [TextContent(type="text", text=job_id)]

    if name == "kiro_done":
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

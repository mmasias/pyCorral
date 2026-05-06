import asyncio
import glob
import os
import shutil
import subprocess
import uuid

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


def _find_opencode() -> str:
    opencode_bin = shutil.which("opencode")
    if opencode_bin:
        return opencode_bin
    candidates = sorted(
        glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/opencode")),
        reverse=True,
    )
    if candidates:
        return candidates[0]
    raise RuntimeError(
        "No se encontro el binario 'opencode'. Instala OpenCode o verifica PATH."
    )


OPENCODE_BIN = _find_opencode()
WRAPPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "opencode-wrapper.sh")
DEFAULT_WORKDIR = os.path.expanduser("~/misRepos/corral/opencode")
OUTPUT_SUFFIX = "\n\nEscribe tu respuesta en: output.md"


def make_env() -> dict:
    node_bin = os.path.dirname(OPENCODE_BIN)
    current_path = os.environ.get("PATH", "")
    return {
        **os.environ,
        "PATH": f"{node_bin}:{current_path}",
        "HOME": os.path.expanduser("~"),
    }


_jobs: dict[str, subprocess.Popen] = {}

app = Server("opencode-mcp")


@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="opencode_run",
            description="Ejecuta OpenCode de forma sincrona via wrapper. La respuesta se escribe en output.md dentro de workdir.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "workdir": {"type": "string", "description": "Directorio de trabajo (default: ~/misRepos/corral/opencode)"},
                },
                "required": ["prompt"],
            },
        ),
        Tool(
            name="opencode_run_async",
            description="Ejecuta OpenCode en segundo plano via wrapper y devuelve un job_id. La respuesta se escribe en output.md dentro de workdir.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "workdir": {"type": "string", "description": "Directorio de trabajo (default: ~/misRepos/corral/opencode)"},
                },
                "required": ["prompt"],
            },
        ),
        Tool(
            name="opencode_done",
            description="Consulta el estado de un job lanzado con opencode_run_async.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                },
                "required": ["job_id"],
            },
        ),
    ]


def _write_prompt_file(prefix: str, prompt: str) -> str:
    path = f"/tmp/opencode_prompt_{prefix}.txt"
    with open(path, "w") as f:
        f.write(prompt)
    return path


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "opencode_run":
        workdir = arguments.get("workdir", DEFAULT_WORKDIR)
        os.makedirs(workdir, exist_ok=True)
        prompt_file = _write_prompt_file(str(os.getpid()), arguments["prompt"] + OUTPUT_SUFFIX)
        proc = subprocess.run(
            [WRAPPER, prompt_file],
            env=make_env(),
            cwd=workdir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=300,
        )
        if proc.returncode == 0:
            text = "ok"
        else:
            text = f"error (rc={proc.returncode}): {proc.stderr.decode(errors='replace')}"
        return [TextContent(type="text", text=text)]

    if name == "opencode_run_async":
        job_id = uuid.uuid4().hex[:12]
        workdir = arguments.get("workdir", DEFAULT_WORKDIR)
        os.makedirs(workdir, exist_ok=True)
        prompt_file = _write_prompt_file(job_id, arguments["prompt"] + OUTPUT_SUFFIX)
        proc = subprocess.Popen(
            [WRAPPER, prompt_file],
            env=make_env(),
            cwd=workdir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _jobs[job_id] = proc
        return [TextContent(type="text", text=job_id)]

    if name == "opencode_done":
        job_id = arguments["job_id"]
        proc = _jobs.get(job_id)
        if proc is None:
            return [TextContent(type="text", text=f"error: job {job_id} no encontrado")]
        ret = proc.poll()
        if ret is None:
            return [TextContent(type="text", text="pendiente")]
        del _jobs[job_id]
        if ret == 0:
            return [TextContent(type="text", text="listo")]
        return [TextContent(type="text", text=f"error: rc={ret}")]

    raise ValueError(f"Herramienta desconocida: {name}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

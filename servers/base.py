import asyncio
import os
import uuid
from abc import ABC, abstractmethod

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool


class BaseAgentMCP(ABC):
    def __init__(self, agent_name: str, server_name: str, default_workdir: str):
        self.agent_name = agent_name
        self.default_workdir = default_workdir
        self._jobs: dict = {}
        self.app = Server(server_name)
        self.app.list_tools()(self._list_tools)
        self.app.call_tool()(self._call_tool)

    def _descriptions(self) -> tuple:
        n = self.agent_name
        return (
            f"Ejecuta {n} de forma sincrona. La respuesta se escribe en output.md dentro de workdir.",
            f"Ejecuta {n} en segundo plano y devuelve un job_id. La respuesta se escribe en output.md dentro de workdir.",
            f"Consulta el estado de un job lanzado con {n}_run_async.",
        )

    def _extra_schema_props(self) -> dict:
        return {}

    def _extra_args(self, arguments: dict) -> dict:
        return {}

    async def _list_tools(self):
        n = self.agent_name
        wd = self.default_workdir.replace(os.path.expanduser("~"), "~")
        sync_desc, async_desc, done_desc = self._descriptions()
        base_props = {
            "prompt": {"type": "string"},
            "workdir": {"type": "string", "description": f"Directorio de trabajo (default: {wd})"},
            **self._extra_schema_props(),
        }
        return [
            Tool(
                name=f"{n}_run",
                description=sync_desc,
                inputSchema={"type": "object", "properties": base_props, "required": ["prompt"]},
            ),
            Tool(
                name=f"{n}_run_async",
                description=async_desc,
                inputSchema={"type": "object", "properties": base_props, "required": ["prompt"]},
            ),
            Tool(
                name=f"{n}_done",
                description=done_desc,
                inputSchema={
                    "type": "object",
                    "properties": {"job_id": {"type": "string"}},
                    "required": ["job_id"],
                },
            ),
        ]

    async def _call_tool(self, name: str, arguments: dict):
        n = self.agent_name
        if name == f"{n}_run":
            workdir = arguments.get("workdir", self.default_workdir)
            os.makedirs(workdir, exist_ok=True)
            text = self._invoke_sync(arguments["prompt"], workdir, **self._extra_args(arguments))
            return [TextContent(type="text", text=text)]

        if name == f"{n}_run_async":
            job_id = uuid.uuid4().hex[:8]
            workdir = arguments.get("workdir", self.default_workdir)
            os.makedirs(workdir, exist_ok=True)
            self._invoke_async(job_id, arguments["prompt"], workdir, **self._extra_args(arguments))
            return [TextContent(type="text", text=job_id)]

        if name == f"{n}_done":
            return [TextContent(type="text", text=self._poll(arguments["job_id"]))]

        raise ValueError(f"Herramienta desconocida: {name}")

    def _poll_popen(self, job_id: str) -> str:
        """Implementación estándar de _poll para agentes basados en subprocess.Popen con tuple (proc, log_path)."""
        entry = self._jobs.get(job_id)
        if entry is None:
            return f"error: job {job_id} no encontrado"
        proc, log_path = entry
        ret = proc.poll()
        if ret is None:
            return "pendiente"
        del self._jobs[job_id]
        if ret == 0:
            return "listo"
        try:
            log = open(log_path).read()[-2000:]
        except Exception:
            log = "(sin log)"
        return f"error: rc={ret}\n{log}"

    @abstractmethod
    def _invoke_sync(self, prompt: str, workdir: str, **kwargs) -> str:
        ...

    @abstractmethod
    def _invoke_async(self, job_id: str, prompt: str, workdir: str, **kwargs) -> None:
        ...

    @abstractmethod
    def _poll(self, job_id: str) -> str:
        ...

    async def main(self):
        async with stdio_server() as (read_stream, write_stream):
            await self.app.run(read_stream, write_stream, self.app.create_initialization_options())


def run(agent: BaseAgentMCP):
    asyncio.run(agent.main())

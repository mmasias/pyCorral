import asyncio
import json
import os
import uuid
from abc import ABC, abstractmethod

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

CORRAL_DATA_DIR = os.path.expanduser("~/.local/share/corral")


class BaseAgentMCP(ABC):
    def __init__(self, agent_name: str, server_name: str, default_workdir: str):
        self.agent_name = agent_name
        self.default_workdir = default_workdir
        self._jobs: dict = {}
        self._job_state: dict = {}  # siempre serializable: {job_id: {status, workdir, log_path, pid}}
        self.app = Server(server_name)
        self.app.list_tools()(self._list_tools)
        self.app.call_tool()(self._call_tool)
        os.makedirs(CORRAL_DATA_DIR, exist_ok=True)
        self._load_jobs()

    # --- Persistencia ---

    def _jobs_path(self) -> str:
        return os.path.join(CORRAL_DATA_DIR, f"jobs_{self.agent_name}.json")

    def _persist_jobs(self) -> None:
        try:
            with open(self._jobs_path(), "w") as f:
                json.dump(self._job_state, f, indent=2)
        except Exception:
            pass

    def _is_pid_alive(self, pid: int) -> bool:
        # Si hay otro proceso del mismo agente vivo con distinto job_id, puede dar
        # falso positivo. Para el caso de uso de miRUP (conservador: preferir
        # "pendiente" a "error") esto es tolerable.
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmdline = f.read().decode(errors="replace")
            return self.agent_name in cmdline
        except Exception:
            return False

    def _load_jobs(self) -> None:
        path = self._jobs_path()
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception:
            return

        surviving = {}
        for job_id, meta in data.items():
            if meta.get("status") in ("done", "error"):
                continue  # limpiar resueltos al arrancar

            workdir = meta.get("workdir", "")
            log_path = meta.get("log_path")
            pid = meta.get("pid")

            if pid and self._is_pid_alive(pid):
                # proceso sigue vivo: reconstruir como pendiente en memoria
                self._jobs[job_id] = {
                    "__reconstructed": True,
                    "pid": pid,
                    "log_path": log_path,
                    "workdir": workdir,
                }
                surviving[job_id] = {**meta, "status": "running"}
            else:
                # proceso muerto (o sin PID, como Ollama): árbitro es output.md
                output_md = os.path.join(workdir, "output.md")
                if os.path.exists(output_md) and os.path.getsize(output_md) > 0:
                    surviving[job_id] = {**meta, "status": "done"}
                else:
                    surviving[job_id] = {**meta, "status": "error"}

        self._job_state = surviving
        self._persist_jobs()

    def _extract_meta(self, job_id: str) -> dict:
        """Extrae pid y log_path del entry recién creado en self._jobs por _invoke_async."""
        entry = self._jobs.get(job_id)
        if entry is None:
            return {"pid": None, "log_path": None}
        if isinstance(entry, dict):
            return {"pid": entry.get("pid"), "log_path": entry.get("log_path")}
        if isinstance(entry, tuple):
            # Convención: (proc, log_path, workdir, ...)
            proc = entry[0]
            return {
                "pid": getattr(proc, "pid", None),
                "log_path": entry[1] if len(entry) > 1 else None,
            }
        return {"pid": None, "log_path": None}

    def _update_job_state(self, job_id: str, status: str) -> None:
        """Actualiza status en _job_state y persiste. Llamar antes de del self._jobs[job_id]."""
        if job_id in self._job_state:
            self._job_state[job_id]["status"] = status
        self._persist_jobs()

    def _poll_reconstructed(self, job_id: str, entry) -> "str | None":
        """Maneja _poll para jobs reconstruidos sin Popen/Thread. Devuelve None si no aplica."""
        if not (isinstance(entry, dict) and entry.get("__reconstructed")):
            return None
        pid = entry.get("pid")
        workdir = entry["workdir"]
        log_path = entry.get("log_path")
        if pid and self._is_pid_alive(pid):
            return "pendiente"
        output_md = os.path.join(workdir, "output.md")
        if os.path.exists(output_md) and os.path.getsize(output_md) > 0:
            self._update_job_state(job_id, "done")
            del self._jobs[job_id]
            return "listo"
        log_msg = "(log no disponible)"
        if log_path:
            try:
                with open(log_path) as f:
                    log_msg = f.read()[-2000:]
            except FileNotFoundError:
                log_msg = "(log eliminado, posible reinicio del sistema)"
        self._update_job_state(job_id, "error")
        del self._jobs[job_id]
        return f"error: proceso terminó sin output\n{log_msg}"

    # --- MCP tools ---

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
            workdir = os.path.expanduser(arguments.get("workdir", self.default_workdir))
            os.makedirs(workdir, exist_ok=True)
            text = self._invoke_sync(arguments["prompt"], workdir, **self._extra_args(arguments))
            return [TextContent(type="text", text=text)]

        if name == f"{n}_run_async":
            job_id = uuid.uuid4().hex[:8]
            workdir = os.path.expanduser(arguments.get("workdir", self.default_workdir))
            os.makedirs(workdir, exist_ok=True)
            self._invoke_async(job_id, arguments["prompt"], workdir, **self._extra_args(arguments))
            meta = self._extract_meta(job_id)
            self._job_state[job_id] = {"status": "running", "workdir": workdir, **meta}
            self._persist_jobs()
            return [TextContent(type="text", text=job_id)]

        if name == f"{n}_done":
            return [TextContent(type="text", text=self._poll(arguments["job_id"]))]

        raise ValueError(f"Herramienta desconocida: {name}")

    def _poll_popen(self, job_id: str) -> str:
        """Implementación estándar de _poll para agentes basados en subprocess.Popen.
        Espera tupla (proc, log_path, workdir, ...) en self._jobs."""
        entry = self._jobs.get(job_id)
        if entry is None:
            state = self._job_state.get(job_id)
            if state:
                return state["status"]
            return f"error: job {job_id} no encontrado"

        result = self._poll_reconstructed(job_id, entry)
        if result is not None:
            return result

        proc, log_path, workdir = entry[0], entry[1], entry[2]
        ret = proc.poll()
        if ret is None:
            return "pendiente"
        self._update_job_state(job_id, "done" if ret == 0 else "error")
        del self._jobs[job_id]
        if ret == 0:
            return "listo"
        log_msg = "(log no disponible)"
        if log_path:
            try:
                with open(log_path) as f:
                    log_msg = f.read()[-2000:]
            except FileNotFoundError:
                log_msg = "(log eliminado, posible reinicio del sistema)"
        return f"error: rc={ret}\n{log_msg}"

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

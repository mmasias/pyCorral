import os
import shutil
import subprocess

from base import BaseAgentMCP, run


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


class KiroMCP(BaseAgentMCP):
    def __init__(self):
        super().__init__("kiro", "kiro-mcp", os.path.expanduser("~/misRepos/corral/kiro"))

    def _descriptions(self):
        n = self.agent_name
        return (
            "Ejecuta Kiro CLI de forma sincrona. Los ficheros generados se escriben en workdir.",
            "Ejecuta Kiro CLI en segundo plano y devuelve un job_id. Los ficheros generados se escriben en workdir.",
            f"Consulta el estado de un job lanzado con {n}_run_async.",
        )

    def _invoke_sync(self, prompt: str, workdir: str, **kwargs) -> str:
        proc = subprocess.run(
            [KIRO_BIN, "chat", "--no-interactive", "--trust-all-tools", prompt],
            cwd=workdir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=120,
        )
        if proc.returncode == 0:
            return "ok"
        return f"error (rc={proc.returncode}): {proc.stderr.decode(errors='replace')}"

    def _invoke_async(self, job_id: str, prompt: str, workdir: str, **kwargs) -> None:
        log_path = f"/tmp/kiro_job_{job_id}.log"
        log_file = open(log_path, "w")
        proc = subprocess.Popen(
            [KIRO_BIN, "chat", "--no-interactive", "--trust-all-tools", prompt],
            cwd=workdir,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=log_file,
        )
        self._jobs[job_id] = (proc, log_path, workdir)

    def _poll(self, job_id: str) -> str:
        return self._poll_popen(job_id)


if __name__ == "__main__":
    run(KiroMCP())

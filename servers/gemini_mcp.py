import glob
import os
import shutil
import subprocess

from base import BaseAgentMCP, run


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
GEMINI_MODEL = os.environ.get("CORRAL_GEMINI_MODEL", "gemini-2.5-flash")


class GeminiMCP(BaseAgentMCP):
    def __init__(self):
        super().__init__("gemini", "gemini-mcp", os.path.expanduser("~/misRepos/corral/gemini"))

    def _descriptions(self):
        n = self.agent_name
        return (
            "Ejecuta Gemini CLI de forma sincrona. La respuesta se escribe en output.md dentro de workdir.",
            "Ejecuta Gemini CLI en segundo plano y devuelve un job_id. La respuesta se escribe en output.md dentro de workdir.",
            f"Consulta el estado de un job lanzado con {n}_run_async.",
        )

    def _invoke_sync(self, prompt: str, workdir: str, **kwargs) -> str:
        proc = subprocess.run(
            [GEMINI_BIN, "-m", GEMINI_MODEL, "-y", "-p", prompt],
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
        log_path = f"/tmp/gemini_job_{job_id}.log"
        log_file = open(log_path, "w")
        proc = subprocess.Popen(
            [GEMINI_BIN, "-m", GEMINI_MODEL, "-y", "-p", prompt],
            cwd=workdir,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=log_file,
        )
        self._jobs[job_id] = (proc, log_path)

    def _poll(self, job_id: str) -> str:
        return self._poll_popen(job_id)


if __name__ == "__main__":
    run(GeminiMCP())

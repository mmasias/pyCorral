import glob
import os
import shutil
import subprocess

from base import BaseAgentMCP, run


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


def _make_env() -> dict:
    node_bin = os.path.dirname(OPENCODE_BIN)
    current_path = os.environ.get("PATH", "")
    return {
        **os.environ,
        "PATH": f"{node_bin}:{current_path}",
        "HOME": os.path.expanduser("~"),
    }


def _write_prompt_file(prefix: str, prompt: str) -> str:
    path = f"/tmp/opencode_prompt_{prefix}.txt"
    with open(path, "w") as f:
        f.write(prompt)
    return path


class OpenCodeMCP(BaseAgentMCP):
    def __init__(self):
        super().__init__("opencode", "opencode-mcp", os.path.expanduser("~/misRepos/corral/opencode"))

    def _descriptions(self):
        n = self.agent_name
        return (
            "Ejecuta OpenCode de forma sincrona via wrapper. La respuesta se escribe en output.md dentro de workdir.",
            "Ejecuta OpenCode en segundo plano via wrapper y devuelve un job_id. La respuesta se escribe en output.md dentro de workdir.",
            f"Consulta el estado de un job lanzado con {n}_run_async.",
        )

    def _invoke_sync(self, prompt: str, workdir: str, **kwargs) -> str:
        prompt_file = _write_prompt_file(str(os.getpid()), prompt)
        output_path = os.path.join(workdir, "output.md")
        log_path = f"/tmp/opencode_sync_{os.getpid()}.log"
        with open(output_path, "w") as out_f, open(log_path, "w") as err_f:
            proc = subprocess.run(
                [WRAPPER, prompt_file],
                env=_make_env(),
                cwd=workdir,
                stdin=subprocess.DEVNULL,
                stdout=out_f,
                stderr=err_f,
                timeout=300,
            )
        if proc.returncode == 0:
            return "ok"
        with open(log_path, errors="replace") as f:
            err = f.read()[-1000:]
        return f"error (rc={proc.returncode}): {err}"

    def _invoke_async(self, job_id: str, prompt: str, workdir: str, **kwargs) -> None:
        prompt_file = _write_prompt_file(job_id, prompt)
        output_path = os.path.join(workdir, "output.md")
        log_path = f"/tmp/opencode_job_{job_id}.log"
        out_f = open(output_path, "w")
        log_f = open(log_path, "w")
        proc = subprocess.Popen(
            [WRAPPER, prompt_file],
            env=_make_env(),
            cwd=workdir,
            stdin=subprocess.DEVNULL,
            stdout=out_f,
            stderr=log_f,
        )
        self._jobs[job_id] = (proc, log_path, out_f, log_f)

    def _poll(self, job_id: str) -> str:
        entry = self._jobs.get(job_id)
        if entry is None:
            return f"error: job {job_id} no encontrado"
        proc, log_path, out_f, log_f = entry
        ret = proc.poll()
        if ret is None:
            return "pendiente"
        out_f.close()
        log_f.close()
        del self._jobs[job_id]
        if ret == 0:
            return "listo"
        with open(log_path, errors="replace") as f:
            err = f.read()[-2000:]
        return f"error: rc={ret}\n{err}"


if __name__ == "__main__":
    run(OpenCodeMCP())

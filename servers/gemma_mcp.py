import os

from ollama_mcp import OllamaAgentMCP, run


class GemmaMCP(OllamaAgentMCP):
    def __init__(self):
        super().__init__(
            "gemma",
            "gemma-mcp",
            os.path.expanduser("~/misRepos/corral/gemma"),
            "CORRAL_GEMMA_MODEL",
            # gemma3 nativo (gemma3:latest, gemma3:1b) no soporta tools en
            # Ollama (error 400 en /api/chat con "tools"). Este fine-tune QAT
            # si declara capability "tools", requisito para write_file/read_file.
            "aliafshar/gemma3-it-qat-tools:4b",
        )


if __name__ == "__main__":
    run(GemmaMCP())

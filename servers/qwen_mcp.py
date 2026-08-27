import os

from ollama_mcp import OllamaAgentMCP, run


class QwenMCP(OllamaAgentMCP):
    def __init__(self):
        super().__init__(
            "qwen",
            "qwen-mcp",
            os.path.expanduser("~/misRepos/corral/qwen"),
            "CORRAL_QWEN_MODEL",
            "qwen2.5:7b",
        )


if __name__ == "__main__":
    run(QwenMCP())

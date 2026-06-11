import ollama
from PyQt6.QtCore import QThread, pyqtSignal


def list_local_models() -> list[str]:
    """Gibt die Namen aller lokal per Ollama installierten Modelle zurueck."""
    try:
        result = ollama.list()
        return [m.model for m in result.models if m.model is not None]
    except Exception:
        return []


def get_model_context_size(model_name: str) -> int:
    """Liest den explizit konfigurierten num_ctx-Wert aus dem Modelfile."""
    try:
        info = ollama.show(model_name)
        parameters = getattr(info, "parameters", "") or ""
        for line in parameters.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] == "num_ctx":
                return int(parts[1])
    except Exception:
        pass
    return 4096


class LLMWorker(QThread):
    """Führt den Ollama-API-Aufruf im Hintergrund-Thread aus (Streaming)."""

    token_received = pyqtSignal(str)   # einzelne Tokens während der Antwort
    response_ready = pyqtSignal(str)   # vollständige Antwort am Ende
    error_occurred = pyqtSignal(str)
    context_used = pyqtSignal(int)      # verbrauchte Tokens nach Abschluss

    def __init__(self, model: str, messages: list[dict], num_ctx: int):
        super().__init__()
        self.model = model
        self.messages = messages
        self.num_ctx = num_ctx
        self._full_response = ""

    def run(self):
        try:
            stream = ollama.chat(
                model=self.model,
                messages=self.messages,
                options={"num_ctx": self.num_ctx},
                stream=True,
            )
            last_chunk = None
            for chunk in stream:
                token = chunk["message"]["content"]
                self._full_response += token
                self.token_received.emit(token)
                last_chunk = chunk
            if last_chunk is not None:
                prompt_tokens = getattr(last_chunk, "prompt_eval_count", 0) or 0
                eval_tokens = getattr(last_chunk, "eval_count", 0) or 0
                self.context_used.emit(prompt_tokens + eval_tokens)
            self.response_ready.emit(self._full_response)
        except Exception as e:
            self.error_occurred.emit(str(e))

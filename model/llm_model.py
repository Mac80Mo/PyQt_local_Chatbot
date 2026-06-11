import ollama
from PyQt6.QtCore import QThread, pyqtSignal


def list_local_models() -> list[str]:
    """Gibt die Namen aller lokal per Ollama installierten Modelle zurueck."""
    try:
        result = ollama.list()
        return [m.model for m in result.models]
    except Exception:
        return []


class LLMWorker(QThread):
    """Führt den Ollama-API-Aufruf im Hintergrund-Thread aus (Streaming)."""

    token_received = pyqtSignal(str)   # einzelne Tokens während der Antwort
    response_ready = pyqtSignal(str)   # vollständige Antwort am Ende
    error_occurred = pyqtSignal(str)

    def __init__(self, model: str, messages: list[dict]):
        super().__init__()
        self.model = model
        self.messages = messages
        self._full_response = ""

    def run(self):
        try:
            stream = ollama.chat(
                model=self.model,
                messages=self.messages,
                stream=True,
            )
            for chunk in stream:
                token = chunk["message"]["content"]
                self._full_response += token
                self.token_received.emit(token)
            self.response_ready.emit(self._full_response)
        except Exception as e:
            self.error_occurred.emit(str(e))

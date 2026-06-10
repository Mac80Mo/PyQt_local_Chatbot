from PyQt6.QtGui import QTextCursor
from model.llm_model import LLMWorker


class ChatController:
    """Verbindet View und Model; enthält die gesamte Chat-Logik."""

    def __init__(self, view, model_name: str = "llama3"):
        self.view = view
        self.model_name = model_name
        self.history: list[dict] = []
        self._worker: LLMWorker | None = None

        # Signale der View verdrahten
        self.view.send_button.clicked.connect(self.handle_send)
        self.view.input_field.returnPressed.connect(self.handle_send)
        self.view.cancel_button.clicked.connect(self.handle_cancel)

    # ------------------------------------------------------------------
    # Öffentliche Slots
    # ------------------------------------------------------------------

    def handle_send(self):
        text = self.view.input_field.text().strip()
        if not text:
            return

        self.view.input_field.clear()
        self.view.chat_display.append(f"<b>Du:</b> {text}<br><b>Bot:</b> ")

        self.history.append({"role": "user", "content": text})

        self._set_busy(True)

        self._worker = LLMWorker(self.model_name, list(self.history))
        self._worker.token_received.connect(self._append_token)
        self._worker.finished.connect(self._on_finished)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.start()

    def handle_cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait()
            self.view.chat_display.append("<br><i>[Abgebrochen]</i>")
        self._set_busy(False)
        self._worker = None

    # ------------------------------------------------------------------
    # Private Helfer
    # ------------------------------------------------------------------

    def _append_token(self, token: str):
        """Token direkt ans Ende des Displays anhängen (kein extra Zeilenumbruch)."""
        cursor = self.view.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(token)
        self.view.chat_display.setTextCursor(cursor)
        self.view.chat_display.ensureCursorVisible()

    def _on_finished(self, full_response: str):
        self.history.append({"role": "assistant", "content": full_response})
        self.view.chat_display.append("")  # Leerzeile als Trenner
        self._set_busy(False)
        self._worker = None

    def _on_error(self, message: str):
        self.view.chat_display.append(
            f"<br><span style='color:red'><b>Fehler:</b> {message}</span>"
        )
        self._set_busy(False)
        self._worker = None

    def _set_busy(self, busy: bool):
        self.view.send_button.setEnabled(not busy)
        self.view.cancel_button.setEnabled(busy)
        self.view.input_field.setEnabled(not busy)

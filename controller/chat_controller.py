from PyQt6.QtGui import QTextCursor
from model.llm_model import LLMWorker, list_local_models


class ChatController:
    """Verbindet View und Model; enthält die gesamte Chat-Logik."""

    def __init__(self, view, model_name: str = ""):
        self.view = view
        self.history: list[dict] = []
        self._worker: LLMWorker | None = None
        self._is_busy: bool = False

        # Verfuegbare Modelle laden und Selector befuellen
        models = list_local_models()
        if models:
            self.view.model_selector.addItems(models)
            # Standardmodell vorauswaehlen, falls angegeben und vorhanden
            if model_name and model_name in models:
                self.view.model_selector.setCurrentText(model_name)
            self.model_name = self.view.model_selector.currentText()
        else:
            self.view.model_selector.addItem("Kein Modell gefunden")
            self.view.model_selector.setEnabled(False)
            self.model_name = ""

        # Signale der View verdrahten
        self.view.send_button.clicked.connect(self.handle_send)
        self.view.input_field.returnPressed.connect(self.handle_send)
        self.view.cancel_button.clicked.connect(self.handle_cancel)
        self.view.model_selector.currentTextChanged.connect(self._on_model_changed)

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
        self._worker.response_ready.connect(self._on_finished)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.finished.connect(self._worker.deleteLater)  # sicheres Qt-Cleanup
        self._worker.start()

    def handle_cancel(self):
        if self._is_busy:
            if self._worker:
                self._worker.terminate()
                self._worker.wait()
            self.view.chat_display.append("<br><i>[Abgebrochen]</i>")
            self._set_busy(False)
        else:
            self.view.chat_display.clear()
            self.history.clear()

    # ------------------------------------------------------------------
    # Private Helfer
    # ------------------------------------------------------------------

    def _on_model_changed(self, model_name: str):
        """Wird aufgerufen, wenn der Benutzer ein anderes Modell auswaehlt."""
        self.model_name = model_name

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
        # Kein self._worker = None hier — deleteLater() uebernimmt das Cleanup

    def _on_error(self, message: str):
        self.view.chat_display.append(
            f"<br><span style='color:red'><b>Fehler:</b> {message}</span>"
        )
        self._set_busy(False)
        # Kein self._worker = None hier — deleteLater() uebernimmt das Cleanup

    def _set_busy(self, busy: bool):
        self._is_busy = busy
        self.view.send_button.setEnabled(not busy)
        self.view.cancel_button.setText("Abbrechen" if busy else "Chat löschen")
        self.view.input_field.setEnabled(not busy)

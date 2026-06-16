from datetime import datetime
from zoneinfo import ZoneInfo

from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from model.llm_model import LLMWorker, list_local_models
from model.rag_model import RAGStore
from model.rag_worker import IndexWorker, QueryWorker


class ChatController:
    """Verbindet View und Model; enthält die gesamte Chat-Logik."""

    def __init__(self, view, model_name: str = ""):
        self.view = view

        self._worker: LLMWorker | None = None
        self._index_worker: IndexWorker | None = None
        self._query_worker: QueryWorker | None = None
        self._pending_query_text: str = ""
        self._is_busy: bool = False
        self.history: list[dict] = self._build_initial_history()

        # RAG-Speicher initialisieren
        self._rag_store = RAGStore()

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
        self.view.add_file_button.clicked.connect(self.handle_file_add)
        self.view.delete_doc_button.clicked.connect(self.handle_delete_document)
        self.view.clear_store_button.clicked.connect(self.handle_clear_store)
        self.view.closing.connect(self._on_closing)

        # Initiale Dokumentenliste laden
        self._refresh_document_list()

    # ------------------------------------------------------------------
    # Öffentliche Slots
    # ------------------------------------------------------------------

    def handle_send(self):
        text = self.view.input_field.text().strip()
        if not text:
            return

        self.view.input_field.clear()
        self.view.chat_display.append(f"<b>Du:</b> {text}<br><b>Bot:</b> ")
        self._set_busy(True)

        if self.view.rag_toggle.isChecked():
            # RAG-Query im Hintergrund-Thread, um den UI-Thread nicht zu blockieren.
            self._pending_query_text = text
            self.view.rag_status_label.setText("Suche läuft…")
            self._query_worker = QueryWorker(self._rag_store, text)
            self._query_worker.query_finished.connect(self._on_query_finished)
            self._query_worker.error_occurred.connect(self._on_query_error)
            self._query_worker.finished.connect(lambda: setattr(self, '_query_worker', None))
            self._query_worker.start()
        else:
            self.history.append({"role": "user", "content": text})
            self._start_llm_worker()

    def handle_cancel(self):
        if self._is_busy:
            if self._query_worker and self._query_worker.isRunning():
                self._query_worker.terminate()
                self._query_worker.wait()
            if self._worker:
                self._worker.terminate()
                self._worker.wait()
            self.view.chat_display.append("<br><i>[Abgebrochen]</i>")
            self._set_busy(False)
        else:
            self.view.chat_display.clear()
            self.history = self._build_initial_history()

    def handle_file_add(self):
        """Öffnet den Dateidialog und startet die Indexierung im Hintergrund."""
        if self._index_worker and self._index_worker.isRunning():
            return
        path, _ = QFileDialog.getOpenFileName(
            self.view,
            "Datei hinzufügen",
            "",
            "Dokumente (*.txt *.md *.pdf *.docx)",
        )
        if not path:
            return
        self.view.rag_status_label.setText("Wird indexiert…")
        self.view.add_file_button.setEnabled(False)
        self._index_worker = IndexWorker(self._rag_store, path)
        self._index_worker.indexing_finished.connect(self._on_indexing_finished)
        self._index_worker.error_occurred.connect(self._on_indexing_error)
        self._index_worker.finished.connect(lambda: setattr(self, '_index_worker', None))
        self._index_worker.start()

    def handle_delete_document(self):
        """Entfernt das ausgewählte Dokument aus dem Vektorspeicher."""
        selected = self.view.document_list.currentItem()
        if not selected:
            return
        filename = selected.text()
        antwort = QMessageBox.question(
            self.view,
            "Dokument entfernen",
            f'Dokument "{filename}" wirklich aus dem Vektorspeicher entfernen?',
        )
        if antwort != QMessageBox.StandardButton.Yes:
            return
        self._rag_store.delete_document(filename)
        self._refresh_document_list()

    def handle_clear_store(self):
        """Leert den gesamten Vektorspeicher."""
        antwort = QMessageBox.question(
            self.view,
            "Vektorspeicher leeren",
            "Wirklich alle Dokumente aus dem Vektorspeicher löschen?",
        )
        if antwort != QMessageBox.StandardButton.Yes:
            return
        self._rag_store.clear()
        self._refresh_document_list()

    # ------------------------------------------------------------------
    # Private Helfer
    # ------------------------------------------------------------------

    def _on_query_finished(self, chunks: list):
        """Wird aufgerufen, wenn der RAG-Query-Worker ein Ergebnis liefert."""
        text = self._pending_query_text
        if chunks:
            # Sliding-Window: nur der aktuelle Turn enthaelt Kontext,
            # aeltere Turns bleiben unveraendert.
            kontext = "\n---\n".join(chunks)
            user_content = (
                f"Nutze folgende Kontext-Informationen zur Beantwortung der Frage:\n\n"
                f"{kontext}\n\nFrage: {text}"
            )
        else:
            user_content = text
        self.history.append({"role": "user", "content": user_content})
        self._refresh_document_list()  # Aktualisiert rag_status_label
        self._start_llm_worker()

    def _on_query_error(self, message: str):
        """Wird aufgerufen, wenn der RAG-Query fehlschlaegt. LLM laeuft ohne Kontext weiter."""
        self.view.chat_display.append(
            f"<br><span style='color:orange'><b>RAG-Warnung:</b> {message}</span><br><b>Bot:</b> "
        )
        self.history.append({"role": "user", "content": self._pending_query_text})
        self._refresh_document_list()
        self._start_llm_worker()

    def _start_llm_worker(self):
        """Startet den LLM-Worker mit der aktuellen History."""
        self._worker = LLMWorker(self.model_name, self.history)
        self._worker.token_received.connect(self._append_token)
        self._worker.response_ready.connect(self._on_finished)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.finished.connect(lambda: setattr(self, '_worker', None))
        self._worker.start()

    def _build_initial_history(self) -> list[dict]:
        """Erstellt die initiale Nachrichtenhistorie mit einem System-Prompt."""
        jetzt = datetime.now(tz=ZoneInfo("Europe/Berlin"))
        inhalt = (
            f"Das aktuelle Datum ist {jetzt.strftime('%d.%m.%Y')}, "
            f"die Uhrzeit ist {jetzt.strftime('%H:%M')} Uhr ({jetzt.strftime('%Z')})."
        )
        return [{"role": "system", "content": inhalt}]

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

    def _on_error(self, message: str):
        self.view.chat_display.append(
            f"<br><span style='color:red'><b>Fehler:</b> {message}</span>"
        )
        self._set_busy(False)

    def _set_busy(self, busy: bool):
        self._is_busy = busy
        self.view.send_button.setEnabled(not busy)
        self.view.cancel_button.setText("Abbrechen" if busy else "Chat löschen")
        self.view.input_field.setEnabled(not busy)

    def _on_indexing_finished(self, filename: str):
        # _refresh_document_list aktualisiert auch explizit rag_status_label.
        self._refresh_document_list()
        self.view.add_file_button.setEnabled(True)

    def _on_indexing_error(self, message: str):
        self.view.rag_status_label.setText("Fehler beim Indexieren")
        self.view.chat_display.append(
            f"<br><span style='color:red'><b>RAG-Fehler:</b> {message}</span>"
        )
        self.view.add_file_button.setEnabled(True)

    def _on_closing(self):
        """Beendet laufende Hintergrund-Threads vor dem Schließen der Anwendung."""
        if self._query_worker and self._query_worker.isRunning():
            self._query_worker.terminate()
            self._query_worker.wait()
        if self._index_worker and self._index_worker.isRunning():
            self._index_worker.requestInterruption()
            self._index_worker.wait()

    def _refresh_document_list(self):
        """Aktualisiert die Dokumentenliste und das Status-Label."""
        documents = self._rag_store.list_documents()
        self.view.document_list.clear()
        self.view.document_list.addItems(documents)
        count = len(documents)
        self.view.rag_status_label.setText(
            f"{count} Dokument{'e' if count != 1 else ''} indexiert"
        )

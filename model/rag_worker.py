from PyQt6.QtCore import QThread, pyqtSignal

from model.rag_model import RAGStore, IndexingAbortedError


class IndexWorker(QThread):
    """Indexiert eine Datei im Hintergrund-Thread."""

    indexing_finished = pyqtSignal(str)  # Dateiname bei Erfolg
    error_occurred = pyqtSignal(str)

    def __init__(self, rag_store: RAGStore, file_path: str):
        super().__init__()
        self._rag_store = rag_store
        self._file_path = file_path

    def run(self):
        try:
            filename = self._rag_store.add_document(
                self._file_path,
                should_stop=self.isInterruptionRequested,
            )
            self.indexing_finished.emit(filename)
        except IndexingAbortedError:
            pass  # Abbruch durch requestInterruption() – kein Fehler-Signal
        except Exception as e:
            self.error_occurred.emit(str(e))


class QueryWorker(QThread):
    """Fuehrt eine RAG-Vektorsuche im Hintergrund-Thread durch."""

    query_finished = pyqtSignal(list)  # Liste der relevanten Chunks
    error_occurred = pyqtSignal(str)

    def __init__(self, rag_store: RAGStore, query_text: str):
        super().__init__()
        self._rag_store = rag_store
        self._query_text = query_text

    def run(self):
        try:
            chunks = self._rag_store.query(self._query_text)
            self.query_finished.emit(chunks)
        except Exception as e:
            self.error_occurred.emit(str(e))

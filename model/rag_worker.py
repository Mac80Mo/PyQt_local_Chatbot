import pathlib

from PyQt6.QtCore import QThread, pyqtSignal

from model.rag_model import RAGStore, IndexingAbortedError, compute_file_hash, extract_date_filter_from_query


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


class FolderIndexWorker(QThread):
    """Indexiert alle unterstützten Dateien eines Ordners sequenziell im Hintergrund."""

    file_indexed = pyqtSignal(str)          # Dateiname bei Erfolg
    folder_indexing_finished = pyqtSignal(int, int)  # (erfolgreich, gesamt)
    error_occurred = pyqtSignal(str)

    def __init__(self, rag_store: RAGStore, file_paths: list[str]):
        super().__init__()
        self._rag_store = rag_store
        self._file_paths = file_paths

    def run(self):
        erfolgreich = 0
        for path in self._file_paths:
            if self.isInterruptionRequested():
                break
            try:
                filename = pathlib.Path(path).name
                aktueller_hash = compute_file_hash(path)
                if aktueller_hash == self._rag_store.get_document_hash(filename):
                    continue
                filename = self._rag_store.add_document(
                    path,
                    should_stop=self.isInterruptionRequested,
                )
                self.file_indexed.emit(filename)
                erfolgreich += 1
            except IndexingAbortedError:
                break
            except Exception as e:
                self.error_occurred.emit(str(e))
        self.folder_indexing_finished.emit(erfolgreich, len(self._file_paths))


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
            date_filter = extract_date_filter_from_query(self._query_text)
            filename_filter = self._rag_store.find_filename_filter(self._query_text)
            if date_filter and filename_filter:
                where_filter: dict | None = {"$and": [date_filter, filename_filter]}
            else:
                where_filter = date_filter or filename_filter
            chunks = self._rag_store.query(self._query_text, where_filter)
            if not self.isInterruptionRequested():
                self.query_finished.emit(chunks)
        except Exception as e:
            if not self.isInterruptionRequested():
                self.error_occurred.emit(str(e))

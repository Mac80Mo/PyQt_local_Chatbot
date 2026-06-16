import os
import pathlib
from collections.abc import Callable
from dataclasses import dataclass, field

import ollama
import chromadb
from chromadb import EmbeddingFunction, Documents, Embeddings
from chromadb.api.types import Metadata


class IndexingAbortedError(Exception):
    """Wird ausgeloest, wenn die Indexierung vom Benutzer abgebrochen wurde."""


@dataclass
class RAGConfig:
    """Konfiguration für den RAG-Vektorspeicher."""
    embedding_model: str = "nomic-embed-text"
    chunk_size: int = 800
    chunk_overlap: int = 100
    top_k: int = 3
    collection_name: str = "rag_dokumente"
    persist_dir: str = field(
        default_factory=lambda: str(
            pathlib.Path.home() / ".local" / "share" / "pyqt-chatbot" / "chroma_db"
        )
    )


class _OllamaEmbeddingFunction(EmbeddingFunction):
    """ChromaDB-kompatible Embedding-Funktion über Ollama."""

    def __init__(self, model: str):
        self._model = model

    def __call__(self, input: Documents) -> Embeddings:
        # Ollama unterstuetzt kein Batch-Embedding; jeder Text wird einzeln eingebettet.
        embeddings = []
        for text in input:
            response = ollama.embeddings(model=self._model, prompt=text)
            embeddings.append(response["embedding"])
        return embeddings


def parse_file(file_path: str) -> str:
    """Liest eine Datei und gibt den Textinhalt zurück."""
    suffix = pathlib.Path(file_path).suffix.lower()
    if suffix in (".txt", ".md"):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    elif suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    elif suffix == ".docx":
        from docx import Document
        doc = Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs)
    else:
        raise ValueError(f"Nicht unterstütztes Dateiformat: {suffix}")


def chunk_text(text: str, size: int = 800, overlap: int = 100) -> list[str]:
    """Teilt Text in Chunks auf, wobei Absatzgrenzen bevorzugt werden.

    Einzelne Absätze, die größer als 'size' sind, werden zeichenbasiert
    mit Überlappung aufgeteilt.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for paragraph in paragraphs:
        if current_len + len(paragraph) <= size:
            current_parts.append(paragraph)
            current_len += len(paragraph)
        else:
            if current_parts:
                chunks.append("\n\n".join(current_parts))
            if len(paragraph) > size:
                start = 0
                letzter_chunk = ""
                while start < len(paragraph):
                    letzter_chunk = paragraph[start:start + size]
                    chunks.append(letzter_chunk)
                    start += size - overlap
                # Letzten 'overlap' Zeichen als Seed fuer den naechsten Abschnitt setzen,
                # damit keine Luecke zwischen zeichenbasiertem Split und dem Folgeabsatz entsteht.
                seed = letzter_chunk[-overlap:].strip()
                current_parts = [seed] if seed else []
                current_len = len(seed) if seed else 0
            else:
                current_parts = [paragraph]
                current_len = len(paragraph)

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    return [c for c in chunks if c.strip()]


class RAGStore:
    """Verwaltet den persistenten Vektorspeicher."""

    def __init__(
        self,
        config: RAGConfig | None = None,
        embedding_function: EmbeddingFunction | None = None,
    ):
        # ChromaDB PersistentClient ist thread-sicher und kann aus Worker-Threads aufgerufen werden.
        self._config = config or RAGConfig()
        os.makedirs(self._config.persist_dir, exist_ok=True)
        self._embedding_fn = embedding_function or _OllamaEmbeddingFunction(self._config.embedding_model)
        self._client = chromadb.PersistentClient(path=self._config.persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=self._config.collection_name,
            embedding_function=self._embedding_fn,
        )

    def add_document(
        self,
        file_path: str,
        should_stop: Callable[[], bool] = lambda: False,
    ) -> str:
        """Indexiert eine Datei. Bestehende Einträge werden vorher entfernt.

        'should_stop' wird nach dem Chunking geprüft. Gibt die Funktion True
        zurück, wird eine InterruptedError ausgelöst und nichts gespeichert.
        """
        filename = pathlib.Path(file_path).name
        self._delete_chunks_by_filename(filename)
        text = parse_file(file_path)
        chunks = chunk_text(text, self._config.chunk_size, self._config.chunk_overlap)
        if not chunks:
            raise ValueError(f"Keine Textinhalte in Datei gefunden: {filename}")
        if should_stop():
            raise IndexingAbortedError("Indexierung abgebrochen.")
        ids = [f"{filename}__chunk_{i}" for i in range(len(chunks))]
        metadatas: list[Metadata] = [{"filename": filename, "chunk_index": i} for i in range(len(chunks))]
        self._collection.add(documents=chunks, ids=ids, metadatas=metadatas)
        return filename

    def query(self, text: str) -> list[str]:
        """Gibt die relevantesten Chunks für den gegebenen Text zurück."""
        count = self._collection.count()
        if count == 0:
            return []
        results = self._collection.query(
            query_texts=[text],
            n_results=min(self._config.top_k, count),
        )
        return results["documents"][0] if results["documents"] else []

    def list_documents(self) -> list[str]:
        """Gibt eindeutige Dateinamen aller indexierten Dokumente zurück."""
        result = self._collection.get(include=["metadatas"])
        raw = result["metadatas"] or []
        filenames = {str(m["filename"]) for m in raw if m and "filename" in m}
        return sorted(filenames)

    def delete_document(self, filename: str) -> None:
        """Entfernt alle Chunks eines bestimmten Dokuments."""
        self._delete_chunks_by_filename(filename)

    def clear(self) -> None:
        """Löscht den gesamten Vektorspeicher und legt ihn neu an."""
        self._client.delete_collection(self._config.collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._config.collection_name,
            embedding_function=self._embedding_fn,
        )

    def _delete_chunks_by_filename(self, filename: str) -> None:
        # include=[] ist korrekt: IDs werden von ChromaDB immer zurueckgegeben
        # und muessen nicht explizit angefragt werden.
        result = self._collection.get(
            where={"filename": filename},
            include=[],
        )
        if result["ids"]:
            self._collection.delete(ids=result["ids"])

import datetime
import hashlib
import os
import pathlib
import re
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
    top_k: int = 6
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


SUPPORTED_SUFFIXES: frozenset[str] = frozenset({".txt", ".md", ".pdf", ".docx"})


def list_supported_files(folder_path: str) -> list[str]:
    """Gibt alle unterstützten Dateien der obersten Ebene eines Ordners zurück."""
    folder = pathlib.Path(folder_path)
    return [
        str(entry)
        for entry in sorted(folder.iterdir())
        if entry.is_file() and entry.suffix.lower() in SUPPORTED_SUFFIXES
    ]


def compute_file_hash(file_path: str) -> str:
    """Berechnet den SHA-256-Hash des Dateiinhalts."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            sha256.update(block)
    return sha256.hexdigest()


def _format_mtime(file_path: str) -> str:
    """Gibt das letzte Aenderungsdatum einer Datei als lesbaren String zurueck."""
    mtime = os.path.getmtime(file_path)
    return datetime.datetime.fromtimestamp(mtime).strftime("%d.%m.%Y")


_MONTH_NAMES: dict[str, int] = {
    "januar": 1, "februar": 2, "maerz": 3, "märz": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "dezember": 12,
}


def _extract_date_from_filename(filename: str) -> int:
    """Extrahiert ein Datum aus dem Dateinamen als Integer YYYYMMDD, oder 0."""
    m = re.search(r'(\d{4})[\-_]?(\d{2})[\-_]?(\d{2})', filename)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
            return year * 10000 + month * 100 + day
    return 0


def _date_int_to_str(date_int: int) -> str:
    """Formatiert einen YYYYMMDD-Integer als DD.MM.YYYY-String."""
    year = date_int // 10000
    month = (date_int % 10000) // 100
    day = date_int % 100
    return f"{day:02d}.{month:02d}.{year}"


def extract_date_filter_from_query(query: str) -> dict | None:
    """Erkennt Datumsangaben in einer Suchanfrage und gibt einen ChromaDB-Where-Filter zurueck."""
    # DD.MM.YYYY oder D.M.YYYY
    m = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', query)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return {"filename_date": {"$eq": year * 10000 + month * 100 + day}}
    # DD. Monatsname YYYY
    month_pattern = "|".join(_MONTH_NAMES.keys())
    m = re.search(rf'(\d{{1,2}})\.?\s*({month_pattern})\s+(\d{{4}})', query.lower())
    if m:
        day, month_name, year = int(m.group(1)), m.group(2), int(m.group(3))
        month = _MONTH_NAMES[month_name]
        return {"filename_date": {"$eq": year * 10000 + month * 100 + day}}
    # Monatsname YYYY (ohne Tag)
    m = re.search(rf'({month_pattern})\s+(\d{{4}})', query.lower())
    if m:
        month_name, year = m.group(1), int(m.group(2))
        month = _MONTH_NAMES[month_name]
        return {"filename_date": {"$gte": year * 10000 + month * 100 + 1,
                                  "$lte": year * 10000 + month * 100 + 31}}
    return None


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
    if overlap >= size:
        raise ValueError(
            f"chunk_overlap ({overlap}) muss kleiner als chunk_size ({size}) sein."
        )
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
        zurück, wird eine IndexingAbortedError ausgelöst und nichts gespeichert.
        """
        filename = pathlib.Path(file_path).name
        file_hash = compute_file_hash(file_path)
        file_date = _format_mtime(file_path)
        filename_date = _extract_date_from_filename(filename)
        self._delete_chunks_by_filename(filename)
        text = parse_file(file_path)
        chunks = chunk_text(text, self._config.chunk_size, self._config.chunk_overlap)
        if not chunks:
            raise ValueError(f"Keine Textinhalte in Datei gefunden: {filename}")
        if should_stop():
            raise IndexingAbortedError("Indexierung abgebrochen.")
        # Dateinamen-Praefix in jeden Chunk einbetten, damit Datums- und Namensuchen greifen.
        prefix = f"Datei: {filename}"
        if filename_date:
            prefix += f" | Datum: {_date_int_to_str(filename_date)}"
        prefixed_chunks = [f"{prefix}\n{chunk}" for chunk in chunks]
        ids = [f"{filename}__chunk_{i}" for i in range(len(prefixed_chunks))]
        metadatas: list[Metadata] = [
            {"filename": filename, "chunk_index": i, "file_hash": file_hash,
             "file_date": file_date, "filename_date": filename_date}
            for i in range(len(prefixed_chunks))
        ]
        self._collection.add(documents=prefixed_chunks, ids=ids, metadatas=metadatas)
        return filename

    def get_document_hash(self, filename: str) -> str | None:
        """Gibt den gespeicherten SHA-256-Hash eines Dokuments zurück, oder None."""
        result = self._collection.get(
            where={"filename": filename},
            include=["metadatas"],
        )
        metadatas = result.get("metadatas") or []
        if metadatas and metadatas[0]:
            value = metadatas[0].get("file_hash")
            return str(value) if value is not None else None
        return None

    def query(self, text: str, where_filter: dict | None = None) -> list[dict]:
        """Gibt die relevantesten Chunks mit Quellinformationen zurueck.

        Jedes Element enthaelt 'text', 'filename' und 'file_date'.
        Bei gesetztem where_filter wird die Suche auf passende Dokumente eingeschraenkt;
        findet der Filter keine Treffer, wird automatisch auf alle Dokumente zurueckgefallen.
        """
        total_count = self._collection.count()
        if total_count == 0:
            return []
        effective_filter = where_filter
        n_results_count = total_count
        if effective_filter:
            gefiltert = self._collection.get(where=effective_filter, include=[])
            gefiltert_anzahl = len(gefiltert["ids"])
            if gefiltert_anzahl == 0:
                effective_filter = None  # Fallback auf alle Dokumente
            else:
                n_results_count = gefiltert_anzahl
        query_kwargs: dict = {
            "query_texts": [text],
            "n_results": min(self._config.top_k, n_results_count),
            "include": ["documents", "metadatas"],
        }
        if effective_filter:
            query_kwargs["where"] = effective_filter
        results = self._collection.query(**query_kwargs)
        documents = results["documents"][0] if results["documents"] else []
        metadatas = results["metadatas"][0] if results["metadatas"] else []
        chunks = []
        for doc, meta in zip(documents, metadatas):
            chunks.append({
                "text": doc,
                "filename": str(meta.get("filename", "")) if meta else "",
                "file_date": str(meta.get("file_date", "")) if meta else "",
            })
        return chunks

    def list_documents(self) -> list[str]:
        """Gibt eindeutige Dateinamen aller indexierten Dokumente zurück."""
        result = self._collection.get(include=["metadatas"])
        raw = result["metadatas"] or []
        filenames = {str(m["filename"]) for m in raw if m and "filename" in m}
        return sorted(filenames)

    def get_store_size_bytes(self) -> int:
        """Gibt die Gesamtgröße des Vektorspeichers auf dem Dateisystem in Bytes zurück."""
        total = 0
        for dirpath, _, filenames in os.walk(self._config.persist_dir):
            for f in filenames:
                total += os.path.getsize(os.path.join(dirpath, f))
        return total

    def find_filename_filter(self, query: str) -> dict | None:
        """Erkennt Dateinamen-Hinweise in einer Suchanfrage und gibt einen Where-Filter zurück.

        Mindestens die Hälfte der signifikanten Schlüsselwörter eines Dateinamens
        muss in der Anfrage enthalten sein, damit der Filter greift.
        """
        query_words = set(re.split(r'\W+', query.lower()))
        query_words.discard('')
        best_match: str | None = None
        best_score = 0.0
        for filename in self.list_documents():
            stem = pathlib.Path(filename).stem.lower()
            keywords = [w for w in re.split(r'[\s_\-\.0-9]+', stem) if len(w) > 3]
            if not keywords:
                continue
            hits = sum(1 for kw in keywords if kw in query_words)
            score = hits / len(keywords)
            if score > best_score:
                best_score = score
                best_match = filename
        if best_score >= 0.5 and best_match:
            return {"filename": {"$eq": best_match}}
        return None

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

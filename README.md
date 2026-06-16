# PyQt Local Chatbot

Ein lokaler Chatbot mit PyQt6-Oberfläche, der über Ollama mit einem lokalen Sprachmodell kommuniziert.

## Voraussetzungen

- Python 3.11+
- [Ollama](https://ollama.com) installiert und gestartet

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Modell herunterladen

```bash
ollama pull llama3.2:3b
```

## Starten

```bash
source .venv/bin/activate
python app.py
```

## Projektstruktur

```
app.py                  # Einstiegspunkt
controller/
    chat_controller.py  # Verbindet View und Model
model/
    llm_model.py        # Ollama-Anbindung (Streaming)
view/
    main_window.py      # PyQt6-Benutzeroberfläche
```

## RAG (Retrieval-Augmented Generation)

Dokumente können lokal indexiert und als Kontext in Anfragen eingebunden werden.

**Unterstützte Formate:** `.txt`, `.md`, `.pdf`, `.docx`

**Funktionsweise:**
- Dokumente werden in Chunks (800 Zeichen, 100 Überlappung) aufgeteilt und als Vektoren in ChromaDB gespeichert.
- Embeddings werden über Ollama erzeugt (Standardmodell: `nomic-embed-text`).
- Pro Anfrage werden die 6 relevantesten Chunks abgerufen und dem Prompt vorangestellt.
- Datumsangaben im Dateinamen oder in der Anfrage werden als Filter ausgewertet.
- Indexierung läuft im Hintergrund-Thread, ohne die UI zu blockieren.

**Embedding-Modell herunterladen:**

```bash
ollama pull nomic-embed-text
```

Der Vektorspeicher wird persistent unter `~/.local/share/pyqt-chatbot/chroma_db` abgelegt.

## Modell wechseln

In `app.py` den Parameter `model_name` anpassen:

```python
controller = ChatController(window, model_name="llama3.2:3b")
```

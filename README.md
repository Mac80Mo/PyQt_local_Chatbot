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

## Modell wechseln

In `app.py` den Parameter `model_name` anpassen:

```python
controller = ChatController(window, model_name="llama3.2:3b")
```

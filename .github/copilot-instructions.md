# Copilot Instructions – PyQt Local Chatbot

## Architektur

- Strikte Einhaltung des MVC-Patterns: `model/`, `controller/`, `view/` sind klar getrennte Schichten.
- Separation of Concerns: Jede Schicht hat genau eine Verantwortung.
  - `model/` – Datenzugriff und LLM-Kommunikation (ollama), kein UI-Code.
  - `view/` – Nur Qt-Widgets und Layout, keine Geschaeftslogik.
  - `controller/` – Verbindet View und Model, enthaelt die Anwendungslogik.
- Keine direkten Rueckwaertsreferenzen vom Model zur View.
- `ollama.*` darf ausschliesslich im `model/`-Layer aufgerufen werden.

## Kommunikation zwischen Schichten

- Kommunikation zwischen Schichten erfolgt ausschliesslich ueber Qt-Signals und Slots.
- UI-Updates duerfen nur im Haupt-Thread stattfinden.
- Hintergrundoperationen laufen in `QThread`-Subklassen.
- Kein direkter Einsatz von `threading.Thread` oder `concurrent.futures`.

## Tech-Stack

- Python 3, PyQt6, Ollama.
- Keine alternativen UI-Frameworks (kein Tkinter, kein PySide6).
- Keine alternativen HTTP-/API-Clients (kein `requests`, kein `httpx` direkt).
- Abhaengigkeiten werden ausschliesslich ueber `requirements.txt` verwaltet.

## Code-Qualitaet

- Clean Code: Sprechende Namen, kleine Funktionen mit einer einzigen Aufgabe.
- Kein Over-Engineering: Keine Abstraktionen, Interfaces oder Helfer, die nicht benoetigt werden.
- Keine `print()`-Statements im Produktionscode.
- Exceptions werden nicht still verschluckt. Fehler werden ueber `error_occurred`-Signal als String weitergereicht.
- Konfigurierbare Werte (z.B. Modellname) gehoeren nicht hardcodiert in den Controller.

## Sprache

- UI-Texte, Kommentare und Docstrings sind auf Deutsch.
- Variablen- und Funktionsnamen sind auf Englisch.

## Allgemein

- Keine Emojis im Code oder in Kommentaren.
- Keine automatischen Refactorings oder strukturellen Aenderungen ohne explizite Aufforderung.
- Keine zusaetzlichen Features, die nicht angefragt wurden.

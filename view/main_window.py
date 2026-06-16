from PyQt6.QtWidgets import (
    QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton,
    QComboBox, QLabel, QToolBar,
    QCheckBox, QListWidget, QSplitter,
)
from PyQt6.QtCore import Qt, pyqtSignal


class MainWindow(QMainWindow):
    closing = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Chatbot")
        self.setMinimumSize(600, 500)

        # --- Toolbar mit Modellauswahl ---
        toolbar = QToolBar("Modellauswahl")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        toolbar.addWidget(QLabel("Modell: "))
        self.model_selector = QComboBox()
        self.model_selector.setMinimumWidth(200)
        toolbar.addWidget(self.model_selector)

        # --- Chatverlauf ---
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet("border: 1px solid #555555;")
        self.chat_display.setPlaceholderText("Chatverlauf erscheint hier...")

        # --- Eingabefeld ---
        self.input_field = QLineEdit()
        self.input_field.setStyleSheet("border: 1px solid #E4E4C9;")
        self.input_field.setPlaceholderText("Nachricht eingeben...")

        # --- Buttons ---
        self.send_button = QPushButton("Senden")
        self.send_button.setDefault(True)

        self.cancel_button = QPushButton("Chat löschen")

        # --- Button-Layout (Eingabe + Buttons nebeneinander) ---
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.input_field)
        button_layout.addWidget(self.send_button)
        button_layout.addWidget(self.cancel_button)

        # --- Chat-Bereich ---
        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.addWidget(self.chat_display)
        chat_layout.addLayout(button_layout)

        # --- RAG-Panel ---
        rag_widget = QWidget()
        rag_widget.setMinimumWidth(220)
        rag_layout = QVBoxLayout(rag_widget)

        self.rag_toggle = QCheckBox("RAG verwenden")

        # Toggle-Button für kollabierbare Details
        self._rag_details_button = QPushButton("▶ Dokumente verwalten")
        self._rag_details_button.setFlat(True)
        self._rag_details_button.setStyleSheet("text-align: left; font-weight: bold;")
        self._rag_details_button.clicked.connect(self._toggle_rag_details)

        # Kollabierter Container – standardmäßig versteckt
        self._rag_details_container = QWidget()
        details_layout = QVBoxLayout(self._rag_details_container)
        details_layout.setContentsMargins(0, 0, 0, 0)

        self.add_file_button = QPushButton("Datei hinzufügen")
        self.document_list = QListWidget()
        self.document_list.setToolTip("Indexierte Dokumente")
        self.delete_doc_button = QPushButton("Ausgewähltes entfernen")
        self.clear_store_button = QPushButton("Alles löschen")
        self.rag_status_label = QLabel("0 Dokumente indexiert")
        self.rag_status_label.setStyleSheet("color: #888888; font-size: 11px;")

        details_layout.addWidget(self.add_file_button)
        details_layout.addWidget(QLabel("Indexierte Dateien:"))
        details_layout.addWidget(self.document_list)
        details_layout.addWidget(self.delete_doc_button)
        details_layout.addWidget(self.clear_store_button)
        details_layout.addWidget(self.rag_status_label)

        self._rag_details_container.setVisible(False)

        rag_layout.addWidget(QLabel("<b>RAG-Wissensbasis</b>"))
        rag_layout.addWidget(self.rag_toggle)
        rag_layout.addWidget(self._rag_details_button)
        rag_layout.addWidget(self._rag_details_container)
        rag_layout.addStretch()

        # --- Splitter: Chat links, RAG-Panel rechts ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(chat_widget)
        splitter.addWidget(rag_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        # --- Haupt-Layout ---
        main_layout = QVBoxLayout()
        main_layout.addWidget(splitter)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

    def _toggle_rag_details(self):
        """Klappt den RAG-Detailbereich ein oder aus."""
        sichtbar = not self._rag_details_container.isVisible()
        self._rag_details_container.setVisible(sichtbar)
        self._rag_details_button.setText(
            "▼ Dokumente verwalten" if sichtbar else "▶ Dokumente verwalten"
        )

    def closeEvent(self, event):
        """Sendet das closing-Signal vor dem Schließen."""
        self.closing.emit()
        super().closeEvent(event)

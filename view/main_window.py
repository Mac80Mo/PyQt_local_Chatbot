from PyQt6.QtWidgets import (
    QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton,
    QComboBox, QLabel, QToolBar, QProgressBar, QSpinBox,
)


class MainWindow(QMainWindow):
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

        toolbar.addSeparator()

        toolbar.addWidget(QLabel("Kontext: "))
        self.num_ctx_spinner = QSpinBox()
        self.num_ctx_spinner.setRange(512, 131072)
        self.num_ctx_spinner.setSingleStep(512)
        self.num_ctx_spinner.setValue(4096)
        self.num_ctx_spinner.setSuffix(" Tokens")
        self.num_ctx_spinner.setMinimumWidth(130)
        toolbar.addWidget(self.num_ctx_spinner)

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

        # --- Kontext-Anzeige ---
        self.context_bar = QProgressBar()
        self.context_bar.setRange(0, 4096)
        self.context_bar.setValue(0)
        self.context_bar.setFormat("%v / %m Tokens")
        self.context_bar.setTextVisible(True)
        self.context_bar.setFixedHeight(16)

        # --- Haupt-Layout ---
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.chat_display)
        main_layout.addLayout(button_layout)
        main_layout.addWidget(self.context_bar)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

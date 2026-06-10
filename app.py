import sys

from PyQt6.QtWidgets import QApplication

from view.main_window import MainWindow
from controller.chat_controller import ChatController

app = QApplication(sys.argv)
window = MainWindow()
controller = ChatController(window, model_name="llama3.2:3b")
window.show()
app.exec()
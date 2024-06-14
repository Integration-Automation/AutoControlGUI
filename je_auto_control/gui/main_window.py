from PySide6.QtWidgets import QMainWindow

from je_auto_control.gui.main_widget import AutoControlWidget


class AutoControlGUI(QMainWindow):

    def __init__(self):
        super().__init__()
        self.central_widget = AutoControlWidget(self)
        self.setCentralWidget(self.central_widget)

import sys

from PySide6.QtWidgets import QApplication

from .controller.game_controller import GameController
from .ui.windows import MainWindow


def run(argv=None):
    argv = argv or sys.argv
    app = QApplication(argv)
    controller = GameController()
    win = MainWindow(controller=controller)
    win.show()
    return app.exec()
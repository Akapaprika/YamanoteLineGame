from PySide6.QtWidgets import QTextEdit, QVBoxLayout, QWidget


class NotificationView(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

    def show_notification(self, level: str, message: str):
        self.log.append(f"[{level}] {message}")
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)


class ControlPanel(QWidget):
    request_load_csv = Signal(str)
    request_start = Signal()
    request_stop = Signal()
    request_submit_answer = Signal(str)
    request_pass = Signal()

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)

        self.load_btn = QPushButton("Load CSV")
        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop")
        self.answer_in = QLineEdit()
        self.submit_btn = QPushButton("Submit")
        self.pass_btn = QPushButton("Pass")
        self.meta_label = QLabel("No CSV")

        layout.addWidget(self.load_btn)
        layout.addWidget(self.start_btn)
        layout.addWidget(self.stop_btn)
        layout.addWidget(self.meta_label)
        layout.addWidget(self.answer_in)
        layout.addWidget(self.submit_btn)
        layout.addWidget(self.pass_btn)

        self.load_btn.clicked.connect(self._on_load)
        self.start_btn.clicked.connect(lambda: self.request_start.emit())
        self.stop_btn.clicked.connect(lambda: self.request_stop.emit())
        self.submit_btn.clicked.connect(self._on_submit)
        self.pass_btn.clicked.connect(lambda: self.request_pass.emit())

    def _on_load(self):
        path, _ = QFileDialog.getOpenFileName(self, "CSV を選択", "", "CSV Files (*.csv);;All Files (*)")
        if path:
            self.request_load_csv.emit(path)

    def on_answer_list_loaded(self, meta: dict):
        total = meta.get("total", "?")
        self.meta_label.setText(f"Loaded: {total}")
        # ここでは表示だけ行う
    def _on_submit(self):
        text = self.answer_in.text().strip()
        if text:
            self.request_submit_answer.emit(text)
            self.answer_in.clear()
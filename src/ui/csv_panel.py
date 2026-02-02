import os
from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)


class CsvPanel(QWidget):
    """CSV file loader with sound and countdown toggles."""

    request_toggle_sound = Signal(bool)
    request_toggle_countdown = Signal(bool)

    def __init__(self, load_callback: Optional[Callable[[str], None]] = None):
        super().__init__()
        self.load_callback = load_callback
        self._current_path = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.load_btn = QPushButton("CSV読み込み")
        self.load_btn.setFixedWidth(88)
        layout.addWidget(self.load_btn)

        self.filename_label = QLabel("お題：未選択")
        self.filename_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.filename_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self.filename_label, 1)

        self.sound_checkbox = QCheckBox("効果音を有効にする")
        self.sound_checkbox.setChecked(False)
        self.sound_checkbox.toggled.connect(self.request_toggle_sound)
        layout.addWidget(self.sound_checkbox)

        self.countdown_checkbox = QCheckBox("秒読み音を有効にする")
        self.countdown_checkbox.setChecked(False)
        self.countdown_checkbox.toggled.connect(self.request_toggle_countdown)
        layout.addWidget(self.countdown_checkbox)

        self.load_btn.clicked.connect(self._on_clicked)

    def _on_clicked(self):
        if self.load_callback:
            self.load_callback()

    def set_path_after_load(self, path: str):
        if not path:
            self._current_path = None
            self.filename_label.setText("お題：未選択")
            return
        self._current_path = path
        stem = os.path.splitext(os.path.basename(path))[0]
        is_in_answer_list = os.path.basename(os.path.dirname(path)) == "answer_list"
        self.filename_label.setStyleSheet("" if is_in_answer_list else "color: orange;")
        self.filename_label.setText(f"お題：{stem}")

    def current_path(self) -> Optional[str]:
        return self._current_path
from typing import Iterable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class AnswerListPanel(QWidget):
    """Display remaining and answered lists side-by-side."""

    request_mark_answer = Signal(str)
    request_save_csv = Signal()
    request_toggle_typing_pause = Signal(bool)
    request_toggle_hide_remaining = Signal(bool)
    request_unmark_answer = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Store mapping of display index to original normalized key
        self._remaining_keys = []  # list of normalized display keys for remaining items
        self._answered_keys = []   # list of normalized display keys for answered items
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        # Top row: summary label, pause typing, hide remaining, save button
        summary_row = QHBoxLayout()
        self.summary_label = QLabel("")
        summary_row.addWidget(self.summary_label, 1)

        self.pause_on_typing_cb = QCheckBox("Pause typing")
        self.pause_on_typing_cb.setChecked(True)
        summary_row.addWidget(self.pause_on_typing_cb, 0)

        self.hide_remaining_cb = QCheckBox("未回答を非表示")
        # default OFF (show remaining)
        self.hide_remaining_cb.setChecked(False)
        summary_row.addWidget(self.hide_remaining_cb, 0)

        self.save_btn = QPushButton("Save CSV")
        summary_row.addWidget(self.save_btn, 0)

        outer.addLayout(summary_row)

        root = QHBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # Remaining
        left = QVBoxLayout()
        self.remaining_label = QLabel("未回答リスト")
        left.addWidget(self.remaining_label)
        self.remaining_list = QListWidget()
        self.remaining_list.setSelectionMode(QListWidget.NoSelection)
        self.remaining_list.setStyleSheet("QListWidget::item{height:14px;}")
        left.addWidget(self.remaining_list, 1)

        # Answered
        right = QVBoxLayout()
        right.addWidget(QLabel("回答済みリスト"))
        self.answered_list = QListWidget()
        self.answered_list.setSelectionMode(QListWidget.NoSelection)
        self.answered_list.setStyleSheet("QListWidget::item{height:14px;}")
        right.addWidget(self.answered_list, 1)

        root.addLayout(left, 1)
        root.addLayout(right, 1)
        outer.addLayout(root)

        # Connections
        self.remaining_list.itemDoubleClicked.connect(self._on_remaining_double_clicked)
        self.answered_list.itemDoubleClicked.connect(self._on_answered_double_clicked)
        self.save_btn.clicked.connect(self._on_save_csv)
        self.pause_on_typing_cb.toggled.connect(self._on_typing_pause_toggled)
        self.hide_remaining_cb.toggled.connect(self._on_hide_remaining_toggled)

    def on_answers_updated(self, remaining: Iterable[str], answered: Iterable[str]):
        """Update widgets with remaining and answered items.
        
        Note: remaining and answered are expected to be formatted strings
        ('display（match）' format). The actual normalized keys are stored
        separately by the caller (windows.py) via _remaining_keys and _answered_keys.
        """
        self.remaining_list.clear()
        self.answered_list.clear()
        rem_list = list(remaining)
        ans_list = list(answered)
        
        for it in rem_list:
            self.remaining_list.addItem(str(it))
        for it in ans_list:
            self.answered_list.addItem(str(it))
        rem = len(rem_list)
        ans = len(ans_list)
        total = rem + ans
        pct = (ans / total * 100) if total > 0 else 0.0
        self.summary_label.setText(f"Remaining: {rem} / Total: {total}  (Answered: {pct:.2f}% )")

    def _on_hide_remaining_toggled(self, checked: bool):
        # checked=True means hide remaining list
        self.request_toggle_hide_remaining.emit(checked)

    def _on_answered_double_clicked(self, item):
        if item:
            try:
                # Get the index of the clicked item in the answered_list
                index = self.answered_list.row(item)
                # Retrieve the original key from _answered_keys mapping
                if 0 <= index < len(self._answered_keys):
                    key = self._answered_keys[index]
                    self.request_unmark_answer.emit(key)
                else:
                    # Fallback if index is out of bounds
                    self.request_unmark_answer.emit(item.text())
            except Exception:
                pass

    def _on_remaining_double_clicked(self, item):
        if item:
            self.request_mark_answer.emit(item.text())

    def _on_save_csv(self):
        self.request_save_csv.emit()

    def _on_countdown_pause_toggled(self, checked):
        pass

    def _on_typing_pause_toggled(self, checked):
        self.request_toggle_typing_pause.emit(checked)


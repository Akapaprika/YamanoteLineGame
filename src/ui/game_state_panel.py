from typing import Callable, Optional

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QFont, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QCompleter,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class GameStatePanel(QWidget):
    """Current player and remaining time display with answer input and controls."""

    typing_event = Signal()
    composition_event = Signal(bool)

    def __init__(
        self,
        submit_callback: Callable[[str], None],
        start_callback: Optional[Callable[[], None]] = None,
        stop_callback: Optional[Callable[[], None]] = None,
        pass_callback: Optional[Callable[[], None]] = None,
        forfeit_callback: Optional[Callable[[], None]] = None,
        skip_callback: Optional[Callable[[], None]] = None,
    ):
        super().__init__()
        self.submit_callback = submit_callback
        self.start_callback = start_callback
        self.stop_callback = stop_callback
        self.pass_callback = pass_callback
        self.forfeit_callback = forfeit_callback
        self.skip_callback = skip_callback

        self._build_ui()
        self.current_player_name = None
        self._remaining_ms = None

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # Player and time row
        top_row = QHBoxLayout()
        self.player_label = QLabel("Current: —")
        pf = QFont()
        pf.setPointSize(14)
        pf.setBold(True)
        self.player_label.setFont(pf)
        top_row.addWidget(self.player_label, 1, Qt.AlignLeft)

        self.time_label = QLabel("--s")
        tf = QFont()
        tf.setPointSize(28)
        tf.setBold(True)
        self.time_label.setFont(tf)
        top_row.addWidget(self.time_label, 0, Qt.AlignRight)
        root.addLayout(top_row)

        # Answer input with completer
        ans_row = QHBoxLayout()
        self.answer_in = QLineEdit()
        self.answer_in.setPlaceholderText("回答を入力して Enter または Submit")
        self._completer_model = QStandardItemModel()
        self._completer = QCompleter(self._completer_model)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.setCompletionMode(QCompleter.PopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.popup().setStyleSheet("QListView::item{height:14px;}")
        self.answer_in.setCompleter(self._completer)
        self._remaining_items = []
        self._match_map = {}
        self.answer_in.installEventFilter(self)
        self.submit_btn = QPushButton("Submit")
        ans_row.addWidget(self.answer_in, 1)
        ans_row.addWidget(self.submit_btn)
        root.addLayout(ans_row)

        # Control buttons
        ctrl_row = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop")
        self.pass_btn = QPushButton("Pass")
        self.forfeit_btn = QPushButton("Forfeit")
        self.skip_btn = QPushButton("Skip")
        ctrl_row.addWidget(self.start_btn)
        ctrl_row.addWidget(self.stop_btn)
        ctrl_row.addWidget(self.pass_btn)
        ctrl_row.addWidget(self.forfeit_btn)
        ctrl_row.addWidget(self.skip_btn)
        root.addLayout(ctrl_row)

        # Connect signals
        self.submit_btn.clicked.connect(self._on_submit)
        self.answer_in.returnPressed.connect(self._on_submit)
        self.answer_in.textEdited.connect(self._on_answer_text_edited)
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        self.pass_btn.clicked.connect(self._on_pass)
        self.forfeit_btn.clicked.connect(self._on_forfeit)
        self.skip_btn.clicked.connect(self._on_skip)

    def set_current_player(self, name: Optional[str]):
        self.current_player_name = name
        self.player_label.setText(f"Current: {name if name else '—'}")
        if not name:
            self.time_label.setText("--s")

    def set_remaining_ms(self, ms: int):
        self._remaining_ms = ms
        seconds = max(0, int(ms // 1000))
        self.time_label.setText(f"{seconds}s")

    def set_controls_enabled(self, enabled: bool):
        # When enabled=True (before start), allow Start
        # When enabled=False (game running), disable Start, enable Stop/Pass
        self.start_btn.setEnabled(enabled)
        self.pass_btn.setEnabled(not enabled)
        self.stop_btn.setEnabled(not enabled)

    def update_answer_suggestions(self, remaining_items):
        """Update completer suggestions from remaining answers list.

        remaining_items: iterable of display strings. The caller may also
        set `self._match_map` (display -> normalized match string) so
        the live filter will match on match keys (hiragana) as well.
        """
        self._remaining_items = list(remaining_items)
        self._rebuild_completer_model(self._remaining_items)

    def _rebuild_completer_model(self, items):
        self._completer_model.clear()
        for item_text in items:
            # Format: "display（match）"
            display = str(item_text)
            match_str = self._match_map.get(item_text, "")
            if match_str:
                label = f"{display}（{match_str}）"
            else:
                label = display
            it = QStandardItem(label)
            # Store the matching string so clicking a suggestion inserts the match into the input
            it.setData(match_str if match_str else display, Qt.UserRole)
            self._completer_model.appendRow(it)
        try:
            # reconnect activated to ensure our handler runs when an item is clicked
            self._completer.activated.disconnect()
        except Exception:
            pass
        self._completer.activated.connect(self._on_completer_activated)

    def _on_answer_text_edited(self, text: str):
        """Filter completer suggestions on text change."""
        try:
            from ..utils.text_norm import normalize_text
            q = normalize_text(text)
            if not q:
                self._rebuild_completer_model(self._remaining_items)
                return
            filtered = []
            for disp in self._remaining_items:
                if q in normalize_text(str(disp)) or q in self._match_map.get(disp, ""):
                    filtered.append(disp)
            self._rebuild_completer_model(filtered)
        except Exception:
            pass

    def _on_submit(self):
        text = self.answer_in.text().strip()
        if not text:
            return
        try:
            # Send raw input text (matching string / 読み) to controller so AnswerList.contains works
            self.submit_callback(text)
        except Exception:
            pass
        self.answer_in.clear()
        self.answer_in.setFocus()

    def _on_completer_activated(self, text: str):
        """Insert matching string into the input when a completer item is clicked."""
        try:
            # Prefer to fetch the matching string stored in the model's UserRole.
            # Some platforms/Qt builds may pass the display text and the popup
            # currentIndex may not be valid, so we search the model rows for the
            # item whose label matches the activated text.
            match_val = None
            try:
                model = self._completer_model
                rows = model.rowCount()
                # 1) Exact label match
                for r in range(rows):
                    it = model.item(r)
                    if it is None:
                        continue
                    label = it.text()
                    if str(label) == str(text):
                        try:
                            val = it.data(Qt.UserRole)
                            if val is not None:
                                match_val = val
                                break
                        except Exception:
                            pass
                # 2) If not found, check if any item's UserRole equals the activated text
                if match_val is None:
                    for r in range(rows):
                        it = model.item(r)
                        if it is None:
                            continue
                        try:
                            val = it.data(Qt.UserRole)
                            if val == text:
                                match_val = val
                                break
                        except Exception:
                            pass
                # 3) If still not found, fuzzy match: label contains activated text or vice versa
                if match_val is None:
                    for r in range(rows):
                        it = model.item(r)
                        if it is None:
                            continue
                        label = it.text()
                        try:
                            if str(text) in str(label) or str(label) in str(text):
                                val = it.data(Qt.UserRole)
                                if val is not None:
                                    match_val = val
                                    break
                        except Exception:
                            pass
            except Exception:
                pass

            # Fallback: extract parenthesis content if present
            if match_val is None:
                import re
                m = re.search('（(.+?)）', str(text))
                match_val = m.group(1) if m else str(text)

            if match_val is None:
                match_val = str(text)

            self.answer_in.setText(str(match_val))
        except Exception:
            try:
                self.answer_in.setText(str(text))
            except Exception:
                pass

    def _on_start(self):
        if self.start_callback:
            try:
                self.start_callback()
            except Exception:
                pass

    def _on_stop(self):
        if self.stop_callback:
            try:
                self.stop_callback()
            except Exception:
                pass

    def _on_pass(self):
        if self.pass_callback:
            try:
                self.pass_callback()
            except Exception:
                pass

    def _on_forfeit(self):
        if self.forfeit_callback:
            try:
                self.forfeit_callback()
            except Exception:
                pass

    def _on_skip(self):
        if self.skip_callback:
            try:
                self.skip_callback()
            except Exception:
                pass

    def eventFilter(self, obj, ev):
        """Emit typing_event on KeyPress to pause countdown (IME-aware)."""
        if obj is self.answer_in:
            if ev.type() == QEvent.KeyPress:
                # Emit regardless of IME state to catch both direct input and before-confirmation input
                self.typing_event.emit()
            elif ev.type() == QEvent.InputMethod:
                # InputMethodEvent carries preedit (未確定文字). Emit composition_event(True) when
                # preedit exists, False when cleared.
                try:
                    pre = ev.preeditString()
                    self.composition_event.emit(bool(pre))
                except Exception:
                    # Some platforms may not expose preeditString; ignore if so
                    pass
        return super().eventFilter(obj, ev)
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class DragDropPlayerTable(QTableWidget):
    """Custom QTableWidget that handles row reordering without deleting source rows"""
    rowDropped = Signal(int, int)  # src_row, dest_row

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._drag_source_rows = []

    def dragMoveEvent(self, event):
        # Allow drops
        event.acceptProposedAction()

    def dropEvent(self, event):
        # Determine source and destination rows and emit a signal instead.
        # Use row rectangle center to decide whether insertion is before/after
        # the row under cursor so that dragging from above->below works.
        selected_rows = sorted(set(idx.row() for idx in self.selectedIndexes()))
        if not selected_rows:
            event.ignore()
            return

        src_row = selected_rows[0]
        pos = event.pos()
        row = self.rowAt(int(pos.y()))
        if row < 0:
            dest_row = self.rowCount()
        else:
            # compute item's vertical center
            item_rect = self.visualItemRect(self.item(row, 0))
            if pos.y() > (item_rect.top() + item_rect.height() / 2):
                dest_row = row + 1
            else:
                dest_row = row

        # Emit and accept; do NOT call base implementation to avoid
        # the widget removing the source row before the controller updates.
        self.rowDropped.emit(src_row, dest_row)
        event.accept()


class PlayerPanel(QWidget):
    request_add_player = Signal(str, int, int, int)  # name, base_seconds, pass_limit, wrong_answer_limit
    request_remove_player = Signal(str)              # player name
    request_reorder_players = Signal(list)           # new list of names in order
    request_move_player = Signal(str, int)           # player name, destination index
    request_forfeit = Signal(str)                    # player name
    request_skip = Signal(str)                       # player name

    def __init__(self):
        super().__init__()

        # safety: initialize flags/maps early
        self._controls_enabled = True
        self._name_to_row = {}
        self._row_player = {}
        self._drag_in_progress = False

        layout = QVBoxLayout(self)

        # input row
        add_row = QHBoxLayout()
        self.name_in = QLineEdit()
        self.name_in.setPlaceholderText("プレイヤー名を入力してEnter または add")
        self.base_time = QSpinBox(); self.base_time.setRange(1, 600); self.base_time.setValue(60)
        self.pass_limit = QSpinBox(); self.pass_limit.setRange(0, 100); self.pass_limit.setValue(0)  # default 0
        self.wrong_answer_limit = QSpinBox(); self.wrong_answer_limit.setRange(0, 100); self.wrong_answer_limit.setValue(5)  # default 5
        self.add_btn = QPushButton("Add")

        add_row.addWidget(QLabel("Name"))
        add_row.addWidget(self.name_in)
        add_row.addWidget(QLabel("Time"))
        add_row.addWidget(self.base_time)
        add_row.addWidget(QLabel("Pass"))
        add_row.addWidget(self.pass_limit)
        add_row.addWidget(QLabel("Wrong"))
        add_row.addWidget(self.wrong_answer_limit)
        add_row.addWidget(self.add_btn)

        layout.addLayout(add_row)

        # player table: Name | Thinking (max seconds) | Passes | Wrong
        self.table = DragDropPlayerTable(0, 4)
        self.table.setHorizontalHeaderLabels(["Name", "Thinking", "Pass", "Wrong"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setShowGrid(True)
        self.table.verticalHeader().setDefaultSectionSize(22)
        # limit maximum visible rows to avoid overflowing tall displays
        max_visible_rows = 6
        header_h = self.table.horizontalHeader().height() or 24
        self.table.setMaximumHeight(header_h + (self.table.verticalHeader().defaultSectionSize() * max_visible_rows) + 4)

        self.table.setColumnWidth(0, 220)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 100)
        layout.addWidget(self.table)

        # connections
        self.add_btn.clicked.connect(self._on_add)
        self.name_in.returnPressed.connect(self._on_add)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        # handle table drop -> move
        try:
            self.table.rowDropped.connect(self._on_row_dropped)
        except Exception:
            pass

        # drag defaults: disabled until controls enabled
        self._apply_drag_mode(enabled=False)

    # Public API
    def set_player_controls_enabled(self, enabled: bool) -> None:
        self._controls_enabled = bool(enabled)
        self.base_time.setEnabled(enabled)
        self.pass_limit.setEnabled(enabled)
        self.wrong_answer_limit.setEnabled(enabled)
        self._apply_drag_mode(enabled)

    def _apply_drag_mode(self, enabled: bool) -> None:
        if enabled:
            self.table.setDragEnabled(True)
            self.table.setAcceptDrops(True)
            # Use DragDrop with MoveAction (not InternalMove which has issues)
            self.table.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
            self.table.setDefaultDropAction(Qt.DropAction.MoveAction)
            self.table.viewport().setAcceptDrops(True)
        else:
            self.table.setDragEnabled(False)
            self.table.setAcceptDrops(False)
            self.table.setDragDropMode(QAbstractItemView.NoDragDrop)

    # Add / Remove / Update UI hooks
    def _on_add(self):
        name = self.name_in.text().strip()
        if not name:
            return
        base = int(self.base_time.value())
        passes = int(self.pass_limit.value())
        wrongs = int(self.wrong_answer_limit.value())
        self.request_add_player.emit(name, base, passes, wrongs)
        self.name_in.clear()
        self.name_in.setFocus()

    def _on_row_dropped(self, src_row: int, dest_row: int) -> None:
        # Called when the table reports a row drop. Notify controller who moved.
        item = self.table.item(src_row, 0)
        if item is None:
            return
        name = item.text()
        # Emit the move request: controller should reorder authoritative list
        self.request_move_player.emit(name, int(dest_row))

    def on_player_added(self, player):
        name = player.name
        if name in self._name_to_row:
            row = self._name_to_row[name]
        else:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._name_to_row[name] = row

        name_item = QTableWidgetItem(name)
        name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 0, name_item)

        # show the configured thinking time (max seconds) in the panel
        remaining_s = getattr(player, "base_seconds", "-")
        rem_item = QTableWidgetItem(f"{remaining_s}s")
        rem_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 1, rem_item)

        limit_pass = getattr(player, "pass_limit", "-")
        rem_pass = getattr(player, "remaining_passes", "-")
        pass_item = QTableWidgetItem(f"{rem_pass}/{limit_pass}")
        pass_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 2, pass_item)

        limit_wrong = getattr(player, "wrong_answer_limit", "-")
        rem_wrong = getattr(player, "remaining_wrong_answers", "-")
        wrong_item = QTableWidgetItem(f"{rem_wrong}/{limit_wrong}")
        wrong_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 3, wrong_item)

        self._row_player[row] = player
        self._apply_row_style(row, player)

    def on_player_state(self, player_name: str, remaining_ms: int, remaining_passes: int, remaining_wrong_answers: int, eliminated: bool):
        row = self._name_to_row.get(player_name)
        if row is None:
            return
        if self.table.item(row, 1) is None:
            self.table.setItem(row, 1, QTableWidgetItem())
        if self.table.item(row, 2) is None:
            self.table.setItem(row, 2, QTableWidgetItem())
        if self.table.item(row, 3) is None:
            self.table.setItem(row, 3, QTableWidgetItem())

        # always display the player's configured max thinking time (base_seconds)
        player = self._row_player.get(row)
        if player:
            self.table.item(row, 1).setText(f"{getattr(player,'base_seconds','-')}s")
        else:
            self.table.item(row, 1).setText("-s")
        # update pass/wrong columns as before
        limit_pass = getattr(player, "pass_limit", "-") if player else "-"
        self.table.item(row, 2).setText(f"{remaining_passes}/{limit_pass}")
        limit_wrong = getattr(player, "wrong_answer_limit", "-") if player else "-"
        self.table.item(row, 3).setText(f"{remaining_wrong_answers}/{limit_wrong}")
        if player:
            player.remaining_passes = remaining_passes
            player.remaining_wrong_answers = remaining_wrong_answers
            player.eliminated = eliminated
        self._apply_row_style(row, player or type("P", (), {"eliminated": eliminated}))

    def on_all_player_states(self, players):
        self.table.setRowCount(0)
        self._name_to_row.clear()
        self._row_player.clear()
        for p in players:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._name_to_row[p.name] = row
            self._row_player[row] = p
            name_item = QTableWidgetItem(p.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, name_item)
            rem_item = QTableWidgetItem(f"{getattr(p,'base_seconds','-')}s")
            rem_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 1, rem_item)
            pass_item = QTableWidgetItem(f"{getattr(p,'remaining_passes','-')}/{getattr(p,'pass_limit','-')}")
            pass_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, pass_item)
            wrong_item = QTableWidgetItem(f"{getattr(p,'remaining_wrong_answers','-')}/{getattr(p,'wrong_answer_limit','-')}")
            wrong_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 3, wrong_item)
            self._apply_row_style(row, p)

    def highlight_current_player(self, name: str):
        for row, player in list(self._row_player.items()):
            if player is None:
                continue
            if player.name == name:
                # current player: leave default theme
                for col in range(self.table.columnCount()):
                    item = self.table.item(row, col)
                    if item:
                        item.setData(Qt.ForegroundRole, None)
            elif getattr(player, "eliminated", False):
                self._set_row_foreground_color(row, QColor(0, 0, 0))  # black for eliminated
            else:
                for col in range(self.table.columnCount()):
                    item = self.table.item(row, col)
                    if item:
                        item.setData(Qt.ForegroundRole, None)

    def _apply_row_style(self, row: int, player):
        if player is None:
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item:
                    item.setData(Qt.ForegroundRole, None)
            return
        if getattr(player, "eliminated", False):
            self._set_row_foreground_color(row, QColor(0, 0, 0))
        else:
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item:
                    item.setData(Qt.ForegroundRole, None)

    def _set_row_foreground_color(self, row: int, color: QColor):
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item:
                item.setForeground(color)

    def _on_cell_double_clicked(self, row, col):
        if not self._controls_enabled:
            return
        item = self.table.item(row, 0)
        if not item:
            return
        name = item.text()
        if QMessageBox.question(self, "削除確認", f"プレイヤー「{name}」を削除しますか？") == QMessageBox.StandardButton.Yes:
            self.request_remove_player.emit(name)

    def remove_player_item(self, name: str):
        row = self._name_to_row.pop(name, None)
        if row is None:
            return
        self.table.removeRow(row)
        self._rebuild_mappings()

    def _rebuild_mappings(self):
        """
        Collect the displayed player names in the current table order and
        emit `request_reorder_players` to ask the controller to reorder
        the authoritative `players` list. Do NOT update internal mappings
        here — wait for the controller to call back into
        `on_all_player_states` with the updated player list, which will
        rebuild the table and internal maps.
        """
        names = []
        for r in range(self.table.rowCount()):
            n_item = self.table.item(r, 0)
            if n_item is not None:
                n = n_item.text().strip()
                if n:
                    names.append(n)

        if not names:
            return

        # Emit new ordering and let controller emit the authoritative list
        self.request_reorder_players.emit(names)

    def event(self, ev):
        if self._controls_enabled and ev.type() == QEvent.Drop:
            res = super().event(ev)
            # Rebuild mappings after drop to reflect new order
            self._rebuild_mappings()
            return res
        return super().event(ev)
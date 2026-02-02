import os
import time

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from ..config import (
    COUNTDOWN_SOUNDS,
    SOUND_CORRECT,
    SOUND_WRONG,
    get_sound_path,
    sound_exists,
)
from .answer_list_panel import AnswerListPanel
from .csv_panel import CsvPanel
from .game_state_panel import GameStatePanel
from .notification_view import NotificationView
from .player_panel import PlayerPanel


class MainWindow(QMainWindow):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowTitle("山手線ゲーム 主催者用")
        self.resize(1300, 680)
        central = QWidget()
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(6, 6, 6, 6)
        root_layout.setSpacing(6)

        left_col = QVBoxLayout()
        left_col.setSpacing(6)

        # CSV panel above PlayerPanel
        self.csv_panel = CsvPanel(load_callback=None)  # windows will handle QFileDialog -> set_path_after_load
        # wire load button to open dialog and call controller.load_csv
        def _open_dialog_and_load():
            # default folder: project/data/answer_list
            start_dir = os.path.join(os.getcwd(), "data", "answer_list")
            path, _ = QFileDialog.getOpenFileName(self, "Load CSV", start_dir, "CSV Files (*.csv);;All Files (*)")
            if path:
                # set label and call controller.load_csv
                self.csv_panel.set_path_after_load(path)
                if hasattr(self.controller, "load_csv"):
                    try:
                        self.controller.load_csv(path)
                    except Exception:
                        pass
        # assign a small wrapper as load_callback so CsvPanel._on_clicked will call it
        self.csv_panel.load_callback = _open_dialog_and_load

        left_col.addWidget(self.csv_panel)

        # PlayerPanel (top)
        self.player_panel = PlayerPanel()
        left_col.addWidget(self.player_panel, 0)

        # Game state panel (middle) - GameStatePanel now uses horizontal player/time
        # provide small wrappers to act on the current player for forfeit/skip
        def _forfeit_current():
            try:
                cur = self.controller.current_player()
                if cur and hasattr(self.controller, "forfeit_player"):
                    self.controller.forfeit_player(cur.name)
            except Exception:
                pass

        def _skip_current():
            try:
                cur = self.controller.current_player()
                if cur and hasattr(self.controller, "skip_player"):
                    self.controller.skip_player(cur.name)
            except Exception:
                pass

        # --- start: wrap start_callback to show reset dialog if answered list is not empty ---
        def _start_game_with_reset_check():
            # If remaining list is empty (all items answered), automatically reset answers
            try:
                al = getattr(self.controller, "answer_list", None)
            except Exception:
                al = None

            if al is None:
                # nothing loaded, just start as usual
                if hasattr(self.controller, "start_game"):
                    self.controller.start_game()
                return

            remaining = [i for i in al.items if i not in al.used]
            answered = [i for i in al.items if i in al.used]

            if len(remaining) == 0 and len(answered) > 0:
                # all items are answered -> force reset and start from beginning
                try:
                    al.used.clear()
                    if hasattr(self.controller, '_answered_order'):
                        self.controller._answered_order.clear()
                    if hasattr(self.controller, 'on_answers_updated'):
                        rem = [i for i in al.items if i not in al.used]
                        ans = []
                        self.controller.on_answers_updated(rem, ans)
                except Exception:
                    pass
                if hasattr(self.controller, "start_game"):
                    self.controller.start_game()
                return

            # If there are answered items but still some remaining, ask user whether to reset or continue
            if len(answered) > 0:
                from PySide6.QtWidgets import QMessageBox
                mb = QMessageBox(self)
                mb.setWindowTitle("開始方法の選択")
                mb.setText("回答済みリストが残っています。どの状態で開始しますか？")
                btn_restart = mb.addButton("初めから", QMessageBox.YesRole)
                mb.addButton("続きから", QMessageBox.NoRole)
                btn_cancel = mb.addButton("キャンセル", QMessageBox.RejectRole)
                mb.exec()
                clicked = mb.clickedButton()
                if clicked is btn_cancel:
                    return
                if clicked is btn_restart:
                    # reset answers and start
                    try:
                        al.used.clear()
                        if hasattr(self.controller, '_answered_order'):
                            self.controller._answered_order.clear()
                        if hasattr(self.controller, 'on_answers_updated'):
                            rem = [i for i in al.items if i not in al.used]
                            ans = []
                            self.controller.on_answers_updated(rem, ans)
                    except Exception:
                        pass
                    if hasattr(self.controller, "start_game"):
                        self.controller.start_game()
                    return
                # clicked is continue: fall through to start without reset
            # default: start game
            if hasattr(self.controller, "start_game"):
                self.controller.start_game()

        self.game_state = GameStatePanel(
            submit_callback=self.controller.host_submit_answer if hasattr(self.controller, "host_submit_answer") else (lambda t: None),
            start_callback=_start_game_with_reset_check,
            stop_callback=self.controller.stop_game if hasattr(self.controller, "stop_game") else None,
            pass_callback=self.controller.host_pass if hasattr(self.controller, "host_pass") else None,
            forfeit_callback=_forfeit_current,
            skip_callback=_skip_current,
        )
        gs_frame = QFrame()
        gs_frame.setFrameShape(QFrame.Panel)
        gs_frame.setFrameShadow(QFrame.Raised)
        gs_layout = QVBoxLayout(gs_frame)
        gs_layout.setContentsMargins(6,6,6,6)
        gs_layout.addWidget(self.game_state)
        left_col.addWidget(gs_frame, 0)

        # Notification/log (bottom)
        self.notification_view = NotificationView()
        self.notification_view.setFixedHeight(250)
        left_col.addWidget(self.notification_view, 0)

        left_widget = QWidget()
        left_widget.setLayout(left_col)

        # Right: two lists horizontally side-by-side (tall vertical lists)
        right_col = QHBoxLayout()
        right_col.setSpacing(10)

        # right side: answer lists widget (remaining / answered)
        # arrange vertically: lists above
        right_v = QVBoxLayout()
        right_v.setSpacing(6)
        self.answer_lists = AnswerListPanel()
        right_v.addWidget(self.answer_lists, 1)

        right_widget = QWidget()
        right_widget.setLayout(right_v)
        right_widget.setFixedWidth(650)

        root_layout.addWidget(left_widget, 3)
        root_layout.addWidget(right_widget, 2)

        self.setCentralWidget(central)

        # player_panel signals
        if hasattr(self.player_panel, "request_add_player"):
            self.player_panel.request_add_player.connect(self._on_add_player_from_panel)
        if hasattr(self.player_panel, "request_remove_player"):
            self.player_panel.request_remove_player.connect(self.controller.remove_player)
        if hasattr(self.player_panel, "request_reorder_players"):
            # prefer controller.reorder_players_by_name if it exists
            if hasattr(self.controller, "reorder_players_by_name"):
                    self.player_panel.request_reorder_players.connect(self.controller.reorder_players_by_name)
            else:
                # fallback: connect to a no-op or wrapper
                self.player_panel.request_reorder_players.connect(lambda order: None)
        if hasattr(self.player_panel, "request_move_player"):
            if hasattr(self.controller, "move_player"):
                self.player_panel.request_move_player.connect(self.controller.move_player)
            else:
                self.player_panel.request_move_player.connect(lambda name, idx: None)
        if hasattr(self.player_panel, "request_forfeit"):
            if hasattr(self.controller, "forfeit_player"):
                self.player_panel.request_forfeit.connect(self.controller.forfeit_player)
            else:
                self.player_panel.request_forfeit.connect(lambda name: None)
        if hasattr(self.player_panel, "request_skip"):
            if hasattr(self.controller, "skip_player"):
                self.player_panel.request_skip.connect(self.controller.skip_player)
            else:
                self.player_panel.request_skip.connect(lambda name: None)

        # controller -> UI callbacks
        if hasattr(self.controller, "register_notification"):
            self.controller.register_notification(self.notification_view.show_notification)
        if hasattr(self.controller, "register_player_added"):
            self.controller.register_player_added(self.player_panel.on_player_added)
        if hasattr(self.controller, "register_player_state"):
            self.controller.register_player_state(self._on_player_state)
        if hasattr(self.controller, "register_answer_list_loaded"):
            self.controller.register_answer_list_loaded(self._on_answer_list_loaded)
        # new: answers updated callback to update the AnswerListPanel and GameStatePanel completer
        def _on_answers_updated(remaining, answered):
            # format items for display: "display（match）"
            try:
                mm = getattr(self.controller.answer_list, '_match_map', {}) if getattr(self.controller, 'answer_list', None) is not None else {}
            except Exception:
                mm = {}
            formatted_rem = [f"{d}（{mm.get(d, '')}）" if mm.get(d) else str(d) for d in remaining]
            formatted_ans = [f"{d}（{mm.get(d, '')}）" if mm.get(d) else str(d) for d in answered]
            # Store raw keys in answer_lists BEFORE updating UI (so they're available when items are clicked)
            self.answer_lists._remaining_keys = list(remaining)
            self.answer_lists._answered_keys = list(answered)
            # update answer lists panel with formatted labels and preserve raw keys
            self.answer_lists.on_answers_updated(formatted_rem, formatted_ans)
            # update completer suggestions with raw keys (game_state expects raw display keys)
            if hasattr(self.game_state, "update_answer_suggestions"):
                try:
                    self.game_state._match_map = mm
                except Exception:
                    pass
                # When hide-remaining is enabled, do not provide suggestions to the completer
                try:
                    if getattr(self, '_hide_remaining', False):
                        # supply empty list to ensure popup/suggestions are suppressed
                        self.game_state.update_answer_suggestions([])
                    else:
                        self.game_state.update_answer_suggestions(list(remaining))
                except Exception:
                    pass
        if hasattr(self.controller, "register_answers_updated"):
            self.controller.register_answers_updated(_on_answers_updated)
        # connect double-click on remaining list to mark answer as correct, but only when game is running
        if hasattr(self.answer_lists, "request_mark_answer") and hasattr(self.controller, "host_submit_answer"):
            def _on_remaining_mark(text):
                try:
                    if not getattr(self.controller, 'is_running', False):
                        return
                    # text may be formatted as 'display（match）' — extract match if present
                    match_text = None
                    try:
                        if '（' in text and '）' in text:
                            start = text.rfind('（')
                            end = text.rfind('）')
                            match_text = text[start+1:end]
                        else:
                            # fallback: try to lookup match from answer_list
                            match_text = getattr(self.controller.answer_list, '_match_map', {}).get(text, text)
                    except Exception:
                        match_text = text
                    self.controller.host_submit_answer(match_text)
                except Exception:
                    pass
            self.answer_lists.request_mark_answer.connect(_on_remaining_mark)
        # connect double-click on answered list to move item back to remaining
        if hasattr(self.answer_lists, 'request_unmark_answer') and hasattr(self.controller, 'unmark_answer'):
            def _on_unmark_request(text):
                try:
                    # text is now the normalized display key directly from AnswerListPanel
                    # (no need to parse formatted text anymore)
                    if text:
                        self.controller.unmark_answer(text)
                except Exception:
                    pass
            self.answer_lists.request_unmark_answer.connect(_on_unmark_request)

        # sound toggle connection (CsvPanel emits request_toggle_sound)
        # Initialize _sound_enabled from the CSV panel checkbox (default OFF)
        try:
            self._sound_enabled = bool(self.csv_panel.sound_checkbox.isChecked())
        except Exception:
            self._sound_enabled = False
        if hasattr(self.csv_panel, 'request_toggle_sound'):
            try:
                self.csv_panel.request_toggle_sound.connect(lambda s: setattr(self, '_sound_enabled', bool(s)))
            except Exception:
                pass

        # Prepare cached media players to reduce playback latency for short sounds.
        # Map filename -> (QMediaPlayer, QAudioOutput)
        self._sound_players = {}

        def _play_sound_internal(filename, volume=0.9):
            try:
                if not getattr(self, '_sound_enabled', False):
                    return
                if not sound_exists(filename):
                    return
                fname = get_sound_path(filename)
                # Reuse a cached player when possible to avoid load latency
                pair = self._sound_players.get(filename)
                if pair is None:
                    player = QMediaPlayer(self)
                    audio = QAudioOutput(self)
                    audio.setVolume(float(volume))
                    player.setAudioOutput(audio)
                    player.setSource(QUrl.fromLocalFile(fname))
                    # keep in cache
                    self._sound_players[filename] = (player, audio)
                    pair = (player, audio)
                    # cleanup when finished (not removing cache, just avoid leak)
                    def _on_state_changed(state, player=player, filename=filename):
                        try:
                            from PySide6.QtMultimedia import QMediaPlayer

                            # If ended or stopped, ensure position reset so next play starts at beginning
                            if state == QMediaPlayer.StoppedState:
                                try:
                                    player.setPosition(0)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    try:
                        player.playbackStateChanged.connect(_on_state_changed)
                    except Exception:
                        pass
                else:
                    player, audio = pair
                    try:
                        audio.setVolume(float(volume))
                    except Exception:
                        pass
                player, audio = self._sound_players[filename]
                try:
                    # reset to start for immediate playback
                    player.setPosition(0)
                except Exception:
                    pass
                try:
                    player.play()
                except Exception:
                    pass
            except Exception:
                pass

        # expose helper as method-like attribute for internal use
        self._play_sound = _play_sound_internal

        # countdown toggle connection (initialize from UI checkbox)
        try:
            self._countdown_enabled = bool(self.csv_panel.countdown_checkbox.isChecked())
        except Exception:
            self._countdown_enabled = False
        if hasattr(self.csv_panel, 'request_toggle_countdown'):
            try:
                self.csv_panel.request_toggle_countdown.connect(lambda s: setattr(self, '_countdown_enabled', bool(s)))
            except Exception:
                pass
        # register for sound events from controller
        if hasattr(self.controller, 'register_sound_event'):
            try:
                self.controller.register_sound_event(self._on_sound_event)
            except Exception:
                pass

        # key-input pause state
        # When True, typing or IME composition will pause the countdown
        self._keypause_enabled = True
        self._keypause_until = 0.0
        self._last_countdown_second = None
        # IME composition flag
        self._is_composing = False
        # Track remaining_ms at turn start for 10-second beep detection
        # Format: {player_name: remaining_ms_at_start}
        self._player_remaining_at_turn_start = {}
        self.game_state.typing_event.connect(self._on_answer_typing)
        # pause_on_typing is provided by AnswerListPanel now
        # listen for IME composition changes from game state
        if hasattr(self.game_state, 'composition_event'):
            self.game_state.composition_event.connect(self._on_composition_changed)
        # New: connect save CSV button
        if hasattr(self.answer_lists, 'request_save_csv'):
            self.answer_lists.request_save_csv.connect(self._on_save_csv)
        # listen for hide-remaining toggle from AnswerListPanel
        if hasattr(self.answer_lists, 'request_toggle_hide_remaining'):
            self.answer_lists.request_toggle_hide_remaining.connect(self._on_hide_remaining_toggled)
        # track hide-remaining state so we can suppress completer suggestions when enabled
        self._hide_remaining = False
        # New: connect typing pause checkbox from answer list panel
        if hasattr(self.answer_lists, 'request_toggle_typing_pause'):
            self.answer_lists.request_toggle_typing_pause.connect(lambda v: setattr(self, '_keypause_enabled', v))
        self.controller.register_player_state(self._on_player_state)
        self.controller.register_game_ended(lambda reason: self.notification_view.show_notification("info", f"ゲーム終了: {reason}"))
        self.controller.register_all_players(self.player_panel.on_all_player_states)
        # Combine all current_player callbacks into one handler
        def _on_current_player_changed(player_name):
            # Update player panel highlighting
            if hasattr(self.player_panel, 'highlight_current_player'):
                try:
                    self.player_panel.highlight_current_player(player_name)
                except Exception:
                    pass
            # Update game state panel
            if hasattr(self.game_state, 'set_current_player'):
                try:
                    self.game_state.set_current_player(player_name)
                except Exception:
                    pass
            # Reset countdown turn state when player changes
            try:
                self._player_remaining_at_turn_start.clear()
                # clear per-player announcement flags
                keys_to_clear = [k for k in vars(self).keys() if k.startswith('_last_announced_intervals_') or k.startswith('_announced_timeout_')]
                for k in keys_to_clear:
                    delattr(self, k)
            except Exception:
                pass
        self.controller.register_current_player(_on_current_player_changed)
        self.controller.register_running_state(self._on_running_state_changed)

        # initial states
        self.player_panel.set_player_controls_enabled(True)
        self.game_state.set_controls_enabled(not self.controller.is_running)
        # initialize keypause flag from UI checkbox default
        try:
            self._keypause_enabled = bool(self.answer_lists.pause_on_typing_cb.isChecked())
        except Exception:
            pass

        # periodic UI refresh
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(200)
        self._refresh_timer.timeout.connect(self._on_tick_refresh)
        self._refresh_timer.start()

    def _on_add_player_from_panel(self, name: str, base_seconds: int, pass_limit: int, wrong_answer_limit: int):
        self.controller.add_player(name, base_seconds, pass_limit, wrong_answer_limit)

    def _on_answer_typing(self):
        now = time.monotonic()
        self._keypause_until = now + 1.0
        self.controller._last_tick_monotonic = now

    def _on_composition_changed(self, composing: bool):
        """Handle IME composition start/end.
        When composition state changes we flag `_is_composing` and reset
        controller._last_tick_monotonic so that paused duration isn't counted
        when ticking resumes (prevents time jump).
        """
        import time
        self._is_composing = bool(composing)
        try:
            # reset controller tick base so elapsed during composition isn't applied
            self.controller._last_tick_monotonic = time.monotonic()
        except Exception:
            pass

    def _on_hide_remaining_toggled(self, hide: bool):
        """Hide or show the remaining list in the AnswerListPanel."""
        try:
            visible = not bool(hide)
            self._hide_remaining = bool(hide)
            if hasattr(self.answer_lists, 'remaining_list'):
                self.answer_lists.remaining_list.setVisible(visible)
            if hasattr(self.answer_lists, 'remaining_label'):
                self.answer_lists.remaining_label.setVisible(visible)
            # Refresh completer suggestions when unhidden
            if not hide and hasattr(self.game_state, 'update_answer_suggestions'):
                try:
                    al = getattr(self.controller, 'answer_list', None)
                    if al is not None:
                        remaining = [i for i in al.items if i not in al.used]
                        self.game_state.update_answer_suggestions(list(remaining))
                except Exception:
                    pass
        except Exception:
            pass

    def _on_sound_event(self, kind: str):
        # kind is 'correct' or 'wrong'
        if not getattr(self, '_sound_enabled', False):
            return
        # Determine which config constant to use
        sound_file = SOUND_CORRECT if kind == 'correct' else SOUND_WRONG
        if not sound_exists(sound_file):
            return
        self._play_sound(sound_file, volume=0.9)

    def _on_player_state(self, player_name: str, remaining_ms: int, remaining_passes: int, remaining_wrong_answers: int, eliminated: bool):
        if hasattr(self.player_panel, "on_player_state"):
            self.player_panel.on_player_state(player_name, remaining_ms, remaining_passes, remaining_wrong_answers, eliminated)
        # update big time display when the reported player is the current one
        try:
            cur = self.controller.current_player()
        except Exception:
            cur = None
        if cur and player_name == cur.name:
            try:
                self.game_state.set_remaining_ms(remaining_ms)
            except Exception:
                pass
            # handle countdown beeps when enabled
            try:
                if getattr(self, '_countdown_enabled', False):
                    # remaining seconds (ceiling)
                    sec = int((remaining_ms + 999) // 1000)
                    # only act when second changed to avoid repeated beeps within same second
                    if sec != getattr(self, '_last_countdown_second', None):
                        self._last_countdown_second = sec
                        # when time reaches 0 use 'timeout' key
                        if sec == 0:
                            sound_file = COUNTDOWN_SOUNDS.get('timeout')
                        else:
                            sound_file = COUNTDOWN_SOUNDS.get(sec)

                        if sound_file and sound_exists(sound_file):
                            # play configured sound (volume tuned slightly lower for countdown)
                            self._play_sound(sound_file, volume=0.8)
            except Exception:
                pass

    def _on_answer_list_loaded(self, meta: dict):
        # legacy hook: leave behavior to register_answers_updated if available
        # otherwise reuse the existing controller.answer_list content
        al = getattr(self.controller, "answer_list", None)
        if al is None:
            return
        remaining = [i for i in al.items if i not in al.used]
        answered = [i for i in al.items if i in al.used]
        # format for display
        try:
            mm = getattr(self.controller.answer_list, '_match_map', {})
        except Exception:
            mm = {}
        formatted_rem = [f"{d}（{mm.get(d, '')}）" if mm.get(d) else str(d) for d in remaining]
        formatted_ans = [f"{d}（{mm.get(d, '')}）" if mm.get(d) else str(d) for d in answered]
        # update UI
        try:
            self.answer_lists.on_answers_updated(formatted_rem, formatted_ans)
        except Exception:
            pass

    def _on_running_state_changed(self, is_running: bool):
        if hasattr(self.player_panel, "set_player_controls_enabled"):
            self.player_panel.set_player_controls_enabled(not is_running)
        if hasattr(self.game_state, "set_controls_enabled"):
            # During game: disable start button, enable stop/pass
            self.game_state.set_controls_enabled(not is_running)
        # reset turn state when game stops
        if not is_running:
            self._player_remaining_at_turn_start.clear()

    def _on_tick_refresh(self):
        # First, advance controller time if running
        try:
            if hasattr(self.controller, "tick"):
                # if key-input pause enabled and either IME composition is active or
                # last keypress is within the pause window, skip ticking but reset
                # controller._last_tick_monotonic so elapsed doesn't accumulate
                now = time.monotonic()
                if getattr(self, '_keypause_enabled', False) and (getattr(self, '_is_composing', False) or now < getattr(self, '_keypause_until', 0)):
                    try:
                        self.controller._last_tick_monotonic = now
                    except Exception:
                        pass
                    return
                self.controller.tick()
        except Exception:
            pass
        # current player updates (name/time) are emitted via register_current_player
        # and register_player_state callbacks; nothing else needed here.

    # manual countdown pause removed; pause is controlled by typing/IME only

    def _on_save_csv(self):
        """Save current answer state to CSV with timestamp replacement."""
        try:
            import re
            from datetime import datetime
            al = getattr(self.controller, "answer_list", None)
            if al is None:
                self.notification_view.show_notification("error", "回答リストが読み込まれていません")
                return
            
            # Get answer list title from controller or use default
            title = getattr(self.controller, '_answer_list_title', 'answers')
            
            # Create output filename with current timestamp
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

            # Default save directory: data/answer_list
            save_dir = os.path.join(os.getcwd(), "data", "answer_list")
            os.makedirs(save_dir, exist_ok=True)

            # If the provided title already ends with a timestamp suffix, strip it
            # so we don't accumulate multiple timestamps in the name.
            base_title = re.sub(r'_\d{14}$', '', title)
            output_filename = f"{base_title}_{timestamp}.csv"
            
            output_path = os.path.join(save_dir, output_filename)
            
            # Save to CSV (silently overwrites if file exists)
            al.save_to_csv(output_path)
            self.notification_view.show_notification("info", f"CSV保存: {output_filename}")
        except Exception as e:
            self.notification_view.show_notification("error", f"CSV保存失敗: {str(e)}")
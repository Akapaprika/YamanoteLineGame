import os
import time
from functools import lru_cache

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
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
from ..utils.logger import get_logger
from .answer_list_panel import AnswerListPanel
from .csv_panel import CsvPanel
from .game_state_panel import GameStatePanel
from .notification_view import NotificationView
from .player_panel import PlayerPanel

logger = get_logger('windows')


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
        self.csv_panel = CsvPanel(load_callback=None)
        # wire load button to open dialog and call controller.load_csv
        def _open_dialog_and_load():
            start_dir = os.path.join(os.getcwd(), "data", "answer_list")
            path, _ = QFileDialog.getOpenFileName(self, "Load CSV", start_dir, "CSV Files (*.csv);;All Files (*)")
            if path:
                self.csv_panel.set_path_after_load(path)
                try:
                    if hasattr(self.controller, "load_csv"):
                        self.controller.load_csv(path)
                except Exception as e:
                    logger.error(f"Failed to load CSV: {e}", exc_info=True)
        
        self.csv_panel.load_callback = _open_dialog_and_load
        left_col.addWidget(self.csv_panel)

        # PlayerPanel (top)
        self.player_panel = PlayerPanel()
        left_col.addWidget(self.player_panel, 0)

        # Game state panel (middle)
        def _forfeit_current():
            try:
                cur = self.controller.current_player()
                if cur and hasattr(self.controller, "forfeit_player"):
                    self.controller.forfeit_player(cur.name)
            except Exception as e:
                logger.error(f"Error forfeiting player: {e}", exc_info=True)

        def _skip_current():
            try:
                cur = self.controller.current_player()
                if cur and hasattr(self.controller, "skip_player"):
                    self.controller.skip_player(cur.name)
            except Exception as e:
                logger.error(f"Error skipping player: {e}", exc_info=True)

        def _start_game_with_reset_check():
            """Start game with optional reset of answered items."""
            try:
                al = getattr(self.controller, "answer_list", None)
            except Exception as e:
                logger.error(f"Error getting answer_list: {e}", exc_info=True)
                al = None

            if al is None:
                if hasattr(self.controller, "start_game"):
                    self.controller.start_game()
                return

            remaining = [i for i in al.items if i not in al.used]
            answered = [i for i in al.items if i in al.used]

            if len(remaining) == 0 and len(answered) > 0:
                # all items are answered -> force reset and start from beginning
                try:
                    if hasattr(self.controller, "reset_answers"):
                        self.controller.reset_answers()
                except Exception as e:
                    logger.error(f"Error resetting answers: {e}", exc_info=True)
                if hasattr(self.controller, "start_game"):
                    self.controller.start_game()
                return

            # If there are answered items but still some remaining, ask user
            if len(answered) > 0:
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
                    try:
                        if hasattr(self.controller, "reset_answers"):
                            self.controller.reset_answers()
                    except Exception as e:
                        logger.error(f"Error resetting answers: {e}", exc_info=True)
                    if hasattr(self.controller, "start_game"):
                        self.controller.start_game()
                    return
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
        gs_layout.setContentsMargins(6, 6, 6, 6)
        gs_layout.addWidget(self.game_state)
        left_col.addWidget(gs_frame, 0)

        # Notification/log (bottom)
        self.notification_view = NotificationView()
        self.notification_view.setFixedHeight(250)
        left_col.addWidget(self.notification_view, 0)

        left_widget = QWidget()
        left_widget.setLayout(left_col)

        # Right: answer lists
        right_col = QHBoxLayout()
        right_col.setSpacing(10)
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

        # Register UI callbacks
        self._register_player_panel_callbacks()
        self._register_controller_callbacks()
        self._setup_sound_system()
        self._setup_timing_controls()

        # initial states
        self.player_panel.set_player_controls_enabled(True)
        self.game_state.set_controls_enabled(not self.controller.is_running)

        # periodic UI refresh
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(200)
        self._refresh_timer.timeout.connect(self._on_tick_refresh)
        self._refresh_timer.start()

    def _register_player_panel_callbacks(self) -> None:
        """Register all player panel signal callbacks."""
        try:
            if hasattr(self.player_panel, "request_add_player"):
                self.player_panel.request_add_player.connect(self._on_add_player_from_panel)
            if hasattr(self.player_panel, "request_remove_player"):
                self.player_panel.request_remove_player.connect(self.controller.remove_player)
            if hasattr(self.player_panel, "request_reorder_players"):
                if hasattr(self.controller, "reorder_players_by_name"):
                    self.player_panel.request_reorder_players.connect(self.controller.reorder_players_by_name)
            if hasattr(self.player_panel, "request_move_player"):
                if hasattr(self.controller, "move_player"):
                    self.player_panel.request_move_player.connect(self.controller.move_player)
            if hasattr(self.player_panel, "request_forfeit"):
                if hasattr(self.controller, "forfeit_player"):
                    self.player_panel.request_forfeit.connect(self.controller.forfeit_player)
            if hasattr(self.player_panel, "request_skip"):
                if hasattr(self.controller, "skip_player"):
                    self.player_panel.request_skip.connect(self.controller.skip_player)
        except Exception as e:
            logger.error(f"Error registering player panel callbacks: {e}", exc_info=True)

    def _register_controller_callbacks(self) -> None:
        """Register all controller signal callbacks."""
        try:
            if hasattr(self.controller, "register_notification"):
                self.controller.register_notification(self.notification_view.show_notification)
            if hasattr(self.controller, "register_player_added"):
                self.controller.register_player_added(self.player_panel.on_player_added)
            if hasattr(self.controller, "register_player_state"):
                self.controller.register_player_state(self._on_player_state)
            if hasattr(self.controller, "register_answer_list_loaded"):
                self.controller.register_answer_list_loaded(self._on_answer_list_loaded)
            if hasattr(self.controller, "register_answers_updated"):
                self.controller.register_answers_updated(self._on_answers_updated)
            if hasattr(self.controller, "register_sound_event"):
                self.controller.register_sound_event(self._on_sound_event)
            if hasattr(self.controller, "register_all_players"):
                self.controller.register_all_players(self.player_panel.on_all_player_states)
            if hasattr(self.controller, "register_current_player"):
                self.controller.register_current_player(self._on_current_player_changed)
            if hasattr(self.controller, "register_running_state"):
                self.controller.register_running_state(self._on_running_state_changed)
            if hasattr(self.controller, "register_game_ended"):
                self.controller.register_game_ended(
                    lambda reason: self.notification_view.show_notification("info", f"ゲーム終了: {reason}")
                )
        except Exception as e:
            logger.error(f"Error registering controller callbacks: {e}", exc_info=True)

    def _register_answer_list_callbacks(self) -> None:
        """Register answer list panel callbacks."""
        try:
            if hasattr(self.answer_lists, "request_mark_answer") and hasattr(self.controller, "host_submit_answer"):
                self.answer_lists.request_mark_answer.connect(self._on_remaining_mark)
            if hasattr(self.answer_lists, "request_unmark_answer") and hasattr(self.controller, "unmark_answer"):
                self.answer_lists.request_unmark_answer.connect(self._on_unmark_request)
            if hasattr(self.answer_lists, "request_save_csv"):
                self.answer_lists.request_save_csv.connect(self._on_save_csv)
            if hasattr(self.answer_lists, "request_toggle_hide_remaining"):
                self.answer_lists.request_toggle_hide_remaining.connect(self._on_hide_remaining_toggled)
            if hasattr(self.answer_lists, "request_toggle_typing_pause"):
                self.answer_lists.request_toggle_typing_pause.connect(lambda v: setattr(self, '_keypause_enabled', v))
        except Exception as e:
            logger.error(f"Error registering answer list callbacks: {e}", exc_info=True)

    def _setup_sound_system(self) -> None:
        """Initialize sound system and media players."""
        try:
            self._sound_enabled = bool(self.csv_panel.sound_checkbox.isChecked())
        except Exception:
            self._sound_enabled = False
        
        try:
            self._countdown_enabled = bool(self.csv_panel.countdown_checkbox.isChecked())
        except Exception:
            self._countdown_enabled = False
        
        # Sound toggle connections
        if hasattr(self.csv_panel, 'request_toggle_sound'):
            try:
                self.csv_panel.request_toggle_sound.connect(lambda s: setattr(self, '_sound_enabled', bool(s)))
            except Exception as e:
                logger.error(f"Error connecting sound toggle: {e}")
        
        if hasattr(self.csv_panel, 'request_toggle_countdown'):
            try:
                self.csv_panel.request_toggle_countdown.connect(lambda s: setattr(self, '_countdown_enabled', bool(s)))
            except Exception as e:
                logger.error(f"Error connecting countdown toggle: {e}")
        
        # Cached media players
        self._sound_players = {}
        self._sound_player_cache_max = 10  # Limit cache size

    def _setup_timing_controls(self) -> None:
        """Initialize timing and pause controls."""
        self._keypause_enabled = True
        self._keypause_until = 0.0
        self._last_countdown_second = None
        self._is_composing = False
        self._player_remaining_at_turn_start = {}
        self._hide_remaining = False
        
        try:
            if hasattr(self.game_state, 'typing_event'):
                self.game_state.typing_event.connect(self._on_answer_typing)
            if hasattr(self.game_state, 'composition_event'):
                self.game_state.composition_event.connect(self._on_composition_changed)
        except Exception as e:
            logger.error(f"Error setting up timing controls: {e}", exc_info=True)
        
        # Register answer list callbacks after setup
        self._register_answer_list_callbacks()
        
        try:
            self._keypause_enabled = bool(self.answer_lists.pause_on_typing_cb.isChecked())
        except Exception:
            pass

    def _on_add_player_from_panel(self, name: str, base_seconds: int, pass_limit: int, wrong_answer_limit: int):
        try:
            self.controller.add_player(name, base_seconds, pass_limit, wrong_answer_limit)
        except Exception as e:
            logger.error(f"Error adding player: {e}", exc_info=True)

    def _on_answer_typing(self):
        try:
            now = time.monotonic()
            self._keypause_until = now + 1.0
            self.controller._last_tick_monotonic = now
        except Exception as e:
            logger.error(f"Error handling answer typing: {e}", exc_info=True)

    def _on_composition_changed(self, composing: bool):
        """Handle IME composition start/end."""
        try:
            self._is_composing = bool(composing)
            self.controller._last_tick_monotonic = time.monotonic()
        except Exception as e:
            logger.error(f"Error handling composition change: {e}", exc_info=True)

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
                al = getattr(self.controller, 'answer_list', None)
                if al is not None:
                    remaining = [i for i in al.items if i not in al.used]
                    self.game_state.update_answer_suggestions(list(remaining))
        except Exception as e:
            logger.error(f"Error toggling hide remaining: {e}", exc_info=True)

    def _on_sound_event(self, kind: str):
        """Handle sound events from controller."""
        if not getattr(self, '_sound_enabled', False):
            return
        try:
            sound_file = SOUND_CORRECT if kind == 'correct' else SOUND_WRONG
            if sound_exists(sound_file):
                self._play_sound(sound_file, volume=0.9)
        except Exception as e:
            logger.error(f"Error playing sound event: {e}", exc_info=True)

    def _play_sound(self, filename: str, volume: float = 0.9) -> None:
        """Play a sound file with caching to reduce latency."""
        try:
            if not getattr(self, '_sound_enabled', False):
                return
            if not sound_exists(filename):
                return
            
            fname = get_sound_path(filename)
            # Reuse cached player or create new one
            pair = self._sound_players.get(filename)
            if pair is None:
                if len(self._sound_players) >= self._sound_player_cache_max:
                    # Remove oldest cached player
                    oldest_key = next(iter(self._sound_players))
                    del self._sound_players[oldest_key]
                
                player = QMediaPlayer(self)
                audio = QAudioOutput(self)
                audio.setVolume(float(volume))
                player.setAudioOutput(audio)
                player.setSource(QUrl.fromLocalFile(fname))
                self._sound_players[filename] = (player, audio)
                pair = (player, audio)
                
                def _on_state_changed(state, player=player):
                    try:
                        if state == QMediaPlayer.StoppedState:
                            player.setPosition(0)
                    except Exception as e:
                        logger.debug(f"Error resetting player position: {e}")
                
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
            
            player, _ = self._sound_players[filename]
            try:
                player.setPosition(0)
                player.play()
            except Exception as e:
                logger.error(f"Error playing sound: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error in _play_sound: {e}", exc_info=True)

    def _on_player_state(self, player_name: str, remaining_ms: int, remaining_passes: int, remaining_wrong_answers: int, eliminated: bool):
        try:
            if hasattr(self.player_panel, "on_player_state"):
                self.player_panel.on_player_state(player_name, remaining_ms, remaining_passes, remaining_wrong_answers, eliminated)
            
            cur = self.controller.current_player()
            if cur and player_name == cur.name:
                try:
                    self.game_state.set_remaining_ms(remaining_ms)
                except Exception:
                    pass
                
                # Handle countdown beeps
                if getattr(self, '_countdown_enabled', False):
                    sec = int((remaining_ms + 999) // 1000)
                    if sec != getattr(self, '_last_countdown_second', None):
                        self._last_countdown_second = sec
                        sound_file = COUNTDOWN_SOUNDS.get('timeout') if sec == 0 else COUNTDOWN_SOUNDS.get(sec)
                        if sound_file and sound_exists(sound_file):
                            self._play_sound(sound_file, volume=0.8)
        except Exception as e:
            logger.error(f"Error handling player state: {e}", exc_info=True)

    def _on_answers_updated(self, remaining, answered):
        """Update answer lists and completer when answers change."""
        try:
            mm = {}
            al = getattr(self.controller, 'answer_list', None)
            if al is not None:
                mm = getattr(al, '_match_map', {})
            
            formatted_rem = [f"{d}（{mm.get(d, '')}）" if mm.get(d) else str(d) for d in remaining]
            formatted_ans = [f"{d}（{mm.get(d, '')}）" if mm.get(d) else str(d) for d in answered]
            
            self.answer_lists._remaining_keys = list(remaining)
            self.answer_lists._answered_keys = list(answered)
            self.answer_lists.on_answers_updated(formatted_rem, formatted_ans)
            
            if hasattr(self.game_state, "update_answer_suggestions"):
                try:
                    self.game_state._match_map = mm
                    if getattr(self, '_hide_remaining', False):
                        self.game_state.update_answer_suggestions([])
                    else:
                        self.game_state.update_answer_suggestions(list(remaining))
                except Exception as e:
                    logger.debug(f"Error updating answer suggestions: {e}")
        except Exception as e:
            logger.error(f"Error in _on_answers_updated: {e}", exc_info=True)

    def _on_remaining_mark(self, text: str):
        """Mark a remaining answer as correct (double-click handler)."""
        try:
            if not getattr(self.controller, 'is_running', False):
                return
            match_text = text
            try:
                if '（' in text and '）' in text:
                    start = text.rfind('（')
                    end = text.rfind('）')
                    match_text = text[start+1:end]
                else:
                    mm = getattr(self.controller.answer_list, '_match_map', {})
                    match_text = mm.get(text, text)
            except Exception:
                pass
            self.controller.host_submit_answer(match_text)
        except Exception as e:
            logger.error(f"Error marking answer: {e}", exc_info=True)

    def _on_unmark_request(self, text: str):
        """Move an answered item back to remaining."""
        try:
            if text:
                self.controller.unmark_answer(text)
        except Exception as e:
            logger.error(f"Error unmarking answer: {e}", exc_info=True)

    def _on_answer_list_loaded(self, meta: dict):
        """Handle answer list loading."""
        try:
            al = getattr(self.controller, "answer_list", None)
            if al is None:
                return
            remaining = [i for i in al.items if i not in al.used]
            answered = [i for i in al.items if i in al.used]
            mm = getattr(al, '_match_map', {})
            formatted_rem = [f"{d}（{mm.get(d, '')}）" if mm.get(d) else str(d) for d in remaining]
            formatted_ans = [f"{d}（{mm.get(d, '')}）" if mm.get(d) else str(d) for d in answered]
            self.answer_lists.on_answers_updated(formatted_rem, formatted_ans)
        except Exception as e:
            logger.error(f"Error in _on_answer_list_loaded: {e}", exc_info=True)

    def _on_running_state_changed(self, is_running: bool):
        """Update UI when game running state changes."""
        try:
            if hasattr(self.player_panel, "set_player_controls_enabled"):
                self.player_panel.set_player_controls_enabled(not is_running)
            if hasattr(self.game_state, "set_controls_enabled"):
                self.game_state.set_controls_enabled(not is_running)
            if not is_running:
                self._player_remaining_at_turn_start.clear()
        except Exception as e:
            logger.error(f"Error handling running state change: {e}", exc_info=True)

    def _on_current_player_changed(self, player_name):
        """Update UI when current player changes."""
        try:
            if hasattr(self.player_panel, 'highlight_current_player'):
                self.player_panel.highlight_current_player(player_name)
            if hasattr(self.game_state, 'set_current_player'):
                self.game_state.set_current_player(player_name)
            self._player_remaining_at_turn_start.clear()
            keys_to_clear = [k for k in vars(self).keys() if k.startswith('_last_announced_intervals_') or k.startswith('_announced_timeout_')]
            for k in keys_to_clear:
                delattr(self, k)
        except Exception as e:
            logger.error(f"Error handling current player change: {e}", exc_info=True)

    def _on_tick_refresh(self):
        """Periodic UI refresh and controller tick."""
        try:
            if hasattr(self.controller, "tick"):
                now = time.monotonic()
                if getattr(self, '_keypause_enabled', False) and (getattr(self, '_is_composing', False) or now < getattr(self, '_keypause_until', 0)):
                    try:
                        self.controller._last_tick_monotonic = now
                    except Exception:
                        pass
                    return
                self.controller.tick()
        except Exception as e:
            logger.error(f"Error in tick refresh: {e}", exc_info=True)

    def _on_save_csv(self):
        """Save current answer state to CSV with timestamp."""
        try:
            import re
            from datetime import datetime
            al = getattr(self.controller, "answer_list", None)
            if al is None:
                self.notification_view.show_notification("error", "回答リストが読み込まれていません")
                return
            
            title = getattr(self.controller, '_answer_list_title', 'answers')
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            save_dir = os.path.join(os.getcwd(), "data", "answer_list")
            os.makedirs(save_dir, exist_ok=True)
            
            base_title = re.sub(r'_\d{14}$', '', title)
            output_filename = f"{base_title}_{timestamp}.csv"
            output_path = os.path.join(save_dir, output_filename)
            
            al.save_to_csv(output_path)
            self.notification_view.show_notification("info", f"CSV保存: {output_filename}")
        except FileNotFoundError as e:
            logger.error(f"Save directory not found: {e}", exc_info=True)
            self.notification_view.show_notification("error", f"CSV保存失敗: ディレクトリが見つかりません")
        except IOError as e:
            logger.error(f"IO error saving CSV: {e}", exc_info=True)
            self.notification_view.show_notification("error", f"CSV保存失敗: ファイル書き込みエラー")
        except Exception as e:
            logger.error(f"Error saving CSV: {e}", exc_info=True)
            self.notification_view.show_notification("error", f"CSV保存失敗: {str(e)}")

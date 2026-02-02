import time
import uuid
from typing import Callable, Iterable, List, Optional

from ..model.answer_list import AnswerList
from ..model.player import Player
from ..utils.text_norm import normalize_text

# callback types
NotificationCB = Callable[[str, str], None]
PlayerAddedCB = Callable[[Player], None]
PlayerStateCB = Callable[[str, int, int, int, bool], None]  # name, remaining_ms, remaining_passes, remaining_wrong_answers, eliminated
GameEndedCB = Callable[[str], None]
AnswerListLoadedCB = Callable[[dict], None]
AllPlayersCB = Callable[[Iterable[Player]], None]
CurrentPlayerCB = Callable[[Optional[str]], None]
RunningStateCB = Callable[[bool], None]
AnswersUpdatedCB = Callable[[list, list], None]  # remaining_items, answered_items
SoundEventCB = Callable[[str], None]  # 'correct' or 'wrong'

class GameController:
    """
    UI に依存しないコントローラ
    - UI は register_* でコールバックを渡し、public メソッドで操作する
    - tick() を外部タイマー（UI）から定期的に呼ぶ
    """

    def __init__(self):
        # model state
        self.players: List[Player] = []
        self.answer_list: Optional[AnswerList] = None
        self.current_idx: int = 0
        self.is_running: bool = False
        self._last_tick_monotonic: Optional[float] = None

        # callbacks (UI側で登録)
        self.on_notification: Optional[NotificationCB] = None
        self.on_player_added: Optional[PlayerAddedCB] = None
        self.on_player_state: Optional[PlayerStateCB] = None
        self.on_game_ended: Optional[GameEndedCB] = None
        self.on_answer_list_loaded: Optional[AnswerListLoadedCB] = None
        self.on_answers_updated: Optional[AnswersUpdatedCB] = None
        self.on_sound_event: Optional[SoundEventCB] = None
        self.on_all_players: Optional[AllPlayersCB] = None
        self.on_current_player: Optional[CurrentPlayerCB] = None
        self.on_running_state: Optional[RunningStateCB] = None
        # track answered items in chronological order (oldest -> newest)
        self._answered_order: List[str] = []
        # last answered classification key (normalized), used to allow short-form matches
        self._last_answered_class: Optional[str] = None

    # registration
    def register_notification(self, cb: NotificationCB) -> None:
        self.on_notification = cb
    def register_player_added(self, cb: PlayerAddedCB) -> None:
        self.on_player_added = cb
    def register_player_state(self, cb: PlayerStateCB) -> None:
        self.on_player_state = cb
    def register_game_ended(self, cb: GameEndedCB) -> None:
        self.on_game_ended = cb
    def register_answer_list_loaded(self, cb: AnswerListLoadedCB) -> None:
        self.on_answer_list_loaded = cb
    def register_answers_updated(self, cb: AnswersUpdatedCB) -> None:
        self.on_answers_updated = cb
    def register_sound_event(self, cb: SoundEventCB) -> None:
        self.on_sound_event = cb
    def register_all_players(self, cb: AllPlayersCB) -> None:
        self.on_all_players = cb
    def register_current_player(self, cb: CurrentPlayerCB) -> None:
        self.on_current_player = cb
    def register_running_state(self, cb: RunningStateCB) -> None:
        self.on_running_state = cb

    # internal notifications
    def _notify(self, level: str, message: str) -> None:
        if self.on_notification:
            self.on_notification(level, message)

    def _emit_player_state(self, p: Player) -> None:
        if self.on_player_state:
            # remaining_ms is calculated dynamically during tick, stored in _remaining_ms
            remaining_ms = getattr(p, '_remaining_ms', 0)
            self.on_player_state(p.name, remaining_ms, p.remaining_passes, p.remaining_wrong_answers, p.eliminated)

    def _emit_all_players(self) -> None:
        if self.on_all_players:
            self.on_all_players(list(self.players))

    def _emit_current_player(self) -> None:
        cp = self.current_player()
        name = cp.name if cp is not None else None
        if self.on_current_player:
            self.on_current_player(name)

    def _emit_running_state(self) -> None:
        if self.on_running_state:
            self.on_running_state(self.is_running)

    def _name_exists(self, name: str) -> bool:
        norm = normalize_text(name)
        return any(normalize_text(p.name) == norm for p in self.players)

    def load_csv(self, path: str) -> None:
        try:
            import os
            import shutil

            # Ensure file is in data/answer_list/
            answer_list_dir = os.path.join(os.getcwd(), "data", "answer_list")
            if os.path.basename(os.path.dirname(path)) != "answer_list":
                os.makedirs(answer_list_dir, exist_ok=True)
                dst = os.path.join(answer_list_dir, os.path.basename(path))
                if os.path.abspath(path) != os.path.abspath(dst):
                    shutil.copy2(path, dst)
                path = dst
            self.answer_list = AnswerList.load_from_csv(path)
            # Store answer list title (filename without extension) for CSV output
            self._answer_list_title = os.path.splitext(os.path.basename(path))[0]
            self._answered_order = [i for i in self.answer_list.items if i in self.answer_list.used]
            meta = {"total": len(self.answer_list.items)}
            if self.on_answer_list_loaded:
                self.on_answer_list_loaded(meta)
            if self.on_answers_updated:
                remaining = [i for i in self.answer_list.items if i not in self.answer_list.used]
                answered = list(reversed(self._answered_order))
                self.on_answers_updated(remaining, answered)
            self._notify("info", f"読み込み完了: {meta['total']} 件")
            self._emit_all_players()
        except Exception as e:
            self._notify("error", f"CSV 読み込みエラー: {e}")

    def add_player(self, name: str, base_seconds: int, pass_limit: int, wrong_answer_limit: int) -> None:
        if not name or len(name) > 60:
            self._notify("error", "名前を1〜60文字で入力してください")
            return
        if self._name_exists(name):
            self._notify("error", f"同名のプレイヤーが既に存在します: {name}")
            return
        pid = str(uuid.uuid4())[:8]
        p = Player(id=pid, name=name, base_seconds=base_seconds, pass_limit=pass_limit, wrong_answer_limit=wrong_answer_limit)
        p.reset_runtime()
        self.players.append(p)
        if self.on_player_added:
            self.on_player_added(p)
        self._notify("info", f"プレイヤー追加: {name}")
        self._emit_all_players()
        self._emit_current_player()

    def remove_player(self, name: str) -> None:
        norm = normalize_text(name)
        before = len(self.players)
        self.players = [p for p in self.players if normalize_text(p.name) != norm]
        removed = before - len(self.players)
        if removed > 0:
            self._notify("info", f"プレイヤー削除: {removed} 件")
        else:
            self._notify("error", f"プレイヤーが見つかりません: {name}")
        self.current_idx = max(0, min(self.current_idx, max(0, len(self.players)-1)))
        self._emit_all_players()
        self._emit_current_player()

    def start_game(self) -> None:
        if not self.answer_list:
            self._notify("error", "正解リストを読み込んでください")
            return
        if not self.players:
            self._notify("error", "プレイヤーがいません")
            return
        for p in self.players:
            p.reset_runtime()
            p._remaining_ms = int(p.base_seconds * 1000)  # set initial time per player
        self.current_idx = 0
        self.is_running = True
        self._last_tick_monotonic = time.monotonic()
        self._notify("info", "ゲーム開始")
        self._emit_all_players()
        self._emit_current_player()
        self._emit_running_state()
        cp = self.current_player()
        if cp:
            self._emit_player_state(cp)

    def stop_game(self) -> None:
        self.is_running = False
        self._notify("info", "ゲーム停止")
        if self.on_game_ended:
            self.on_game_ended("stopped")
        self._emit_all_players()
        self._emit_current_player()
        self._emit_running_state()

    def host_submit_answer(self, text: str) -> None:
        p = self.current_player()
        if p is None:
            self._notify("error", "現在のプレイヤーがいません")
            return
        if not self.answer_list:
            self._notify("error", "正解リストが読み込まれていません")
            return
        
        # Extract answer text: if format is "...（answer）" or "...(answer)", 
        # use the text inside parentheses for matching
        answer_text = text
        try:
            # Try to extract text from （...）or (...) 
            if '（' in text and '）' in text:
                start = text.rfind('（')
                end = text.rfind('）')
                if start < end:
                    answer_text = text[start+1:end]
            elif '(' in text and ')' in text:
                start = text.rfind('(')
                end = text.rfind(')')
                if start < end:
                    answer_text = text[start+1:end]
        except Exception:
            pass
        
        # pass previous class to matching to allow short form matching
        prev_class = getattr(self, '_last_answered_class', None)
        matched_disp = None
        try:
            matched_disp = self.answer_list.find_match(answer_text, previous_class=prev_class)
        except Exception:
            matched_disp = None
        is_correct = matched_disp is not None
        p.record_answer(text, is_correct)

        # Regardless of correctness, attempt to infer and remember classification prefix
        try:
            t_norm = normalize_text(answer_text)
            # prefer class from matched_disp if available
            if matched_disp:
                cls_key = getattr(self.answer_list, '_class_map', {}).get(matched_disp)
                if cls_key:
                    self._last_answered_class = cls_key
            else:
                # fall back: detect a class prefix from known class_map values
                class_values = list(set(getattr(self.answer_list, '_class_map', {}).values()))
                # sort by length desc so longer (more specific) match wins
                class_values.sort(key=lambda s: len(s), reverse=True)
                for cv in class_values:
                    if cv and t_norm.startswith(cv):
                        self._last_answered_class = cv
                        break
        except Exception:
            pass

        if is_correct:
            # mark used and record chronology (store display string in _answered_order)
            try:
                used_disp = self.answer_list.mark_used(answer_text, previous_class=prev_class)
                if not used_disp:
                    # fallback: try to use matched_disp
                    used_disp = matched_disp
                if used_disp:
                    if used_disp not in self._answered_order:
                        self._answered_order.append(used_disp)
            except Exception:
                pass
            # notify UI about moved item (remaining, answered newest-first)
            if self.on_answers_updated:
                remaining = [i for i in self.answer_list.items if i not in self.answer_list.used]
                answered = list(reversed(self._answered_order))
                self.on_answers_updated(remaining, answered)
            # emit sound event for correct answer
            if self.on_sound_event:
                try:
                    self.on_sound_event('correct')
                except Exception:
                    pass
            p.reset_wrong_answers()  # reset wrong answer count on correct

            try:
                if self._answered_order:
                    used_disp = self._answered_order[-1]
                    cls_key = getattr(self.answer_list, '_class_map', {}).get(used_disp)
                    if cls_key:
                        self._last_answered_class = cls_key
            except Exception:
                pass

            self._notify("info", f"{p.name} が正解しました: {text}")
            self._emit_player_state(p)
            self._advance_turn_after_event("correct")
        else:
            if not p.consume_wrong_answer():
                # no wrong answers left -> eliminate
                p.eliminated = True
                self._notify("info", f"{p.name} が誤答制限に達しました")
                self._emit_player_state(p)
                self._advance_turn_after_event("wrong_limit")
            else:
                self._notify("info", f"{p.name} の不正解: {text} （残り: {p.remaining_wrong_answers}）")
                self._emit_player_state(p)
                # emit wrong sound
                if self.on_sound_event:
                    try:
                        self.on_sound_event('wrong')
                    except Exception:
                        pass
        self._emit_all_players()
        self._emit_current_player()

    def host_pass(self) -> None:
        p = self.current_player()
        if p is None:
            self._notify("error", "現在のプレイヤーがいません")
            return
        if p.consume_pass():
            self._notify("info", f"{p.name} がパスを使いました（残: {p.remaining_passes}）")
            self._emit_player_state(p)
            self._advance_turn_after_event("pass")
        else:
            # show as info rather than error per UI request
            self._notify("info", "パス権がありません")
        self._emit_all_players()
        self._emit_current_player()

    def unmark_answer(self, display_key: str) -> bool:
        """Move an answered item back to remaining. Return True if changed."""
        if not self.answer_list:
            self._notify("error", "回答リストが読み込まれていません")
            return False
        # display_key expected to be the normalized display string (as used in answer_list.items)
        try:
            if display_key in self.answer_list.used:
                try:
                    self.answer_list.used.discard(display_key)
                except Exception:
                    pass
                # remove from chronology if present
                try:
                    if display_key in self._answered_order:
                        self._answered_order.remove(display_key)
                except Exception:
                    pass
                # notify UI
                if self.on_answers_updated:
                    remaining = [i for i in self.answer_list.items if i not in self.answer_list.used]
                    answered = list(reversed(self._answered_order))
                    self.on_answers_updated(remaining, answered)
                self._notify("info", f"{display_key} を未回答に戻しました")
                return True
            else:
                self._notify("info", f"項目が回答済みではありません: {display_key}")
                return False
        except Exception as e:
            self._notify("error", f"内部エラー: {e}")
            return False

    def tick(self) -> None:
        if not self.is_running:
            return
        now = time.monotonic()
        if self._last_tick_monotonic is None:
            self._last_tick_monotonic = now
            return
        elapsed = now - self._last_tick_monotonic
        self._last_tick_monotonic = now
        p = self.current_player()
        if p is None:
            self._notify("info", "アクティブなプレイヤーがいません")
            self._end_if_finished()
            self._emit_all_players()
            self._emit_current_player()
            return
        p._remaining_ms = max(0, getattr(p, '_remaining_ms', 0) - int(elapsed * 1000))
        if p._remaining_ms == 0:
            p.eliminated = True
            self._notify("info", f"{p.name} がタイムアウトで脱落しました")
            self._emit_player_state(p)
            self._advance_turn_after_event("timeout")
        else:
            self._emit_player_state(p)
        self._emit_all_players()
        self._emit_current_player()

    def current_player(self) -> Optional[Player]:
        n = len(self.players)
        if n == 0:
            return None
        for i in range(n):
            idx = (self.current_idx + i) % n
            if not self.players[idx].eliminated:
                self.current_idx = idx
                return self.players[idx]
        return None

    def _advance_turn_after_event(self, reason: str) -> None:
        if self._end_if_finished():
            return
        n = len(self.players)
        if n == 0:
            self._notify("info", "プレイヤーがいません")
            return
        for i in range(1, n + 1):
            cand = (self.current_idx + i) % n
            if not self.players[cand].eliminated:
                self.current_idx = cand
                break
        np = self.current_player()
        if np:
            # reset thinking time to base_seconds for each player's turn
            np._remaining_ms = int(np.base_seconds * 1000)
            self._emit_player_state(np)
        self._emit_all_players()
        self._emit_current_player()

    def _end_if_finished(self) -> bool:
        if self.players and all(p.eliminated for p in self.players):
            # treat as Stop pressed
            try:
                self.stop_game()
            except Exception:
                pass
            return True
        if self.answer_list and self.answer_list.remaining_count() == 0:
            # treat as Stop pressed
            try:
                self.stop_game()
            except Exception:
                pass
            return True
        return False
    
    def reorder_players_by_name(self, names: list) -> None:
        """
        UI から渡された名前順に players リストを並べ替える。
        - names: プレイヤー名のリスト（表示名、生テキスト）
        - 正規化してマッチさせ、見つからない名前は無視する
        """
        if not names or not self.players:
            return

        # build map by normalized name -> Player
        name_map = {normalize_text(p.name): p for p in self.players}

        new_players = []
        used = set()
        for n in names:
            norm = normalize_text(n)
            p = name_map.get(norm)
            if p and p not in used:
                new_players.append(p)
                used.add(p)

        # append any remaining players that were not listed (preserve them)
        for p in self.players:
            if p not in used:
                new_players.append(p)

        # if nothing changed, skip
        if new_players == self.players:
            return

        self.players = new_players
        # ensure current_idx remains valid (clamp)
        self.current_idx = max(0, min(self.current_idx, max(0, len(self.players)-1)))
        # notify UI of the new full ordering and current highlight
        self._emit_all_players()
        self._emit_current_player()

    def move_player(self, name: str, target_index: int) -> None:
        """Move player identified by name to target_index in the players list.

        target_index is the desired position in the original (pre-move)
        indexing: when dropping onto row i, controller will insert the
        moved player before the item that used to be at index i. This
        method adjusts for removal shift.
        """
        norm = normalize_text(name)
        orig_idx = None
        for i, p in enumerate(self.players):
            if normalize_text(p.name) == norm:
                orig_idx = i
                break
        if orig_idx is None:
            self._notify("error", f"プレイヤーが見つかりません: {name}")
            return

        n = len(self.players)
        target_index = max(0, min(int(target_index), n))

        # if target is after original, after removal the insertion index
        # should be target_index - 1
        if target_index > orig_idx:
            insert_at = target_index - 1
        else:
            insert_at = target_index

        if insert_at == orig_idx:
            return

        p = self.players.pop(orig_idx)
        # clamp insert position in the shortened list
        insert_at = max(0, min(insert_at, len(self.players)))
        self.players.insert(insert_at, p)

        # keep current_idx valid
        self.current_idx = max(0, min(self.current_idx, max(0, len(self.players)-1)))

        self._emit_all_players()
        self._emit_current_player()

    def forfeit_player(self, name: str) -> None:
        """Mark player as eliminated (strong forfeit)."""
        norm = normalize_text(name)
        for p in self.players:
            if normalize_text(p.name) == norm:
                p.eliminated = True
                self._notify("info", f"{p.name} が強制失格しました")
                self._emit_player_state(p)
                self._advance_turn_after_event("forfeit")
                self._emit_all_players()
                self._emit_current_player()
                return
        self._notify("error", f"プレイヤーが見つかりません: {name}")

    def skip_player(self, name: str) -> None:
        """Skip current player without consuming pass limit."""
        p = self.current_player()
        if p is None or normalize_text(p.name) != normalize_text(name):
            self._notify("error", "スキップ対象が現在のプレイヤーではありません")
            return
        self._notify("info", f"{p.name} をスキップしました")
        self._advance_turn_after_event("skip")
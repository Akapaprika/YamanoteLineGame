import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List

from ..utils.text_norm import normalize_text


@dataclass
class AnswerRecord:
    text: str
    ts_utc: datetime
    monotonic_ms: int
    is_correct: bool

@dataclass
class Player:
    id: str
    name: str
    base_seconds: int = 60
    pass_limit: int = 0
    wrong_answer_limit: int = 5

    # runtime (remaining_ms is NOT stored, calculated per-turn)
    remaining_passes: int = 0
    remaining_wrong_answers: int = 0
    eliminated: bool = False

    # history
    correct_answers: List[AnswerRecord] = field(default_factory=list)
    wrong_answers: List[AnswerRecord] = field(default_factory=list)

    def reset_runtime(self) -> None:
        self.remaining_passes = self.pass_limit
        self.remaining_wrong_answers = self.wrong_answer_limit
        self.eliminated = False
        self.correct_answers.clear()
        self.wrong_answers.clear()

    def consume_wrong_answer(self) -> bool:
        """Check and decrement wrong answer count."""
        if self.remaining_wrong_answers > 0:
            self.remaining_wrong_answers -= 1
            return True
        return False

    def reset_wrong_answers(self) -> None:
        """Reset wrong answer count to max (on correct answer)."""
        self.remaining_wrong_answers = self.wrong_answer_limit

    def can_pass(self) -> bool:
        return self.remaining_passes > 0

    def consume_pass(self) -> bool:
        if self.can_pass():
            self.remaining_passes -= 1
            return True
        return False

    def record_answer(self, text: str, is_correct: bool) -> None:
        rec = AnswerRecord(
            text=normalize_text(text),
            ts_utc=datetime.now(timezone.utc),
            monotonic_ms=int(time.monotonic() * 1000),
            is_correct=is_correct,
        )
        if is_correct:
            self.correct_answers.append(rec)
        else:
            self.wrong_answers.append(rec)
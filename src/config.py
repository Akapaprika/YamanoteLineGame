"""
Centralized configuration for sound files and game settings.
"""

import os

# Base directories
SOUND_DIR = os.path.join(os.getcwd(), "data", "sound")

# Correct/Wrong answer sounds
SOUND_CORRECT = "6835395119082655.mp3"
SOUND_WRONG = "6835395119082682.mp3"

# Countdown beep sounds: use available MP3 files
# Played at specific elapsed times during a turn
COUNTDOWN_SOUNDS = {
    "timeout": "6835395119082634.mp3",        # Played when time runs out (0 seconds)
    10: "6835395119082634.mp3",               # 10 seconds elapsed
    20: "6835395119082655.mp3",               # 20 seconds elapsed
    30: "6835395119082682.mp3",               # 30 seconds elapsed
    40: "6835395119082719.mp3",               # 40 seconds elapsed
    50: "6835395119082764.mp3",               # 50 seconds elapsed
    51: "6835395119082938.mp3",               # 51 seconds elapsed
    52: "6835395119082956.mp3",
    53: "6835395119082983.mp3",
    # For 54-59 seconds, reuse available files or leave unmapped
}


def get_sound_path(filename: str) -> str:
    """Get full path to a sound file. Returns path even if file doesn't exist."""
    return os.path.join(SOUND_DIR, filename)


def sound_exists(filename: str) -> bool:
    """Check if a sound file exists."""
    path = get_sound_path(filename)
    return os.path.exists(path)

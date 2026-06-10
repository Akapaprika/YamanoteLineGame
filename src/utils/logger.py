"""
Logging utility for YamanoteLineGame.
"""

import logging
import sys

# Configure logging
logger = logging.getLogger('yamanote_game')
logger.setLevel(logging.DEBUG)

# Console handler
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
handler.setFormatter(formatter)
logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(f'yamanote_game.{name}')

from __future__ import annotations

import os
import logging

# Create logs directory if it doesn't exist
if not os.path.exists('logs'):
    os.makedirs('logs')

# Logging configuration
LOG_DIR = 'logs'
LOG_FILE = os.path.join(LOG_DIR, 'deck_builder.log')
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_LEVEL = logging.INFO

# Create formatters and handlers
# Create a formatter that removes double underscores
class NoDunderFormatter(logging.Formatter):
    def format(self, record):
        record.name = record.name.replace("__", "")
        return super().format(record)

# File handler
file_handler = logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')
file_handler.setFormatter(NoDunderFormatter(LOG_FORMAT))

# Stream handler
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(NoDunderFormatter(LOG_FORMAT))

# Root logger assembly helper (idempotent)
def get_logger(name: str = 'deck_builder') -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(LOG_LEVEL)
        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)
    return logger
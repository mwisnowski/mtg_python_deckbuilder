from __future__ import annotations

from settings import os
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
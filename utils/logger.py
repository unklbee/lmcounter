# utils/logger.py
# -*- coding: utf-8 -*-

"""
Logging system for Vehicle Counter application
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime
import json
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler

# Default log directory
DEFAULT_LOG_DIR = Path(__file__).parent.parent / "logs"

# Log format settings
DEFAULT_FORMAT = "%(asctime)s | %(levelname)8s | %(name)25s | %(message)s"
DETAILED_FORMAT = "%(asctime)s | %(levelname)8s | %(name)25s | %(filename)s:%(lineno)d | %(message)s"

class JSONFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings for each log record
    """
    def format(self, record):
        """Format record as JSON"""
        logobj = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }

        # Add exception info if available
        if record.exc_info:
            logobj["exception"] = self.formatException(record.exc_info)

        return json.dumps(logobj)

class LogManager:
    """
    Manages application logging across components
    """
    def __init__(self, log_dir=None, log_level=logging.INFO):
        """
        Initialize log manager

        Args:
            log_dir (str): Directory for log files (uses default if None)
            log_level (int): Default log level
        """
        self.log_dir = Path(log_dir or DEFAULT_LOG_DIR)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.log_level = log_level
        self.handlers = {}

        # Configure root logger
        self.setup_root_logger()

        # Module-specific loggers
        self.loggers = {}

    def setup_root_logger(self):
        """Setup root logger with console and file handlers"""
        root_logger = logging.getLogger()
        root_logger.setLevel(self.log_level)

        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter(DEFAULT_FORMAT))
        root_logger.addHandler(console_handler)
        self.handlers["console"] = console_handler

        # File handler - app.log
        file_handler = RotatingFileHandler(
            self.log_dir / "app.log",
            maxBytes=10*1024*1024,  # 10 MB
            backupCount=5
        )
        file_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
        root_logger.addHandler(file_handler)
        self.handlers["file"] = file_handler

        # Daily file handler
        daily_handler = TimedRotatingFileHandler(
            self.log_dir / "daily.log",
            when="midnight",
            interval=1,
            backupCount=30
        )
        daily_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
        root_logger.addHandler(daily_handler)
        self.handlers["daily"] = daily_handler

        # JSON file handler
        json_handler = RotatingFileHandler(
            self.log_dir / "app.json",
            maxBytes=10*1024*1024,  # 10 MB
            backupCount=5
        )
        json_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(json_handler)
        self.handlers["json"] = json_handler

        logging.info(f"Log directory: {self.log_dir}")

    def get_logger(self, name):
        """
        Get logger for a specific component

        Args:
            name (str): Logger name (usually __name__)

        Returns:
            logging.Logger: Logger instance
        """
        if name in self.loggers:
            return self.loggers[name]

        logger = logging.getLogger(name)
        self.loggers[name] = logger
        return logger

    def set_log_level(self, level, logger_name=None):
        """
        Set log level for all or specific logger

        Args:
            level (int): Log level (logging.DEBUG, INFO, etc.)
            logger_name (str): Logger name or None for all
        """
        if logger_name:
            logger = logging.getLogger(logger_name)
            logger.setLevel(level)
        else:
            # Update root logger and all handlers
            logging.getLogger().setLevel(level)
            for handler in self.handlers.values():
                handler.setLevel(level)

            # Update instance variable
            self.log_level = level

        logging.info(f"Set log level to {logging.getLevelName(level)}" +
                     (f" for {logger_name}" if logger_name else ""))

    def enable_debug(self, logger_name=None):
        """
        Enable debug logging for all or specific logger

        Args:
            logger_name (str): Logger name or None for all
        """
        self.set_log_level(logging.DEBUG, logger_name)

    def add_component_file_handler(self, component_name):
        """
        Add a separate file handler for a specific component

        Args:
            component_name (str): Component name

        Returns:
            logging.Handler: Created handler
        """
        logger = logging.getLogger(component_name)

        # Create component log file
        safe_name = component_name.replace(".", "_").lower()
        file_handler = RotatingFileHandler(
            self.log_dir / f"{safe_name}.log",
            maxBytes=5*1024*1024,  # 5 MB
            backupCount=3
        )
        file_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
        logger.addHandler(file_handler)

        return file_handler

    def get_log_files(self):
        """
        Get list of log files

        Returns:
            list: List of log file paths
        """
        log_files = []
        for file_path in self.log_dir.glob("*.log"):
            log_files.append(str(file_path))
        return log_files

    def archive_logs(self):
        """
        Archive current logs

        Returns:
            str: Archive path
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_dir = self.log_dir / f"archive_{timestamp}"
        archive_dir.mkdir(exist_ok=True)

        # Close handlers
        for handler in self.handlers.values():
            handler.close()

        # Move logs to archive
        for file_path in self.log_dir.glob("*.log*"):
            if file_path.is_file():
                target_path = archive_dir / file_path.name
                try:
                    os.rename(file_path, target_path)
                except Exception as e:
                    logging.error(f"Error archiving log {file_path}: {str(e)}")

        # Recreate handlers
        self.setup_root_logger()

        return str(archive_dir)


# Singleton instance
_log_manager = None

def setup_logging(log_dir=None, log_level=logging.INFO):
    """
    Setup application logging

    Args:
        log_dir (str): Directory for log files
        log_level (int): Default log level

    Returns:
        LogManager: Log manager instance
    """
    global _log_manager
    if _log_manager is None:
        _log_manager = LogManager(log_dir, log_level)
    return _log_manager

def get_logger(name):
    """
    Get logger for component

    Args:
        name (str): Logger name (usually __name__)

    Returns:
        logging.Logger: Logger instance
    """
    global _log_manager
    if _log_manager is None:
        _log_manager = setup_logging()
    return _log_manager.get_logger(name)

def set_log_level(level, logger_name=None):
    """
    Set log level

    Args:
        level (int): Log level
        logger_name (str): Logger name or None for all
    """
    global _log_manager
    if _log_manager is None:
        _log_manager = setup_logging()
    _log_manager.set_log_level(level, logger_name)

def enable_debug(logger_name=None):
    """
    Enable debug logging

    Args:
        logger_name (str): Logger name or None for all
    """
    set_log_level(logging.DEBUG, logger_name)
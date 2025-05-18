#config/settings.py
# -*- coding: utf-8 -*-

"""
Global application settings for Vehicle Counter
"""

import os
from pathlib import Path

# Project paths
ROOT_DIR = Path(os.environ.get("VEHICLE_COUNTER_ROOT", Path(__file__).parent.parent.parent))
CONFIG_DIR = ROOT_DIR / "config"
PRESETS_DIR = CONFIG_DIR / "presets"
DATA_DIR = ROOT_DIR / "data"
MODELS_DIR = DATA_DIR / "models"
DB_DIR = DATA_DIR / "db"

# Database settings
DATABASE_PATH = DB_DIR / "vehicle_counter.db"
DB_SCHEMA_PATH = DB_DIR / "schema.sql"

# Default model settings
DEFAULT_MODEL = MODELS_DIR / "nanodet-plus-m_416_openvino.xml"
DEFAULT_CONF_THRESHOLD = 0.5
DEFAULT_NMS_THRESHOLD = 0.4

# Video processing settings
DEFAULT_FPS = 30
DEFAULT_FRAME_WIDTH = 1280
DEFAULT_FRAME_HEIGHT = 720
DEFAULT_BUFFER_SIZE = 10  # Frames to buffer for async processing

# API settings
DEFAULT_API_ENDPOINT = "http://localhost:8000/api/counts"
API_TIMEOUT = 5  # seconds

# Vehicle class mapping
VEHICLE_CLASSES = {
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck"
}

# Color settings (BGR format)
COLORS = {
    "car": (0, 255, 0),        # Green
    "bicycle": (255, 0, 0),    # Blue
    "motorcycle": (0, 0, 255), # Red
    "bus": (255, 255, 0),      # Cyan
    "truck": (255, 0, 255),    # Magenta
    "roi": (255, 165, 0),      # Orange
    "counting_line": (0, 255, 255), # Yellow
    "text_bg": (0, 0, 0),      # Black
    "text_fg": (255, 255, 255) # White
}

# GUI settings
WINDOW_TITLE = "Vehicle Counter"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 800
CONTROL_PANEL_WIDTH = 280

# Application version
VERSION = "1.0.0"
# utils/preset_manager.py
# -*- coding: utf-8 -*-

"""
Preset manager for handling configuration presets
"""

import os
import json
import uuid
import logging
from pathlib import Path
from datetime import datetime
from config.settings import PRESETS_DIR

# Setup logger
logger = logging.getLogger(__name__)

class PresetManager:
    """
    Manages saving, loading, and validation of configuration presets
    """
    def __init__(self, presets_dir=None):
        """
        Initialize preset manager

        Args:
            presets_dir (str): Directory for presets (uses default if None)
        """
        self.presets_dir = Path(presets_dir or PRESETS_DIR)
        self.presets_dir.mkdir(parents=True, exist_ok=True)

        # Default preset path
        self.default_preset_path = self.presets_dir / "default.json"

        # Cached presets
        self.presets = {}

        # Current preset
        self.current_preset = None
        self.current_preset_path = None

        # Load available presets
        self.load_available_presets()

    def load_available_presets(self):
        """
        Load information about available presets

        Returns:
            dict: Preset information {id: {name, path, created}}
        """
        self.presets = {}

        # Scan preset directory
        for file_path in self.presets_dir.glob("*.json"):
            try:
                # Load basic info without full preset data
                with open(file_path, 'r') as f:
                    data = json.load(f)

                preset_id = data.get("id", str(uuid.uuid4()))
                self.presets[preset_id] = {
                    "id": preset_id,
                    "name": data.get("name", file_path.stem),
                    "path": str(file_path),
                    "created": data.get("created", datetime.now().isoformat()),
                    "description": data.get("description", "")
                }
            except Exception as e:
                logger.error(f"Error loading preset info from {file_path}: {str(e)}")

        logger.info(f"Loaded information for {len(self.presets)} presets")
        return self.presets

    def get_preset_list(self):
        """
        Get list of available presets

        Returns:
            list: List of preset info dictionaries
        """
        return list(self.presets.values())

    def create_empty_preset(self):
        """
        Create a new empty preset structure

        Returns:
            dict: Empty preset structure
        """
        return {
            "id": str(uuid.uuid4()),
            "name": "New Preset",
            "description": "",
            "created": datetime.now().isoformat(),
            "modified": datetime.now().isoformat(),
            "source": {
                "type": "file",
                "path": "",
                "options": {}
            },
            "detector": {
                "model": "yolov5n.xml",
                "device": "GPU",
                "conf_threshold": 0.5,
                "nms_threshold": 0.4,
                "async_mode": True
            },
            "tracker": {
                "max_disappeared": 10,
                "min_iou_threshold": 0.3,
                "max_distance": 150
            },
            "rois": {},
            "counting_lines": {},
            "output": {
                "save_video": False,
                "output_path": "",
                "push_to_api": False,
                "api_endpoint": ""
            },
            "display": {
                "show_detections": True,
                "show_tracking": True,
                "show_counting": True,
                "show_performance": True
            }
        }

    def load_preset(self, preset_id=None, path=None):
        """
        Load a preset by ID or path

        Args:
            preset_id (str): Preset ID to load
            path (str): Path to preset file (alternative to preset_id)

        Returns:
            dict: Loaded preset or None on failure
        """
        # Determine path to load
        if preset_id and preset_id in self.presets:
            path_to_load = self.presets[preset_id]["path"]
        elif path:
            path_to_load = path
        elif os.path.exists(self.default_preset_path):
            path_to_load = self.default_preset_path
        else:
            logger.warning("No preset specified and no default preset found")
            return None

        try:
            with open(path_to_load, 'r') as f:
                preset = json.load(f)

            # Validate preset
            if not self._validate_preset(preset):
                logger.warning(f"Invalid preset format in {path_to_load}")
                return None

            # Store current preset
            self.current_preset = preset
            self.current_preset_path = path_to_load

            logger.info(f"Loaded preset from {path_to_load}")
            return preset

        except Exception as e:
            logger.error(f"Error loading preset from {path_to_load}: {str(e)}")
            return None

    def save_preset(self, preset, path=None, update_current=True):
        """
        Save preset to file

        Args:
            preset (dict): Preset data
            path (str): Path to save (generates from name if None)
            update_current (bool): Update current preset reference

        Returns:
            bool: Success status
        """
        if path is None:
            # Generate filename from preset name
            safe_name = preset.get("name", "preset").replace(" ", "_").lower()
            path = self.presets_dir / f"{safe_name}.json"

        try:
            # Ensure preset has basic fields
            if "id" not in preset:
                preset["id"] = str(uuid.uuid4())

            if "created" not in preset:
                preset["created"] = datetime.now().isoformat()

            preset["modified"] = datetime.now().isoformat()

            # Save to file
            with open(path, 'w') as f:
                json.dump(preset, f, indent=2)

            # Update current preset if requested
            if update_current:
                self.current_preset = preset
                self.current_preset_path = path

            # Update presets cache
            self.presets[preset["id"]] = {
                "id": preset["id"],
                "name": preset.get("name", "Unnamed"),
                "path": str(path),
                "created": preset.get("created"),
                "description": preset.get("description", "")
            }

            logger.info(f"Saved preset to {path}")
            return True

        except Exception as e:
            logger.error(f"Error saving preset to {path}: {str(e)}")
            return False

    def delete_preset(self, preset_id):
        """
        Delete a preset

        Args:
            preset_id (str): ID of preset to delete

        Returns:
            bool: Success status
        """
        if preset_id not in self.presets:
            logger.warning(f"Preset {preset_id} not found")
            return False

        try:
            path = self.presets[preset_id]["path"]

            # Delete file
            os.remove(path)

            # Remove from cache
            del self.presets[preset_id]

            # Reset current preset if it was deleted
            if self.current_preset and self.current_preset.get("id") == preset_id:
                self.current_preset = None
                self.current_preset_path = None

            logger.info(f"Deleted preset {preset_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting preset {preset_id}: {str(e)}")
            return False

    def save_default_preset(self):
        """
        Save current preset as default

        Returns:
            bool: Success status
        """
        if not self.current_preset:
            logger.warning("No current preset to save as default")
            return False

        return self.save_preset(self.current_preset, self.default_preset_path, False)

    def _validate_preset(self, preset):
        """
        Validate preset structure

        Args:
            preset (dict): Preset to validate

        Returns:
            bool: True if valid
        """
        # Check basic structure
        required_keys = ["source", "detector"]
        for key in required_keys:
            if key not in preset:
                logger.warning(f"Missing required key: {key}")
                return False

        # More detailed validation could be added here

        return True

    def preset_to_config(self, preset=None):
        """
        Convert preset to component configurations

        Args:
            preset (dict): Preset to convert (uses current if None)

        Returns:
            dict: Configuration for different components
        """
        if preset is None:
            preset = self.current_preset

        if not preset:
            logger.warning("No preset available to convert")
            return {}

        # Extract configurations
        config = {
            "source": preset.get("source", {}),
            "detector": preset.get("detector", {}),
            "tracker": preset.get("tracker", {}),
            "rois": preset.get("rois", {}),
            "counting_lines": preset.get("counting_lines", {}),
            "output": preset.get("output", {}),
            "display": preset.get("display", {})
        }

        return config

    def config_to_preset(self, config, base_preset=None):
        """
        Convert configuration to preset

        Args:
            config (dict): Component configurations
            base_preset (dict): Base preset to update (creates new if None)

        Returns:
            dict: Updated preset
        """
        # Use base preset or create new
        preset = base_preset.copy() if base_preset else self.create_empty_preset()

        # Update with config
        for key, value in config.items():
            if key in preset:
                preset[key] = value

        # Update modified timestamp
        preset["modified"] = datetime.now().isoformat()

        return preset


# Singleton instance
_preset_manager = None

def get_preset_manager():
    """
    Get or create preset manager singleton

    Returns:
        PresetManager: Preset manager instance
    """
    global _preset_manager
    if _preset_manager is None:
        _preset_manager = PresetManager()
    return _preset_manager
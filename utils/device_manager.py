# utils/device_manager.py
# -*- coding: utf-8 -*-

"""
Device manager for handling CPU/GPU selection and optimization
"""

import os
import platform
import logging
import subprocess
from enum import Enum
from openvino.runtime import Core, get_version

# Setup logger
logger = logging.getLogger(__name__)

class DeviceType(Enum):
    """Supported compute device types"""
    CPU = "CPU"
    GPU = "GPU"
    AUTO = "AUTO"

class DeviceManager:
    """
    Manages device selection and optimization for inference
    """
    def __init__(self):
        """Initialize device manager"""
        self.core = Core()
        self.available_devices = self._get_available_devices()
        self.current_device = None
        self.device_info = {}

        logger.info(f"OpenVINO version: {get_version()}")
        logger.info(f"Available devices: {self.available_devices}")

    def _get_available_devices(self):
        """
        Get list of available devices from OpenVINO

        Returns:
            list: Available device names
        """
        try:
            devices = self.core.available_devices
            return devices
        except Exception as e:
            logger.error(f"Error getting available devices: {str(e)}")
            return ["CPU"]  # Default to CPU on error

    def get_system_info(self):
        """
        Get system hardware information

        Returns:
            dict: System information
        """
        info = {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
            "openvino_version": get_version(),
            "available_devices": self.available_devices
        }

        # Try to get more detailed CPU info
        try:
            if platform.system() == "Linux":
                cpu_info = subprocess.check_output("lscpu", shell=True).decode().strip()
                info["cpu_details"] = cpu_info
            elif platform.system() == "Windows":
                cpu_info = subprocess.check_output("wmic cpu get name", shell=True).decode().strip()
                info["cpu_name"] = cpu_info.split("\n")[1]
        except Exception as e:
            logger.warning(f"Could not get detailed CPU info: {str(e)}")

        # Try to get GPU info
        try:
            if "GPU" in self.available_devices:
                gpu_properties = self.core.get_property("GPU", "FULL_DEVICE_NAME")
                info["gpu_name"] = gpu_properties
        except Exception as e:
            logger.warning(f"Could not get GPU info: {str(e)}")

        return info

    def select_device(self, device_type=DeviceType.AUTO):
        """
        Select and configure best available device

        Args:
            device_type (DeviceType): Preferred device type

        Returns:
            str: Selected device name
        """
        if device_type == DeviceType.AUTO:
            # Auto-select: prefer GPU if available
            if "GPU" in self.available_devices:
                device = "GPU"
            else:
                device = "CPU"
        else:
            # Use specified device if available
            device = device_type.value
            if device not in self.available_devices:
                logger.warning(f"Requested device {device} not available, falling back to CPU")
                device = "CPU"

        # Store current device
        self.current_device = device

        # Get device info
        try:
            self.device_info = self._get_device_info(device)
        except Exception as e:
            logger.error(f"Error getting device info: {str(e)}")

        logger.info(f"Selected device: {device}")
        return device

    def _get_device_info(self, device):
        """
        Get detailed information about a device

        Args:
            device (str): Device name

        Returns:
            dict: Device properties
        """
        info = {}

        try:
            # Get common properties
            supported_properties = self.core.get_property(device, "SUPPORTED_PROPERTIES")
            info["supported_properties"] = supported_properties

            # Get device name
            if "FULL_DEVICE_NAME" in supported_properties:
                info["name"] = self.core.get_property(device, "FULL_DEVICE_NAME")

            # Get optimization capabilities
            if "OPTIMIZATION_CAPABILITIES" in supported_properties:
                info["optimization_capabilities"] = self.core.get_property(device, "OPTIMIZATION_CAPABILITIES")

            # Get performance-related properties
            if "RANGE_FOR_STREAMS" in supported_properties:
                info["streams_range"] = self.core.get_property(device, "RANGE_FOR_STREAMS")

            if "RANGE_FOR_ASYNC_INFER_REQUESTS" in supported_properties:
                info["async_requests_range"] = self.core.get_property(device, "RANGE_FOR_ASYNC_INFER_REQUESTS")

            # Device-specific properties
            if device == "CPU":
                if "CPU_THREADS_NUM" in supported_properties:
                    info["threads"] = self.core.get_property(device, "CPU_THREADS_NUM")

                # Get CPU optimizations
                if "OPTIMIZATION_CAPABILITIES" in supported_properties:
                    optimizations = self.core.get_property(device, "OPTIMIZATION_CAPABILITIES")
                    info["cpu_features"] = optimizations

            elif device == "GPU":
                # Get GPU memory
                if "AVAILABLE_DEVICES" in supported_properties:
                    info["available_devices"] = self.core.get_property(device, "AVAILABLE_DEVICES")

        except Exception as e:
            logger.error(f"Error getting {device} info: {str(e)}")

        return info

    def get_optimal_config(self, device=None):
        """
        Get optimal configuration for specified device

        Args:
            device (str): Device name (uses current device if None)

        Returns:
            dict: Device configuration
        """
        if device is None:
            device = self.current_device or self.select_device()

        config = {}

        # Set performance hint for throughput
        config["PERFORMANCE_HINT"] = "THROUGHPUT"

        # Device-specific configurations
        if device == "CPU":
            # Set CPU threads to optimal value
            config["CPU_THROUGHPUT_STREAMS"] = "AUTO"

            # Enable CPU optimizations if available
            if "cpu_features" in self.device_info:
                features = self.device_info["cpu_features"]
                if "WINOGRAD" in features:
                    config["CPU_WINOGRAD"] = "YES"

        elif device == "GPU":
            # Set GPU streams
            config["GPU_THROUGHPUT_STREAMS"] = "AUTO"

        logger.info(f"Optimal config for {device}: {config}")
        return config

    def get_device_status(self):
        """
        Get current device status

        Returns:
            dict: Device status information
        """
        if not self.current_device:
            return {"status": "not_initialized"}

        status = {
            "device": self.current_device,
            "info": self.device_info
        }

        return status


# Singleton instance
_device_manager = None

def get_device_manager():
    """
    Get or create device manager singleton

    Returns:
        DeviceManager: Device manager instance
    """
    global _device_manager
    if _device_manager is None:
        _device_manager = DeviceManager()
    return _device_manager
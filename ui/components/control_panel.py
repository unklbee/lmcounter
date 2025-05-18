# ui/components/control_panel.py
# -*- coding: utf-8 -*-

"""
Control Panel component for Vehicle Counter application
Provides UI for configuring and controlling the application
"""

import os
from pathlib import Path
import cv2
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QGroupBox, QFormLayout, QLineEdit, QSpinBox,
    QDoubleSpinBox, QCheckBox, QTabWidget, QFileDialog,
    QScrollArea, QFrame, QSplitter, QMessageBox, QRadioButton
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QIcon

from config.settings import (
    MODELS_DIR, DEFAULT_CONF_THRESHOLD, DEFAULT_NMS_THRESHOLD,
    VEHICLE_CLASSES, COLORS
)
from utils.preset_manager import get_preset_manager
from utils.device_manager import get_device_manager, DeviceType

class ControlPanel(QWidget):
    """Control panel for vehicle counter application"""

    # Signals
    source_changed = pyqtSignal(str, str, dict)  # source_type, source_path, options
    model_changed = pyqtSignal(str, str)  # model_path, device
    detection_settings_changed = pyqtSignal(float, float)  # conf_threshold, nms_threshold
    tracker_settings_changed = pyqtSignal(dict)  # tracker_settings

    start_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()
    pause_clicked = pyqtSignal(bool)  # paused

    save_preset_clicked = pyqtSignal(str)  # preset_path
    load_preset_clicked = pyqtSignal(str)  # preset_path

    edit_roi_clicked = pyqtSignal()
    edit_line_clicked = pyqtSignal()
    finish_editing_clicked = pyqtSignal()
    cancel_editing_clicked = pyqtSignal()

    def __init__(self, parent=None):
        """Initialize control panel"""
        super().__init__(parent)

        # Core components (will be set later)
        self.detector = None
        self.tracker = None
        self.counter = None
        self.roi_manager = None

        # Get utility managers
        self.preset_manager = get_preset_manager()
        self.device_manager = get_device_manager()

        # Set size policy
        self.setMinimumWidth(280)
        self.setMaximumWidth(400)

        # Initialize UI
        self.init_ui()

    def init_ui(self):
        """Initialize user interface"""
        # Main layout
        self.main_layout = QVBoxLayout(self)

        # Create scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        # Create content widget
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        scroll.setWidget(content)

        # Add scroll area to main layout
        self.main_layout.addWidget(scroll)

        # Create tab widget for settings
        self.tabs = QTabWidget()
        self.content_layout.addWidget(self.tabs)

        # Add tabs
        self.create_source_tab()
        self.create_detection_tab()
        self.create_tracking_tab()
        self.create_counter_tab()
        self.create_output_tab()

        # Control buttons
        self.create_control_buttons()

        # Status section
        self.create_status_section()

    def create_source_tab(self):
        """Create video source tab"""
        source_tab = QWidget()
        layout = QVBoxLayout(source_tab)

        # Source type
        source_group = QGroupBox("Video Source")
        source_layout = QFormLayout()

        self.source_type_combo = QComboBox()
        self.source_type_combo.addItem("File", "file")
        self.source_type_combo.addItem("RTSP Stream", "rtsp")
        self.source_type_combo.addItem("Webcam", "webcam")
        self.source_type_combo.currentIndexChanged.connect(self.on_source_type_changed)
        source_layout.addRow("Source Type:", self.source_type_combo)

        # Source path
        self.source_path_layout = QHBoxLayout()
        self.source_path_edit = QLineEdit()
        self.source_path_layout.addWidget(self.source_path_edit)

        self.source_browse_btn = QPushButton("Browse")
        self.source_browse_btn.clicked.connect(self.browse_source)
        self.source_path_layout.addWidget(self.source_browse_btn)

        source_layout.addRow("Source Path:", self.source_path_layout)

        # Webcam options (initially hidden)
        self.webcam_options = QWidget()
        webcam_layout = QFormLayout(self.webcam_options)

        self.webcam_id_spin = QSpinBox()
        self.webcam_id_spin.setRange(0, 10)
        webcam_layout.addRow("Camera ID:", self.webcam_id_spin)

        self.webcam_options.setVisible(False)
        source_layout.addRow("", self.webcam_options)

        # RTSP options (initially hidden)
        self.rtsp_options = QWidget()
        rtsp_layout = QFormLayout(self.rtsp_options)

        self.rtsp_reconnect_spin = QSpinBox()
        self.rtsp_reconnect_spin.setRange(1, 30)
        self.rtsp_reconnect_spin.setValue(5)
        rtsp_layout.addRow("Reconnect Interval (s):", self.rtsp_reconnect_spin)

        self.rtsp_options.setVisible(False)
        source_layout.addRow("", self.rtsp_options)

        # File options (initially visible)
        self.file_options = QWidget()
        file_layout = QFormLayout(self.file_options)

        self.file_loop_check = QCheckBox("Loop Video")
        file_layout.addRow("", self.file_loop_check)

        source_layout.addRow("", self.file_options)

        # Apply source button
        self.apply_source_btn = QPushButton("Apply Source")
        self.apply_source_btn.clicked.connect(self.apply_source)
        source_layout.addRow("", self.apply_source_btn)

        source_group.setLayout(source_layout)
        layout.addWidget(source_group)

        # Add stretch at the end
        layout.addStretch()

        # Add tab
        self.tabs.addTab(source_tab, "Source")

    def create_detection_tab(self):
        """Create detection settings tab"""
        detection_tab = QWidget()
        layout = QVBoxLayout(detection_tab)

        # Model selection
        model_group = QGroupBox("Detection Model")
        model_layout = QFormLayout()

        # Model path
        self.model_path_layout = QHBoxLayout()
        self.model_path_edit = QLineEdit()
        self.model_path_edit.setReadOnly(True)
        self.model_path_layout.addWidget(self.model_path_edit)

        self.model_browse_btn = QPushButton("Browse")
        self.model_browse_btn.clicked.connect(self.browse_model)
        self.model_path_layout.addWidget(self.model_browse_btn)

        model_layout.addRow("Model Path:", self.model_path_layout)

        # Device selection
        self.device_combo = QComboBox()
        available_devices = self.device_manager.available_devices

        self.device_combo.addItem("CPU", "CPU")
        if "GPU" in available_devices:
            self.device_combo.addItem("GPU", "GPU")
            self.device_combo.setCurrentIndex(1)  # Default to GPU if available

        model_layout.addRow("Device:", self.device_combo)

        # Thresholds
        self.conf_threshold_spin = QDoubleSpinBox()
        self.conf_threshold_spin.setRange(0.1, 1.0)
        self.conf_threshold_spin.setSingleStep(0.05)
        self.conf_threshold_spin.setValue(DEFAULT_CONF_THRESHOLD)
        model_layout.addRow("Confidence Threshold:", self.conf_threshold_spin)

        self.nms_threshold_spin = QDoubleSpinBox()
        self.nms_threshold_spin.setRange(0.1, 1.0)
        self.nms_threshold_spin.setSingleStep(0.05)
        self.nms_threshold_spin.setValue(DEFAULT_NMS_THRESHOLD)
        model_layout.addRow("NMS Threshold:", self.nms_threshold_spin)

        # Async inference option
        self.async_inference_check = QCheckBox("Use Async Inference")
        self.async_inference_check.setChecked(True)
        model_layout.addRow("", self.async_inference_check)

        # Apply model settings button
        self.apply_model_btn = QPushButton("Apply Model Settings")
        self.apply_model_btn.clicked.connect(self.apply_model_settings)
        model_layout.addRow("", self.apply_model_btn)

        model_group.setLayout(model_layout)
        layout.addWidget(model_group)

        # Vehicle classes group
        classes_group = QGroupBox("Vehicle Classes")
        classes_layout = QVBoxLayout()

        # Create checkboxes for each class
        self.class_checkboxes = {}
        for class_id, class_name in VEHICLE_CLASSES.items():
            checkbox = QCheckBox(class_name)
            checkbox.setChecked(True)
            color = COLORS.get(class_name, (0, 255, 0))
            style = f"color: rgb({color[2]}, {color[1]}, {color[0]});"
            checkbox.setStyleSheet(style)
            classes_layout.addWidget(checkbox)
            self.class_checkboxes[class_id] = checkbox

        classes_group.setLayout(classes_layout)
        layout.addWidget(classes_group)

        # Add stretch at the end
        layout.addStretch()

        # Add tab
        self.tabs.addTab(detection_tab, "Detection")

    def create_tracking_tab(self):
        """Create tracking settings tab"""
        tracking_tab = QWidget()
        layout = QVBoxLayout(tracking_tab)

        # Tracking settings
        tracking_group = QGroupBox("Tracker Settings")
        tracking_layout = QFormLayout()

        # Max disappeared frames
        self.max_disappeared_spin = QSpinBox()
        self.max_disappeared_spin.setRange(1, 50)
        self.max_disappeared_spin.setValue(10)
        tracking_layout.addRow("Max Disappeared Frames:", self.max_disappeared_spin)

        # IoU threshold
        self.iou_threshold_spin = QDoubleSpinBox()
        self.iou_threshold_spin.setRange(0.1, 1.0)
        self.iou_threshold_spin.setSingleStep(0.05)
        self.iou_threshold_spin.setValue(0.3)
        tracking_layout.addRow("Min IoU Threshold:", self.iou_threshold_spin)

        # Max distance
        self.max_distance_spin = QSpinBox()
        self.max_distance_spin.setRange(50, 500)
        self.max_distance_spin.setSingleStep(10)
        self.max_distance_spin.setValue(150)
        tracking_layout.addRow("Max Distance:", self.max_distance_spin)

        # Apply tracking settings button
        self.apply_tracking_btn = QPushButton("Apply Tracking Settings")
        self.apply_tracking_btn.clicked.connect(self.apply_tracking_settings)
        tracking_layout.addRow("", self.apply_tracking_btn)

        tracking_group.setLayout(tracking_layout)
        layout.addWidget(tracking_group)

        # Visualization options
        visual_group = QGroupBox("Visualization")
        visual_layout = QVBoxLayout()

        self.show_boxes_check = QCheckBox("Show Bounding Boxes")
        self.show_boxes_check.setChecked(True)
        visual_layout.addWidget(self.show_boxes_check)

        self.show_ids_check = QCheckBox("Show Object IDs")
        self.show_ids_check.setChecked(True)
        visual_layout.addWidget(self.show_ids_check)

        self.show_tracks_check = QCheckBox("Show Trajectories")
        self.show_tracks_check.setChecked(True)
        visual_layout.addWidget(self.show_tracks_check)

        visual_group.setLayout(visual_layout)
        layout.addWidget(visual_group)

        # Add stretch at the end
        layout.addStretch()

        # Add tab
        self.tabs.addTab(tracking_tab, "Tracking")

    def create_counter_tab(self):
        """Create counter settings tab"""
        counter_tab = QWidget()
        layout = QVBoxLayout(counter_tab)

        # ROI Editor Group
        roi_group = QGroupBox("Region of Interest (ROI)")
        roi_layout = QVBoxLayout()

        # ROI editing buttons
        roi_buttons_layout = QHBoxLayout()

        self.create_roi_btn = QPushButton("Create ROI")
        self.create_roi_btn.clicked.connect(self.edit_roi_clicked)
        roi_buttons_layout.addWidget(self.create_roi_btn)

        self.create_line_btn = QPushButton("Create Line")
        self.create_line_btn.clicked.connect(self.edit_line_clicked)
        roi_buttons_layout.addWidget(self.create_line_btn)

        roi_layout.addLayout(roi_buttons_layout)

        # Editing controls (initially hidden)
        self.editing_controls = QWidget()
        editing_layout = QVBoxLayout(self.editing_controls)

        editing_label = QLabel("Editing Mode:")
        editing_label.setStyleSheet("font-weight: bold; color: red;")
        editing_layout.addWidget(editing_label)

        editing_buttons = QHBoxLayout()

        self.finish_edit_btn = QPushButton("Finish")
        self.finish_edit_btn.clicked.connect(self.finish_editing_clicked)
        editing_buttons.addWidget(self.finish_edit_btn)

        self.cancel_edit_btn = QPushButton("Cancel")
        self.cancel_edit_btn.clicked.connect(self.cancel_editing_clicked)
        editing_buttons.addWidget(self.cancel_edit_btn)

        editing_layout.addLayout(editing_buttons)
        self.editing_controls.setVisible(False)

        roi_layout.addWidget(self.editing_controls)

        # ROI/Line List
        roi_list_label = QLabel("Defined ROIs and Lines:")
        roi_layout.addWidget(roi_list_label)

        self.roi_list_widget = QFrame()
        self.roi_list_widget.setFrameShape(QFrame.StyledPanel)
        self.roi_list_widget.setMinimumHeight(100)
        roi_layout.addWidget(self.roi_list_widget)

        roi_group.setLayout(roi_layout)
        layout.addWidget(roi_group)

        # Counter Options
        counter_group = QGroupBox("Counting Options")
        counter_layout = QVBoxLayout()

        self.show_counts_check = QCheckBox("Show Counts on Video")
        self.show_counts_check.setChecked(True)
        counter_layout.addWidget(self.show_counts_check)

        self.show_events_check = QCheckBox("Show Count Events")
        self.show_events_check.setChecked(True)
        counter_layout.addWidget(self.show_events_check)

        counter_group.setLayout(counter_layout)
        layout.addWidget(counter_group)

        # Add stretch at the end
        layout.addStretch()

        # Add tab
        self.tabs.addTab(counter_tab, "Counter")

    def create_output_tab(self):
        """Create output settings tab"""
        output_tab = QWidget()
        layout = QVBoxLayout(output_tab)

        # Video output group
        video_group = QGroupBox("Video Output")
        video_layout = QFormLayout()

        self.save_video_check = QCheckBox("Save Video")
        video_layout.addRow("", self.save_video_check)

        # Output path
        self.output_path_layout = QHBoxLayout()
        self.output_path_edit = QLineEdit()
        self.output_path_layout.addWidget(self.output_path_edit)

        self.output_browse_btn = QPushButton("Browse")
        self.output_browse_btn.clicked.connect(self.browse_output)
        self.output_path_layout.addWidget(self.output_browse_btn)

        video_layout.addRow("Output Path:", self.output_path_layout)

        video_group.setLayout(video_layout)
        layout.addWidget(video_group)

        # Database group
        db_group = QGroupBox("Database Storage")
        db_layout = QVBoxLayout()

        self.save_to_db_check = QCheckBox("Save Counts to Database")
        self.save_to_db_check.setChecked(True)
        db_layout.addWidget(self.save_to_db_check)

        db_group.setLayout(db_layout)
        layout.addWidget(db_group)

        # API output group
        api_group = QGroupBox("API Output")
        api_layout = QFormLayout()

        self.push_to_api_check = QCheckBox("Push Counts to API")
        api_layout.addRow("", self.push_to_api_check)

        self.api_url_edit = QLineEdit("http://localhost:8000/api/counts")
        api_layout.addRow("API URL:", self.api_url_edit)

        api_group.setLayout(api_layout)
        layout.addWidget(api_group)

        # Add stretch at the end
        layout.addStretch()

        # Add tab
        self.tabs.addTab(output_tab, "Output")

    def create_control_buttons(self):
        """Create control buttons section"""
        control_group = QGroupBox("Controls")
        control_layout = QVBoxLayout()

        # Processing control buttons
        process_buttons = QHBoxLayout()

        self.start_btn = QPushButton("Start")
        self.start_btn.setEnabled(False)  # Disabled until source is set
        self.start_btn.clicked.connect(self.start_clicked)
        process_buttons.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_clicked)
        process_buttons.addWidget(self.stop_btn)

        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setEnabled(False)
        self.pause_btn.setCheckable(True)
        self.pause_btn.toggled.connect(self.on_pause_toggled)
        process_buttons.addWidget(self.pause_btn)

        control_layout.addLayout(process_buttons)

        # Preset buttons
        preset_buttons = QHBoxLayout()

        self.save_preset_btn = QPushButton("Save Preset")
        self.save_preset_btn.clicked.connect(self.save_preset)
        preset_buttons.addWidget(self.save_preset_btn)

        self.load_preset_btn = QPushButton("Load Preset")
        self.load_preset_btn.clicked.connect(self.load_preset)
        preset_buttons.addWidget(self.load_preset_btn)

        control_layout.addLayout(preset_buttons)

        control_group.setLayout(control_layout)
        self.content_layout.addWidget(control_group)

    def create_status_section(self):
        """Create status section"""
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout()

        # Status label
        self.status_label = QLabel("Idle")
        status_layout.addWidget(self.status_label)

        # Statistics frame
        self.stats_frame = QFrame()
        self.stats_frame.setFrameShape(QFrame.StyledPanel)
        self.stats_layout = QFormLayout(self.stats_frame)

        self.fps_label = QLabel("0.0")
        self.stats_layout.addRow("FPS:", self.fps_label)

        self.inf_time_label = QLabel("0.0 ms")
        self.stats_layout.addRow("Inference Time:", self.inf_time_label)

        self.detection_count_label = QLabel("0")
        self.stats_layout.addRow("Detected Objects:", self.detection_count_label)

        self.vehicle_count_label = QLabel("0")
        self.stats_layout.addRow("Total Counted:", self.vehicle_count_label)

        status_layout.addWidget(self.stats_frame)

        status_group.setLayout(status_layout)
        self.content_layout.addWidget(status_group)

    def on_source_type_changed(self, index):
        """Handle source type change"""
        source_type = self.source_type_combo.currentData()

        # Show/hide appropriate options
        self.file_options.setVisible(source_type == "file")
        self.rtsp_options.setVisible(source_type == "rtsp")
        self.webcam_options.setVisible(source_type == "webcam")

        # Change browse button behavior
        self.source_browse_btn.setVisible(source_type == "file")

        # Update source path field
        if source_type == "webcam":
            self.source_path_edit.setText("0")
            self.source_path_edit.setReadOnly(True)
        elif source_type == "rtsp":
            self.source_path_edit.setText("rtsp://")
            self.source_path_edit.setReadOnly(False)
        else:
            self.source_path_edit.setReadOnly(False)

    def browse_source(self):
        """Browse for video source file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Video File", str(Path.home()),
            "Video Files (*.mp4 *.avi *.mkv *.mov);;All Files (*.*)"
        )

        if file_path:
            self.source_path_edit.setText(file_path)

    def browse_model(self):
        """Browse for model file"""
        model_path, _ = QFileDialog.getOpenFileName(
            self, "Select Model File", str(MODELS_DIR),
            "OpenVINO Models (*.xml);;All Files (*.*)"
        )

        if model_path:
            self.model_path_edit.setText(model_path)

    def browse_output(self):
        """Browse for output directory"""
        output_path, _ = QFileDialog.getSaveFileName(
            self, "Select Output File", str(Path.home()),
            "Video Files (*.mp4);;All Files (*.*)"
        )

        if output_path:
            self.output_path_edit.setText(output_path)

    def apply_source(self):
        """Apply video source settings"""
        source_type = self.source_type_combo.currentData()
        source_path = self.source_path_edit.text().strip()

        if not source_path:
            QMessageBox.warning(self, "Warning", "Please enter a valid source path")
            return

        # Get source-specific options
        options = {}

        if source_type == "file":
            options["loop"] = self.file_loop_check.isChecked()
        elif source_type == "rtsp":
            options["reconnect_interval"] = self.rtsp_reconnect_spin.value()
        elif source_type == "webcam":
            try:
                # Convert to int for webcam ID
                source_path = str(int(self.webcam_id_spin.value()))
            except ValueError:
                source_path = "0"

        # Enable start button
        self.enable_start(True)

        # Emit signal
        self.source_changed.emit(source_type, source_path, options)

    def apply_model_settings(self):
        """Apply model settings"""
        model_path = self.model_path_edit.text().strip()
        device = self.device_combo.currentData()

        if not model_path:
            QMessageBox.warning(self, "Warning", "Please select a model file")
            return

        # Update detector settings if available
        if self.detector:
            self.detector.model_path = model_path
            self.detector.device = device
            self.detector.conf_threshold = self.conf_threshold_spin.value()
            self.detector.nms_threshold = self.nms_threshold_spin.value()
            self.detector.is_async = self.async_inference_check.isChecked()

            # Reinitialize model
            try:
                self.detector._initialize_model()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to initialize model: {str(e)}")
                return

        # Emit signals
        self.model_changed.emit(model_path, device)
        self.detection_settings_changed.emit(
            self.conf_threshold_spin.value(),
            self.nms_threshold_spin.value()
        )

    def apply_tracking_settings(self):
        """Apply tracking settings"""
        if not self.tracker:
            return

        # Update tracker settings
        self.tracker.max_disappeared = self.max_disappeared_spin.value()
        self.tracker.min_iou_threshold = self.iou_threshold_spin.value()
        self.tracker.max_distance = self.max_distance_spin.value()

        # Emit signal
        settings = {
            "max_disappeared": self.tracker.max_disappeared,
            "min_iou_threshold": self.tracker.min_iou_threshold,
            "max_distance": self.tracker.max_distance
        }
        self.tracker_settings_changed.emit(settings)

    def save_preset(self):
        """Save current settings to preset"""
        # Create preset data structure
        preset = self.preset_manager.create_empty_preset()

        # Update with current settings

        # Source settings
        preset["source"] = {
            "type": self.source_type_combo.currentData(),
            "path": self.source_path_edit.text().strip(),
            "options": {}
        }

        # Source-specific options
        if preset["source"]["type"] == "file":
            preset["source"]["options"]["loop"] = self.file_loop_check.isChecked()
        elif preset["source"]["type"] == "rtsp":
            preset["source"]["options"]["reconnect_interval"] = self.rtsp_reconnect_spin.value()

        # Detector settings
        preset["detector"] = {
            "model": self.model_path_edit.text().strip(),
            "device": self.device_combo.currentData(),
            "conf_threshold": self.conf_threshold_spin.value(),
            "nms_threshold": self.nms_threshold_spin.value(),
            "async_mode": self.async_inference_check.isChecked()
        }

        # Tracker settings
        preset["tracker"] = {
            "max_disappeared": self.max_disappeared_spin.value(),
            "min_iou_threshold": self.iou_threshold_spin.value(),
            "max_distance": self.max_distance_spin.value()
        }

        # Display settings
        preset["display"] = {
            "show_boxes": self.show_boxes_check.isChecked(),
            "show_ids": self.show_ids_check.isChecked(),
            "show_tracks": self.show_tracks_check.isChecked(),
            "show_counts": self.show_counts_check.isChecked(),
            "show_events": self.show_events_check.isChecked()
        }

        # Output settings
        preset["output"] = {
            "save_video": self.save_video_check.isChecked(),
            "output_path": self.output_path_edit.text().strip(),
            "push_to_api": self.push_to_api_check.isChecked(),
            "api_endpoint": self.api_url_edit.text().strip(),
            "save_to_db": self.save_to_db_check.isChecked()
        }

        # ROIs and counting lines from roi_manager
        if self.roi_manager:
            preset["rois"] = self.roi_manager.rois
            preset["counting_lines"] = self.roi_manager.counting_lines

        # Open save dialog
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Preset", str(self.preset_manager.presets_dir),
            "JSON Files (*.json);;All Files (*.*)"
        )

        if not file_path:
            return

        # Save preset
        if self.preset_manager.save_preset(preset, file_path):
            QMessageBox.information(self, "Success", "Preset saved successfully")

            # Emit signal
            self.save_preset_clicked.emit(file_path)

    def load_preset(self):
        """Load settings from preset"""
        # Open load dialog
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Preset", str(self.preset_manager.presets_dir),
            "JSON Files (*.json);;All Files (*.*)"
        )

        if not file_path:
            return

        # Load preset
        preset = self.preset_manager.load_preset(path=file_path)
        if not preset:
            QMessageBox.warning(self, "Warning", "Failed to load preset")
            return

        # Apply preset settings to UI
        self.apply_preset_to_ui(preset)

        # Emit signal
        self.load_preset_clicked.emit(file_path)

    def apply_preset_to_ui(self, preset):
        """
        Apply preset settings to UI controls

        Args:
            preset (dict): Preset data
        """
        try:
            # Source settings
            source = preset.get("source", {})
            source_type = source.get("type", "file")
            index = self.source_type_combo.findData(source_type)
            if index >= 0:
                self.source_type_combo.setCurrentIndex(index)

            self.source_path_edit.setText(source.get("path", ""))

            # Source-specific options
            options = source.get("options", {})
            if source_type == "file":
                self.file_loop_check.setChecked(options.get("loop", False))
            elif source_type == "rtsp":
                self.rtsp_reconnect_spin.setValue(options.get("reconnect_interval", 5))

            # Detector settings
            detector = preset.get("detector", {})
            self.model_path_edit.setText(detector.get("model", ""))

            device_index = self.device_combo.findData(detector.get("device", "CPU"))
            if device_index >= 0:
                self.device_combo.setCurrentIndex(device_index)

            self.conf_threshold_spin.setValue(detector.get("conf_threshold", DEFAULT_CONF_THRESHOLD))
            self.nms_threshold_spin.setValue(detector.get("nms_threshold", DEFAULT_NMS_THRESHOLD))
            self.async_inference_check.setChecked(detector.get("async_mode", True))

            # Tracker settings
            tracker = preset.get("tracker", {})
            self.max_disappeared_spin.setValue(tracker.get("max_disappeared", 10))
            self.iou_threshold_spin.setValue(tracker.get("min_iou_threshold", 0.3))
            self.max_distance_spin.setValue(tracker.get("max_distance", 150))

            # Display settings
            display = preset.get("display", {})
            self.show_boxes_check.setChecked(display.get("show_boxes", True))
            self.show_ids_check.setChecked(display.get("show_ids", True))
            self.show_tracks_check.setChecked(display.get("show_tracks", True))
            self.show_counts_check.setChecked(display.get("show_counts", True))
            self.show_events_check.setChecked(display.get("show_events", True))

            # Output settings
            output = preset.get("output", {})
            self.save_video_check.setChecked(output.get("save_video", False))
            self.output_path_edit.setText(output.get("output_path", ""))
            self.push_to_api_check.setChecked(output.get("push_to_api", False))
            self.api_url_edit.setText(output.get("api_endpoint", "http://localhost:8000/api/counts"))
            self.save_to_db_check.setChecked(output.get("save_to_db", True))

            # Apply source settings
            self.apply_source()

            # Apply model settings
            self.apply_model_settings()

            # Apply tracker settings
            self.apply_tracking_settings()

            QMessageBox.information(self, "Success", "Preset loaded successfully")

        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Error applying preset: {str(e)}")

    def on_pause_toggled(self, paused):
        """Handle pause button toggle"""
        if paused:
            self.pause_btn.setText("Resume")
        else:
            self.pause_btn.setText("Pause")

        self.pause_clicked.emit(paused)

    def update_status(self, status):
        """
        Update status text

        Args:
            status (str): Status text
        """
        self.status_label.setText(status)

    def update_statistics(self, results):
        """
        Update statistics display

        Args:
            results (dict): Processing results
        """
        # Performance stats
        perf = results.get("performance", {})
        self.fps_label.setText(f"{perf.get('fps', 0):.1f}")
        self.inf_time_label.setText(f"{perf.get('avg_inference_time', 0):.1f} ms")

        # Detection stats
        detection = results.get("detection", {})
        self.detection_count_label.setText(str(detection.get("total", 0)))

        # Counting stats
        counting = results.get("counting", {})
        total_counted = 0

        # Sum ROI totals
        roi_totals = counting.get("roi_totals", {})
        for roi_id, count in roi_totals.items():
            total_counted += count

        # Sum line totals
        line_totals = counting.get("line_totals", {})
        for line_id, count in line_totals.items():
            total_counted += count

        self.vehicle_count_label.setText(str(total_counted))

    def set_processing_state(self, is_processing):
        """
        Update UI for processing state

        Args:
            is_processing (bool): Whether processing is active
        """
        self.start_btn.setEnabled(not is_processing)
        self.stop_btn.setEnabled(is_processing)
        self.pause_btn.setEnabled(is_processing)

        if not is_processing:
            self.pause_btn.setChecked(False)
            self.pause_btn.setText("Pause")

    def enable_start(self, enabled):
        """
        Enable or disable start button

        Args:
            enabled (bool): Whether to enable the button
        """
        self.start_btn.setEnabled(enabled)

    def set_components(self, detector, tracker, counter, roi_manager):
        """
        Set core components

        Args:
            detector: Detector instance
            tracker: Tracker instance
            counter: Counter instance
            roi_manager: ROI manager instance
        """
        self.detector = detector
        self.tracker = tracker
        self.counter = counter
        self.roi_manager = roi_manager

        # Update UI with component settings
        if detector:
            self.model_path_edit.setText(str(detector.model_path))

            device_index = self.device_combo.findData(detector.device)
            if device_index >= 0:
                self.device_combo.setCurrentIndex(device_index)

            self.conf_threshold_spin.setValue(detector.conf_threshold)
            self.nms_threshold_spin.setValue(detector.nms_threshold)
            self.async_inference_check.setChecked(detector.is_async)

        if tracker:
            self.max_disappeared_spin.setValue(tracker.max_disappeared)
            self.iou_threshold_spin.setValue(tracker.min_iou_threshold)
            self.max_distance_spin.setValue(tracker.max_distance)

        # Update ROI list
        self.update_roi_list()

    def update_roi_list(self):
        """Update ROI and line list display"""
        if not self.roi_manager:
            return

        # Clear current list
        while self.roi_list_widget.layout():
            layout = self.roi_list_widget.layout()
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()
            layout.deleteLater()

        # Create new layout
        list_layout = QVBoxLayout(self.roi_list_widget)

        # Add ROIs
        if self.roi_manager.rois:
            roi_label = QLabel("Regions of Interest:")
            roi_label.setStyleSheet("font-weight: bold;")
            list_layout.addWidget(roi_label)

            for roi_id, roi in self.roi_manager.rois.items():
                roi_item = QLabel(f"• {roi['name']} ({roi['direction']})")
                list_layout.addWidget(roi_item)

        # Add lines
        if self.roi_manager.counting_lines:
            line_label = QLabel("Counting Lines:")
            line_label.setStyleSheet("font-weight: bold;")
            list_layout.addWidget(line_label)

            for line_id, line in self.roi_manager.counting_lines.items():
                line_item = QLabel(f"• {line['name']} ({line['direction']})")
                list_layout.addWidget(line_item)

        # Add empty state if no ROIs or lines
        if not self.roi_manager.rois and not self.roi_manager.counting_lines:
            empty_label = QLabel("No ROIs or counting lines defined")
            empty_label.setStyleSheet("font-style: italic; color: gray;")
            list_layout.addWidget(empty_label)

        # Add stretch at the end
        list_layout.addStretch()
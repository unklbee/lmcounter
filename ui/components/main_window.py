# ui/components/main_window.py
# -*- coding: utf-8 -*-

"""
Main Window component for Vehicle Counter application
Provides the main application window with menus, toolbars, and layout management
"""
import logging
import os
import sys
import traceback
from pathlib import Path
from PyQt5.QtWidgets import (
    QMainWindow, QAction, QToolBar, QMenuBar, QStatusBar, QDockWidget,
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QFileDialog,
    QMessageBox, QLabel, QDialog, QDialogButtonBox, QFormLayout,
    QLineEdit, QTextEdit, QApplication, QShortcut, QMenu
)
from PyQt5.QtCore import Qt, QSize, QSettings, pyqtSignal, QTimer
from PyQt5.QtGui import QIcon, QKeySequence

from ui.components.stream_view import VideoStreamView
from ui.components.control_panel import ControlPanel
from ui.components.preset_manager import PresetManagerWidget

from utils.logger import get_logger
from utils.preset_manager import get_preset_manager
from config.settings import VERSION

# Setup logger
logger = get_logger(__name__)

class AboutDialog(QDialog):
    """About dialog for the application"""

    def __init__(self, parent=None):
        """Initialize about dialog"""
        super().__init__(parent)

        self.setWindowTitle("About Vehicle Counter")
        self.setMinimumWidth(400)

        # Layout
        layout = QVBoxLayout(self)

        # Title
        title_label = QLabel("Vehicle Counter")
        title_font = title_label.font()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # Version
        version_label = QLabel(f"Version {VERSION}")
        version_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(version_label)

        # Description
        desc_label = QLabel(
            "An application for counting vehicles in videos and streams using "
            "computer vision and deep learning."
        )
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_label)

        # Separator
        separator = QWidget()
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: #c0c0c0;")
        layout.addWidget(separator)

        # Technologies
        tech_label = QLabel(
            "Technologies: OpenVINO, OpenCV, PyQt5"
        )
        tech_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(tech_label)

        # Button box
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)


class MainWindow(QMainWindow):
    """Main application window"""

    # Signals
    preset_loaded = pyqtSignal(dict)  # preset data

    def __init__(self):
        """Initialize main window"""
        super().__init__()

        # Settings
        self.settings = QSettings("VehicleCounter", "Application")

        # Get preset manager
        self.preset_manager = get_preset_manager()

        # Initialize UI without connecting signals
        self.init_ui()

        # Restore window state
        self.restore_window_state()

        # Connect signals AFTER all components are created
        self.connect_signals()

        # Auto-save timer (every 5 minutes)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self.auto_save_state)
        self.autosave_timer.start(300000)  # 5 minutes in milliseconds

        logger.info("Main window initialized")

    def init_ui(self):
        """Initialize user interface"""
        # Window properties
        self.setWindowTitle("Vehicle Counter")
        self.setMinimumSize(1024, 768)

        # Central widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # Main layout
        self.main_layout = QHBoxLayout(self.central_widget)

        # Create splitter for resizable sections
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_layout.addWidget(self.main_splitter)

        # Stream view (left side)
        self.stream_view = VideoStreamView()
        self.main_splitter.addWidget(self.stream_view)

        # Control panel (right side)
        self.control_panel = ControlPanel()
        self.main_splitter.addWidget(self.control_panel)

        # Set initial splitter sizes (70% stream, 30% control panel)
        self.main_splitter.setSizes([700, 300])

        # Create menus
        self.create_menus()

        # Create toolbar
        self.create_toolbar()

        # Create status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready")

        # Set up dock widgets
        self.setup_dock_widgets()

        # Set up keyboard shortcuts
        self.setup_shortcuts()

        # Note: DO NOT call connect_signals() here

    def create_menus(self):
        """Create application menus"""
        # File menu
        file_menu = self.menuBar().addMenu("&File")

        # Open source
        open_action = QAction("&Open Video...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_video_file)
        file_menu.addAction(open_action)

        # Open RTSP stream
        rtsp_action = QAction("Open RTSP &Stream...", self)
        rtsp_action.triggered.connect(self.open_rtsp_stream)
        file_menu.addAction(rtsp_action)

        # Open webcam
        webcam_action = QAction("Open &Webcam", self)
        webcam_action.triggered.connect(self.open_webcam)
        file_menu.addAction(webcam_action)

        file_menu.addSeparator()

        # Preset submenu
        preset_menu = file_menu.addMenu("&Presets")

        # Manage presets
        manage_presets_action = QAction("&Manage Presets...", self)
        manage_presets_action.triggered.connect(self.show_preset_manager)
        preset_menu.addAction(manage_presets_action)

        # Save preset
        save_preset_action = QAction("&Save Preset...", self)
        save_preset_action.triggered.connect(self.save_preset)
        preset_menu.addAction(save_preset_action)

        # Load preset
        load_preset_action = QAction("&Load Preset...", self)
        load_preset_action.triggered.connect(self.load_preset)
        preset_menu.addAction(load_preset_action)

        # Save as default
        save_default_action = QAction("Save as &Default", self)
        save_default_action.triggered.connect(self.save_default_preset)
        preset_menu.addAction(save_default_action)

        preset_menu.addSeparator()

        # Recent presets submenu
        self.recent_presets_menu = preset_menu.addMenu("&Recent Presets")
        self.update_recent_presets_menu()

        file_menu.addSeparator()

        # Exit action
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit menu
        edit_menu = self.menuBar().addMenu("&Edit")

        # Preferences
        pref_action = QAction("&Preferences...", self)
        pref_action.triggered.connect(self.show_preferences)
        edit_menu.addAction(pref_action)

        # View menu
        view_menu = self.menuBar().addMenu("&View")

        # Toggle fullscreen
        fullscreen_action = QAction("&Fullscreen", self)
        fullscreen_action.setShortcut("F11")
        fullscreen_action.setCheckable(True)
        fullscreen_action.triggered.connect(self.toggle_fullscreen)
        view_menu.addAction(fullscreen_action)

        # Toggle control panel
        toggle_control_action = QAction("Toggle &Control Panel", self)
        toggle_control_action.setShortcut("F10")
        toggle_control_action.triggered.connect(self.toggle_control_panel)
        view_menu.addAction(toggle_control_action)

        # Toggle grid
        grid_action = QAction("Show &Grid", self)
        grid_action.setCheckable(True)
        grid_action.triggered.connect(self.toggle_grid)
        view_menu.addAction(grid_action)

        # Toggle info overlay
        info_action = QAction("Show &Info Overlay", self)
        info_action.setCheckable(True)
        info_action.setChecked(True)
        info_action.triggered.connect(self.toggle_info)
        view_menu.addAction(info_action)

        # Tools menu
        tools_menu = self.menuBar().addMenu("&Tools")

        # Edit ROI
        roi_action = QAction("Edit &ROI", self)
        roi_action.triggered.connect(self.edit_roi)
        tools_menu.addAction(roi_action)

        # Edit Line
        line_action = QAction("Edit &Line", self)
        line_action.triggered.connect(self.edit_line)
        tools_menu.addAction(line_action)

        tools_menu.addSeparator()

        # Export counts
        export_action = QAction("&Export Counts...", self)
        export_action.triggered.connect(self.export_counts)
        tools_menu.addAction(export_action)

        # Help menu
        help_menu = self.menuBar().addMenu("&Help")

        # About
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def create_toolbar(self):
        """Create main toolbar"""
        self.toolbar = QToolBar("Main Toolbar")
        self.toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(self.toolbar)

        # Start processing
        start_action = QAction("Start", self)
        start_action.triggered.connect(self.start_processing)
        self.toolbar.addAction(start_action)

        # Stop processing
        stop_action = QAction("Stop", self)
        stop_action.triggered.connect(self.stop_processing)
        self.toolbar.addAction(stop_action)

        # Pause processing
        pause_action = QAction("Pause", self)
        pause_action.setCheckable(True)
        pause_action.triggered.connect(self.pause_processing)
        self.toolbar.addAction(pause_action)

        self.toolbar.addSeparator()

        # Edit ROI
        roi_action = QAction("Edit ROI", self)
        roi_action.triggered.connect(self.edit_roi)
        self.toolbar.addAction(roi_action)

        # Edit Line
        line_action = QAction("Edit Line", self)
        line_action.triggered.connect(self.edit_line)
        self.toolbar.addAction(line_action)

        self.toolbar.addSeparator()

        # Load preset
        load_preset_action = QAction("Load Preset", self)
        load_preset_action.triggered.connect(self.load_preset)
        self.toolbar.addAction(load_preset_action)

        # Save preset
        save_preset_action = QAction("Save Preset", self)
        save_preset_action.triggered.connect(self.save_preset)
        self.toolbar.addAction(save_preset_action)

    def setup_dock_widgets(self):
        """Setup dock widgets"""
        # Preset manager dock
        self.preset_dock = QDockWidget("Preset Manager", self)
        self.preset_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self.preset_manager_widget = PresetManagerWidget(self.preset_manager)
        self.preset_dock.setWidget(self.preset_manager_widget)

        # Hide by default, can be shown from View menu
        self.preset_dock.setVisible(False)
        self.addDockWidget(Qt.RightDockWidgetArea, self.preset_dock)

        # Add to View menu
        view_menu = self.menuBar().findChild(QMenu, "View")
        if view_menu:
            view_menu.addAction(self.preset_dock.toggleViewAction())

    def setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        # F5 to start
        start_shortcut = QShortcut(QKeySequence("F5"), self)
        start_shortcut.activated.connect(self.start_processing)

        # F6 to stop
        stop_shortcut = QShortcut(QKeySequence("F6"), self)
        stop_shortcut.activated.connect(self.stop_processing)

        # Space to pause/resume
        pause_shortcut = QShortcut(QKeySequence("Space"), self)
        pause_shortcut.activated.connect(self.toggle_pause)

        # Escape to exit editing mode
        escape_shortcut = QShortcut(QKeySequence("Esc"), self)
        escape_shortcut.activated.connect(self.cancel_editing)

    def connect_signals(self):
        """Connect component signals"""
        # Connect control panel signals
        self.control_panel.source_changed.connect(self.on_source_changed)
        self.control_panel.start_clicked.connect(self.start_processing)
        self.control_panel.stop_clicked.connect(self.stop_processing)
        self.control_panel.pause_clicked.connect(self.on_pause_toggled)
        self.control_panel.save_preset_clicked.connect(self.on_preset_saved)
        self.control_panel.load_preset_clicked.connect(self.on_preset_loaded)

        # Connect ROI editing signals
        self.control_panel.edit_roi_clicked.connect(self.edit_roi)
        self.control_panel.edit_line_clicked.connect(self.edit_line)
        self.control_panel.finish_editing_clicked.connect(self.finish_editing)
        self.control_panel.cancel_editing_clicked.connect(self.cancel_editing)

        # Connect preset manager signals
        self.preset_manager_widget.preset_selected.connect(self.on_preset_selected)
        self.preset_manager_widget.preset_loaded.connect(self.on_preset_loaded)

    def restore_window_state(self):
        """Restore window position, size, and state"""
        # Restore window geometry
        geometry = self.settings.value("WindowGeometry")
        if geometry:
            self.restoreGeometry(geometry)

        # Restore window state (toolbar positions, etc.)
        state = self.settings.value("WindowState")
        if state:
            self.restoreState(state)

        # Restore splitter position
        splitter_sizes = self.settings.value("SplitterSizes")
        if splitter_sizes:
            try:
                # Convert string values to integers if needed
                if isinstance(splitter_sizes, list):
                    int_sizes = [int(size) for size in splitter_sizes]
                else:
                    # If it's not a list, use default sizes
                    int_sizes = [700, 300]  # Default 70% stream, 30% control panel

                self.main_splitter.setSizes(int_sizes)
            except (ValueError, TypeError):
                # If conversion fails, use default sizes
                self.main_splitter.setSizes([700, 300])
                logger.warning("Failed to restore splitter sizes, using defaults")

    def save_window_state(self):
        """Save window position, size, and state"""
        self.settings.setValue("WindowGeometry", self.saveGeometry())
        self.settings.setValue("WindowState", self.saveState())
        self.settings.setValue("SplitterSizes", self.main_splitter.sizes())

        logger.debug("Window state saved")

    def auto_save_state(self):
        """Auto-save window state and settings"""
        self.save_window_state()

        # Save recent presets list
        recent_presets = self.settings.value("RecentPresets", [])
        self.settings.setValue("RecentPresets", recent_presets)

        logger.debug("Auto-saved application state")

    def update_recent_presets_menu(self):
        """Update recent presets menu"""
        self.recent_presets_menu.clear()

        # Get recent presets from settings
        recent_presets = self.settings.value("RecentPresets", [])

        if not recent_presets:
            no_presets_action = QAction("No Recent Presets", self)
            no_presets_action.setEnabled(False)
            self.recent_presets_menu.addAction(no_presets_action)
            return

        # Add entries for each recent preset
        for path in recent_presets:
            name = Path(path).stem
            action = QAction(name, self)
            action.setData(path)
            action.triggered.connect(lambda checked, p=path: self.load_preset_from_path(p))
            self.recent_presets_menu.addAction(action)

        self.recent_presets_menu.addSeparator()

        # Add clear recent presets action
        clear_action = QAction("Clear Recent Presets", self)
        clear_action.triggered.connect(self.clear_recent_presets)
        self.recent_presets_menu.addAction(clear_action)

    def add_to_recent_presets(self, path):
        """Add preset path to recent presets list"""
        # Get current list
        recent_presets = self.settings.value("RecentPresets", [])

        # Convert to list if it's not already
        if not isinstance(recent_presets, list):
            recent_presets = [recent_presets] if recent_presets else []

        # Remove if already in list
        if path in recent_presets:
            recent_presets.remove(path)

        # Add to front of list
        recent_presets.insert(0, path)

        # Trim list to 10 items
        recent_presets = recent_presets[:10]

        # Save back to settings
        self.settings.setValue("RecentPresets", recent_presets)

        # Update menu
        self.update_recent_presets_menu()

    def clear_recent_presets(self):
        """Clear recent presets list"""
        self.settings.setValue("RecentPresets", [])
        self.update_recent_presets_menu()

    def open_video_file(self):
        """Open video file dialog"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Video File", str(Path.home()),
            "Video Files (*.mp4 *.avi *.mkv *.mov);;All Files (*.*)"
        )

        if file_path:
            # Set source type to file
            self.control_panel.source_type_combo.setCurrentIndex(
                self.control_panel.source_type_combo.findData("file")
            )

            # Set file path
            self.control_panel.source_path_edit.setText(file_path)

            # Apply source
            self.control_panel.apply_source()

    def open_rtsp_stream(self):
        """Open RTSP stream dialog"""
        # Create simple dialog to input RTSP URL
        dialog = QDialog(self)
        dialog.setWindowTitle("Open RTSP Stream")
        dialog.setMinimumWidth(400)

        layout = QFormLayout(dialog)

        rtsp_edit = QLineEdit("rtsp://")
        layout.addRow("RTSP URL:", rtsp_edit)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addRow(button_box)

        # Show dialog
        result = dialog.exec_()

        if result == QDialog.Accepted:
            rtsp_url = rtsp_edit.text().strip()
            if rtsp_url:
                # Set source type to RTSP
                self.control_panel.source_type_combo.setCurrentIndex(
                    self.control_panel.source_type_combo.findData("rtsp")
                )

                # Set RTSP URL
                self.control_panel.source_path_edit.setText(rtsp_url)

                # Apply source
                self.control_panel.apply_source()

    def open_webcam(self):
        """Open webcam"""
        # Set source type to webcam
        self.control_panel.source_type_combo.setCurrentIndex(
            self.control_panel.source_type_combo.findData("webcam")
        )

        # Apply source
        self.control_panel.apply_source()

    def show_preset_manager(self):
        """Show preset manager dock"""
        self.preset_dock.setVisible(True)
        self.preset_manager_widget.refresh()

    def save_preset(self):
        """Save current settings to preset"""
        self.control_panel.save_preset()

    def load_preset(self):
        """Load settings from preset file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Preset", str(self.preset_manager.presets_dir),
            "JSON Files (*.json);;All Files (*.*)"
        )

        if file_path:
            self.load_preset_from_path(file_path)

    def load_preset_from_path(self, path):
        """
        Load preset from specific path

        Args:
            path (str): Path to preset file
        """
        preset = self.preset_manager.load_preset(path=path)
        if preset:
            self.control_panel.apply_preset_to_ui(preset)
            self.add_to_recent_presets(path)
            self.statusBar.showMessage(f"Loaded preset: {Path(path).stem}")

            # Emit signal
            self.preset_loaded.emit(preset)

    def save_default_preset(self):
        """Save current settings as default preset"""
        # Get current preset data from control panel (similar to save_preset)
        preset = self.preset_manager.create_empty_preset()

        # Update with current settings from control panel
        # (Code similar to control_panel.save_preset)

        # Save as default
        if self.preset_manager.save_preset(preset, self.preset_manager.default_preset_path):
            QMessageBox.information(self, "Success", "Default preset saved successfully")
            self.statusBar.showMessage("Default preset saved")

    def show_preferences(self):
        """Show preferences dialog"""
        # Create preferences dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Preferences")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout(dialog)

        # Add preference controls here

        # Button box
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # Show dialog
        dialog.exec_()

    def toggle_fullscreen(self, checked):
        """Toggle fullscreen mode"""
        if checked:
            self.showFullScreen()
        else:
            self.showNormal()

    def toggle_control_panel(self):
        """Toggle control panel visibility"""
        current_sizes = self.main_splitter.sizes()

        if current_sizes[1] > 0:
            # Hide control panel
            self.main_splitter.setSizes([sum(current_sizes), 0])
        else:
            # Show control panel (30% of width)
            total_width = sum(current_sizes)
            self.main_splitter.setSizes([int(total_width * 0.7), int(total_width * 0.3)])

    def toggle_grid(self, checked=None):
        """Toggle grid on stream view"""
        if checked is None:
            # If called without argument, toggle current state
            self.stream_view.toggle_grid()
        else:
            # Set to specific state
            self.stream_view.show_grid = checked
            self.stream_view.refresh()

    def toggle_info(self, checked=None):
        """Toggle info overlay on stream view"""
        if checked is None:
            # If called without argument, toggle current state
            self.stream_view.toggle_info()
        else:
            # Set to specific state
            self.stream_view.show_info = checked
            self.stream_view.refresh()

    def edit_roi(self):
        """Start ROI editing mode"""
        self.control_panel.edit_roi_clicked.emit()

    def edit_line(self):
        """Start line editing mode"""
        self.control_panel.edit_line_clicked.emit()

    def finish_editing(self):
        """Finish ROI/line editing"""
        self.control_panel.finish_editing_clicked.emit()

    def cancel_editing(self):
        """Cancel ROI/line editing"""
        self.control_panel.cancel_editing_clicked.emit()

    def export_counts(self):
        """Export counting data"""
        # TODO: Implement export functionality
        QMessageBox.information(self, "Export Counts", "Export functionality not yet implemented")

    def show_about(self):
        """Show about dialog"""
        dialog = AboutDialog(self)
        dialog.exec_()

    def start_processing(self):
        """Start video processing"""
        if getattr(self, '_in_start_processing', False):
            return
        self._in_start_processing = True

        try:
            # 1) Update UI
            self.statusBar.showMessage("Processing started")
            self.control_panel.set_processing_state(True)

            # 2) Directly implement video processing instead of checking for method
            try:
                logging.info("Starting video processing directly")

                # Import VehicleCounterGUI
                from ui.gui_app import VehicleCounterGUI

                # Create video processor if not already created
                if not hasattr(self, '_video_processor'):
                    self._video_processor = VehicleCounterGUI()
                    logging.info("VehicleCounterGUI instance created")

                # Get source configuration from control panel
                source_type = self.control_panel.source_type_combo.currentData()
                source_path = self.control_panel.source_path_edit.text()
                options = {}  # Add any option parameters from control panel if needed

                # Change source in the video processor
                self._video_processor.change_source(source_type, source_path, options)

                # Start processing
                self._video_processor.start_processing()

                # Connect signals to update UI
                if hasattr(self._video_processor, 'processing_thread'):
                    try:
                        # First disconnect any existing connections
                        self._video_processor.processing_thread.frame_processed.disconnect()
                    except Exception:
                        pass  # Ignore if no connections existed

                    # Connect to update our stream view
                    self._video_processor.processing_thread.frame_processed.connect(
                        self.on_frame_processed if hasattr(self, 'on_frame_processed') else self.stream_view.update_frame,
                        type=Qt.QueuedConnection
                    )

                logging.info("Video processing started successfully")

            except Exception as e:
                logging.error(f"Error starting video processing: {str(e)}")
                traceback.print_exc()
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.critical(self, "Processing Error", f"Failed to start video processing: {str(e)}")
        finally:
            del self._in_start_processing


    def stop_processing(self):
        """Stop video processing"""
        self.control_panel.stop_clicked.emit()
        self.statusBar.showMessage("Processing stopped")

    def pause_processing(self, paused):
        """Pause/resume video processing"""
        self.control_panel.pause_clicked.emit(paused)

        if hasattr(self, '_video_processor') and hasattr(self._video_processor, 'processing_thread'):
            try:
                if paused:
                    self._video_processor.processing_thread.pause()
                    self.statusBar.showMessage("Processing paused")
                else:
                    self._video_processor.processing_thread.resume()
                    self.statusBar.showMessage("Processing resumed")
            except Exception as e:
                logger.error(f"Error in pause_processing: {e}")
                traceback.print_exc()
        else:
            if paused:
                self.statusBar.showMessage("Processing paused")
            else:
                self.statusBar.showMessage("Processing resumed")

    def toggle_pause(self):
        """Toggle pause state"""
        # Find pause button in toolbar
        for action in self.toolbar.actions():
            if action.text() == "Pause":
                action.setChecked(not action.isChecked())
                self.pause_processing(action.isChecked())
                break

    def on_source_changed(self, source_type, source_path, options):
        """
        Handle source changed

        Args:
            source_type (str): Source type
            source_path (str): Source path
            options (dict): Source options
        """
        # Update status bar
        self.statusBar.showMessage(f"Source changed: {source_type} - {source_path}")

        # Update video processor if it exists
        if hasattr(self, '_video_processor'):
            try:
                self._video_processor.change_source(source_type, source_path, options)
                logger.info(f"Updated source in video processor: {source_type} - {source_path}")
            except Exception as e:
                logger.error(f"Error updating source in video processor: {e}")

    def on_pause_toggled(self, paused):
        """
        Handle pause toggled

        Args:
            paused (bool): Whether video is paused
        """
        # Find pause button in toolbar and update its state
        for action in self.toolbar.actions():
            if action.text() == "Pause":
                action.setChecked(paused)
                break

        # Call pause_processing to update the actual processing thread
        self.pause_processing(paused)

    def on_preset_saved(self, path):
        """
        Handle preset saved

        Args:
            path (str): Path to saved preset
        """
        self.add_to_recent_presets(path)
        self.statusBar.showMessage(f"Preset saved: {Path(path).stem}")

        # Refresh preset manager if visible
        if self.preset_dock.isVisible():
            self.preset_manager_widget.refresh()

    def on_preset_loaded(self, path):
        """
        Handle preset loaded

        Args:
            path (str): Path to loaded preset
        """
        self.add_to_recent_presets(path)

        # Update status
        self.statusBar.showMessage(f"Preset loaded: {Path(path).stem}")

    def on_preset_selected(self, preset_id):
        """
        Handle preset selected in preset manager

        Args:
            preset_id (str): Selected preset ID
        """
        # Update status
        preset_info = self.preset_manager.presets.get(preset_id, {})
        if preset_info:
            self.statusBar.showMessage(f"Preset selected: {preset_info.get('name', 'Unnamed')}")

    def closeEvent(self, event):
        """Handle window close event"""
        # Save window state
        self.save_window_state()

        # Stop processing and clean up
        if hasattr(self, '_video_processor'):
            # Stop processing
            if hasattr(self._video_processor, 'processing_thread') and self._video_processor.processing_thread:
                try:
                    self._video_processor.stop_processing()
                    logger.info("Processing stopped during window close")
                except Exception as e:
                    logger.error(f"Error stopping processing during close: {e}")

        # Ask for confirmation if processing is active
        if hasattr(self.control_panel, 'processing_active') and self.control_panel.processing_active:
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "Processing is active. Are you sure you want to quit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.No:
                event.ignore()
                return

        # Accept the event and close
        event.accept()


# ui/gui_app.py
# -*- coding: utf-8 -*-

"""
GUI application for Vehicle Counter
"""

import numpy as np
import time
from pathlib import Path
from PyQt5.QtWidgets import (QMainWindow, QWidget, QHBoxLayout,
    QFileDialog, QMessageBox, QDockWidget,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot, QThread, pyqtSignal, QMutex, QMutexLocker

# Import core components
from core.detector import VehicleDetector
from core.tracker import VehicleTracker
from core.counter import VehicleCounter
from core.roi_manager import ROIManager
from utils.video_sources import create_video_source
from config.settings import (
    MODELS_DIR, DEFAULT_MODEL, DEFAULT_CONF_THRESHOLD, DEFAULT_NMS_THRESHOLD,
    VEHICLE_CLASSES, COLORS
)

# Import UI components
from ui.components.stream_view import VideoStreamView
from ui.components.control_panel import ControlPanel

class ProcessingThread(QThread):
    """Thread for processing video frames"""
    frame_processed = pyqtSignal(np.ndarray, dict)
    processing_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, source, detector, tracker, counter):
        """Initialize processing thread"""
        super().__init__()
        self.source = source
        self.detector = detector
        self.tracker = tracker
        self.counter = counter
        self.running = False
        self.paused = False

        # Add mutex for thread safety
        self._mutex = QMutex()

    def run(self):
        """Main processing loop"""
        self.running = True

        # Basic validation to prevent errors
        if not self.source or not self.detector or not self.tracker or not self.counter:
            self.error_occurred.emit("One or more processing components are missing")
            return

        try:
            # Start async inference for first frame
            if not hasattr(self.source, 'read'):
                self.error_occurred.emit("Video source is invalid")
                return

            ret, first_frame = self.source.read()
            if not ret or first_frame is None:
                self.error_occurred.emit("Failed to read first frame from source")
                return

            # Start async inference with proper error handling
            if hasattr(self.detector, 'is_async') and self.detector.is_async:
                try:
                    self.detector.detect(first_frame)
                except Exception as detect_error:
                    self.error_occurred.emit(f"Error during initial detection: {str(detect_error)}")
                    return

            # Main processing loop with better error checking
            frame_count = 0
            while self.running:
                # Use mutex to check if paused
                with QMutexLocker(self._mutex):
                    paused = self.paused

                if paused:
                    # Do not consume CPU when paused
                    time.sleep(0.1)
                    continue

                # Read frame with timeout
                ret, frame = self.source.read()
                if not ret:
                    # End of stream or error
                    break

                # Stop if frame is None
                if frame is None:
                    self.error_occurred.emit("Received empty frame from source")
                    break

                # Make a deep copy for drawing to avoid reference issues
                vis_frame = frame.copy()

                # Process frame with proper error handling
                try:
                    # Run detection based on mode
                    if hasattr(self.detector, 'is_async') and self.detector.is_async:
                        # For async mode, pass current frame and get results from previous frame
                        detections, infer_time = self.detector.detect(frame)
                        # Skip first frame in async mode as it won't have results
                        if detections is None:
                            continue
                    else:
                        # Sync mode
                        detections, infer_time = self.detector.detect(frame)

                    # Process detections and update tracking
                    processed_frame, detection_results = self.detector.postprocess(vis_frame, detections)

                    # Update tracker with proper error checking
                    if not detection_results or "boxes" not in detection_results:
                        # Skip frame if detection failed
                        continue

                    tracking_results = self.tracker.update(
                        detection_results["boxes"],
                        detection_results["classes"],
                        detection_results["class_names"]
                    )

                    # Update counter
                    counting_results = self.counter.update(tracking_results)

                    # Drawing operations - wrap in try/except to prevent crashes
                    try:
                        # Draw tracking
                        processed_frame = self.tracker.draw_tracking(processed_frame)
                        # Draw counting
                        processed_frame = self.counter.draw_counting_info(processed_frame)
                        # Draw performance stats
                        processed_frame = self.detector.draw_stats(processed_frame)
                    except Exception as draw_error:
                        # Continue even if drawing fails
                        print(f"Warning: Drawing error: {str(draw_error)}")

                    # Combine all results
                    results = {
                        "detection": detection_results,
                        "tracking": tracking_results,
                        "counting": counting_results,
                        "performance": self.detector.get_performance_stats()
                    }

                    # Make a deep copy to ensure thread safety before emitting
                    safe_frame = processed_frame.copy()

                    # Emit processed frame - this is where Qt signal emission happens
                    self.frame_processed.emit(safe_frame, results)
                    frame_count += 1

                except Exception as process_error:
                    import traceback
                    traceback.print_exc()
                    self.error_occurred.emit(f"Frame processing error: {str(process_error)}")
                    # Continue processing next frame instead of breaking
                    continue

            # Signal that processing has finished normally
            self.processing_finished.emit()

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(f"Processing error: {str(e)}")

    def stop(self):
        """Stop processing thread safely"""
        self.running = False
        # Don't wait here - calling thread will wait if needed

    def pause(self):
        """Pause processing"""
        with QMutexLocker(self._mutex):
            self.paused = True

    def resume(self):
        """Resume processing"""
        with QMutexLocker(self._mutex):
            self.paused = False


class VehicleCounterGUI(QMainWindow):
    """Main GUI window for Vehicle Counter application"""

    def __init__(self, preset_path=None):
        """Initialize GUI application"""
        super().__init__()

        self.preset_path = preset_path
        self.video_source = None
        self.processing_thread = None

        # Core components
        self.detector = None
        self.tracker = None
        self.counter = None
        self.roi_manager = None

        # Initialize UI
        self.init_ui()

        # Initialize components
        self.init_components()

        # Load preset if provided
        if preset_path:
            self.load_preset(preset_path)

    def init_ui(self):
        """Initialize user interface"""
        self.setWindowTitle("Vehicle Counter")
        self.setGeometry(100, 100, 1280, 800)

        # Main widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)

        # Video stream view
        self.stream_view = VideoStreamView()
        self.main_layout.addWidget(self.stream_view)

        # Control panel dock widget
        self.control_panel = ControlPanel()
        self.control_dock = QDockWidget("Control Panel", self)
        self.control_dock.setWidget(self.control_panel)
        self.control_dock.setFeatures(QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.RightDockWidgetArea, self.control_dock)

        # Connect control panel signals
        self.connect_signals()

        # Timer for updating UI
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(100)  # Update every 100ms

    def init_components(self):
        """Initialize core components"""
        try:
            # 1. Create the ROI manager first (no arguments to constructor)
            self.roi_manager = ROIManager()

            # 2. Create the detector
            self.detector = VehicleDetector(
                model_path=DEFAULT_MODEL,
                device="GPU",
                conf_threshold=DEFAULT_CONF_THRESHOLD,
                nms_threshold=DEFAULT_NMS_THRESHOLD,
                async_mode=True
            )

            # 3. Create the tracker
            self.tracker = VehicleTracker()

            # 4. Create the counter, passing in the ROI manager
            self.counter = VehicleCounter(self.roi_manager)

            # 5. Wire up the ROI manager to the video stream view
            self.stream_view.set_roi_manager(self.roi_manager)

            # 6. Give all components to the control panel
            self.control_panel.set_components(
                self.detector,
                self.tracker,
                self.counter,
                self.roi_manager
            )

        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(
                self,
                "Initialization Error",
                f"Error initializing components: {str(e)}"
            )


    def connect_signals(self):
        """Connect UI signals to slots with better error handling"""
        try:
            # Connect control panel signals using explicit connection types
            self.control_panel.source_changed.connect(self.change_source, Qt.QueuedConnection)
            self.control_panel.start_clicked.connect(self.start_processing, Qt.QueuedConnection)
            self.control_panel.stop_clicked.connect(self.stop_processing, Qt.QueuedConnection)

            # Disconnect existing signals to prevent double connections
            try:
                self.control_panel.save_preset_clicked.disconnect()
                self.control_panel.load_preset_clicked.disconnect()
            except:
                pass

            # Connect remaining signals
            self.control_panel.save_preset_clicked.connect(self.save_preset, Qt.QueuedConnection)
            self.control_panel.load_preset_clicked.connect(self.load_preset_dialog, Qt.QueuedConnection)

            # Connect ROI editing signals
            self.control_panel.edit_roi_clicked.connect(self.start_roi_editing, Qt.QueuedConnection)
            self.control_panel.edit_line_clicked.connect(self.start_line_editing, Qt.QueuedConnection)
            self.control_panel.finish_editing_clicked.connect(self.finish_editing, Qt.QueuedConnection)
            self.control_panel.cancel_editing_clicked.connect(self.cancel_editing, Qt.QueuedConnection)
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to connect signals: {str(e)}")

    def update_ui(self):
        """Update UI components"""
        # Update status if processing thread is running
        if self.processing_thread and self.processing_thread.isRunning():
            self.control_panel.update_status("Processing")
        else:
            self.control_panel.update_status("Idle")

    @pyqtSlot(str, str, dict)
    def change_source(self, source_type, source_path, options):
        """Change video source"""
        try:
            # Stop current processing
            self.stop_processing()

            # Release previous source
            if self.video_source:
                self.video_source.release()

            # Create new source
            self.video_source = create_video_source(source_type, source_path, **options)

            # Open source
            if not self.video_source.open():
                QMessageBox.warning(self, "Error", f"Failed to open {source_type} source: {source_path}")
                return

            # Update stream view with source info
            self.stream_view.set_source_info(self.video_source.get_info())

            # Enable start button
            self.control_panel.enable_start(True)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error changing source: {str(e)}")

    def start_processing(self):
        """Start video processing"""
        if not self.video_source or not self.video_source.is_opened:
            QMessageBox.warning(self, "Error", "No video source opened")
            return

        try:
            # First, ensure any existing thread is properly stopped and disconnected
            if self.processing_thread is not None:
                # Disconnect all signals safely to prevent memory leaks and recursive calls
                try:
                    self.processing_thread.frame_processed.disconnect()
                    self.processing_thread.processing_finished.disconnect()
                    self.processing_thread.error_occurred.disconnect()
                except (TypeError, RuntimeError) as e:
                    # More specific exception handling for Qt disconnection errors
                    print(f"Signal disconnect warning (non-critical): {str(e)}")

                # Stop the thread and wait for it to finish
                self.processing_thread.stop()
                if self.processing_thread.isRunning():
                    if not self.processing_thread.wait(3000):  # Wait up to 3 seconds
                        print("Warning: Processing thread did not terminate in time")
                        # In a production app, you might want to handle this differently

                # Delete the thread to ensure clean up
                self.processing_thread.deleteLater()
                self.processing_thread = None

            # Reset components to clean state
            if self.tracker:
                self.tracker.reset()
            if self.counter:
                self.counter.reset()

            # Create new processing thread with proper error handling
            self.processing_thread = ProcessingThread(
                self.video_source, self.detector, self.tracker, self.counter
            )

            # Connect thread signals - use QueuedConnection for thread safety
            self.processing_thread.frame_processed.connect(
                self.on_frame_processed,
                type=Qt.QueuedConnection  # Use QueuedConnection for UI updates from other threads
            )
            self.processing_thread.processing_finished.connect(
                self.on_processing_finished,
                type=Qt.QueuedConnection
            )
            self.processing_thread.error_occurred.connect(
                self.on_processing_error,
                type=Qt.QueuedConnection
            )

            # Start processing in a try/except block
            try:
                self.processing_thread.start(QThread.HighPriority)  # Set higher priority
                # Update UI only after thread has successfully started
                self.control_panel.set_processing_state(True)
            except Exception as e:
                QMessageBox.critical(self, "Thread Error", f"Failed to start processing: {str(e)}")
                self.processing_thread = None

        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Error preparing processing: {str(e)}")

    @pyqtSlot(np.ndarray, dict)
    def on_frame_processed(self, frame, results):
        """Handle processed frame"""
        try:
            # Make a copy of the frame to ensure thread safety
            frame_copy = frame.copy()

            # Update stream view
            self.stream_view.update_frame(frame_copy)

            # Update statistics
            self.control_panel.update_statistics(results)
        except Exception as e:
            print(f"Error processing frame: {str(e)}")
            # Don't show message box here as it would flood the UI

    @pyqtSlot()
    def stop_processing(self):
        """Stop video processing"""
        if self.processing_thread and self.processing_thread.isRunning():
            self.processing_thread.stop()
            self.control_panel.set_processing_state(False)

    @pyqtSlot(np.ndarray, dict)
    def on_frame_processed(self, frame, results):
        """Handle processed frame"""
        # Update stream view
        self.stream_view.update_frame(frame)

        # Update statistics
        self.control_panel.update_statistics(results)

    @pyqtSlot()
    def on_processing_finished(self):
        """Handle processing finished event"""
        self.control_panel.set_processing_state(False)

    @pyqtSlot(str)
    def on_processing_error(self, error_msg):
        """Handle processing error"""
        QMessageBox.critical(self, "Processing Error", error_msg)
        self.control_panel.set_processing_state(False)

    def save_preset(self, file_path=None):
        """Save current configuration to preset file"""
        if not file_path:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save Preset", str(Path.home()), "JSON Files (*.json)"
            )

            if not file_path:
                return

        try:
            # Get current configuration
            config = {
                "detector": {
                    "model": str(self.detector.model_path),
                    "device": self.detector.device,
                    "conf_threshold": self.detector.conf_threshold,
                    "nms_threshold": self.detector.nms_threshold,
                    "async_mode": self.detector.is_async
                },
                "tracker": {
                    "max_disappeared": self.tracker.max_disappeared,
                    "min_iou_threshold": self.tracker.min_iou_threshold,
                    "max_distance": self.tracker.max_distance
                },
                "source": {
                    "type": self.video_source.source_type.value if self.video_source else None,
                    "path": self.video_source.source_path if self.video_source else None
                }
            }

            # Add ROIs and counting lines
            self.roi_manager.save_to_file(file_path)

            QMessageBox.information(self, "Success", "Preset saved successfully")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error saving preset: {str(e)}")

    def load_preset_dialog(self):
        """Open file dialog to load preset"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Preset", str(Path.home()), "JSON Files (*.json)"
        )

        if file_path:
            self.load_preset(file_path)

    def load_preset(self, file_path):
        """Load configuration from preset file"""
        try:
            # Load ROIs and counting lines
            if not self.roi_manager.load_from_file(file_path):
                QMessageBox.warning(self, "Warning", "Failed to load ROIs and counting lines")

            # Update stream view
            self.stream_view.refresh()

            QMessageBox.information(self, "Success", "Preset loaded successfully")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error loading preset: {str(e)}")

    @pyqtSlot()
    def start_roi_editing(self):
        """Start ROI editing mode"""
        self.stop_processing()
        self.stream_view.enable_editing(True, "roi")
        self.roi_manager.start_roi_editing()

    @pyqtSlot()
    def start_line_editing(self):
        """Start counting line editing mode"""
        self.stop_processing()
        self.stream_view.enable_editing(True, "line")
        self.roi_manager.start_line_editing()

    @pyqtSlot()
    def finish_editing(self):
        """Finish ROI or line editing"""
        self.stream_view.enable_editing(False)
        self.roi_manager.finish_editing()

    @pyqtSlot()
    def cancel_editing(self):
        """Cancel ROI or line editing"""
        self.stream_view.enable_editing(False)
        self.roi_manager.cancel_editing()

    def run(self):
        """Show the window and start the application"""
        self.show()

    def closeEvent(self, event):
        """Handle window close event"""
        # Stop processing thread
        self.stop_processing()

        # Release video source
        if self.video_source:
            self.video_source.release()

        event.accept()
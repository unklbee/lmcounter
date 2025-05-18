# ui/gui_app.py
# -*- coding: utf-8 -*-

"""
GUI application for Vehicle Counter
"""

import numpy as np
import time
import logging
import traceback
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union

from PyQt5.QtWidgets import (QMainWindow, QWidget, QHBoxLayout,
                             QFileDialog, QMessageBox, QDockWidget, QApplication
                             )
from PyQt5.QtCore import Qt, QTimer, pyqtSlot, QThread, pyqtSignal, QMutex, QMutexLocker

# Import core components
from core.detector import VehicleDetector
from core.tracker import VehicleTracker
from core.counter import VehicleCounter
from core.roi_manager import ROIManager
from utils.video_sources import create_video_source, VideoSource
from config.settings import (
    MODELS_DIR, DEFAULT_MODEL, DEFAULT_CONF_THRESHOLD, DEFAULT_NMS_THRESHOLD,
    VEHICLE_CLASSES, COLORS
)

# Import UI components
from ui.components.stream_view import VideoStreamView
from ui.components.control_panel import ControlPanel

# Setup logger
logger = logging.getLogger(__name__)

class ProcessingThread(QThread):
    """Thread for processing video frames"""
    frame_processed = pyqtSignal(np.ndarray, dict)
    processing_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, source: VideoSource, detector: VehicleDetector,
                 tracker: VehicleTracker, counter: VehicleCounter):
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

        # Validate components
        if not self._validate_components():
            return

        try:
            # Get first frame
            ret, first_frame = self._get_first_frame()
            if not ret:
                return

            # Start async inference for first frame if needed
            self._start_initial_detection(first_frame)

            # Main processing loop
            self._process_frames()

            # Signal that processing has finished normally
            self.processing_finished.emit()

        except Exception as e:
            self._handle_processing_error(e)

    def _validate_components(self) -> bool:
        """Validate that all required components are available"""
        if not self.source or not self.detector or not self.tracker or not self.counter:
            self.error_occurred.emit("One or more processing components are missing")
            return False

        # Basic validation to prevent errors
        if not hasattr(self.source, 'read'):
            self.error_occurred.emit("Video source is invalid")
            return False

        return True

    def _get_first_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Get the first frame from source"""
        ret, first_frame = self.source.read()
        if not ret or first_frame is None:
            self.error_occurred.emit("Failed to read first frame from source")
            return False, None
        return True, first_frame

    def _start_initial_detection(self, frame: np.ndarray):
        """Start initial detection if using async mode"""
        if hasattr(self.detector, 'is_async') and self.detector.is_async:
            try:
                self.detector.detect(frame)
            except Exception as detect_error:
                self.error_occurred.emit(f"Error during initial detection: {str(detect_error)}")
                raise

    def _process_frames(self):
        """Process video frames"""
        frame_count = 0
        logger.info("Starting frame processing loop")

        while self.running:
            # Check if paused
            if self._check_if_paused():
                continue

            # Read frame with timeout
            ret, frame = self.source.read()
            if not ret:
                logger.warning("Failed to read frame or end of video")
                # End of stream or error
                break

            if frame is None:
                logger.error("Received empty frame from source")
                self.error_occurred.emit("Received empty frame from source")
                break

            # Log setiap 30 frame untuk mengurangi spam log
            if frame_count % 30 == 0:
                logger.debug(f"Processing frame #{frame_count}")

            # Process current frame
            try:
                self._process_single_frame(frame, frame_count)
                frame_count += 1
            except Exception as e:
                logger.error(f"Error processing frame {frame_count}: {str(e)}")
                logger.debug(traceback.format_exc())
                # Continue processing next frame instead of breaking
                continue

        logger.info(f"Frame processing loop ended after {frame_count} frames")
        self.processing_finished.emit()


    def _check_if_paused(self) -> bool:
        """Check if processing is paused"""
        with QMutexLocker(self._mutex):
            paused = self.paused

        if paused:
            # Do not consume CPU when paused
            time.sleep(0.1)
            return True
        return False

    def _process_single_frame(self, frame: np.ndarray, frame_count: int):
        """Process a single video frame"""
        # Make a deep copy for drawing to avoid reference issues
        vis_frame = frame.copy()

        # Run detection
        results = self._run_detection(frame)
        if results is None:
            logger.warning(f"Detection returned None for frame {frame_count}")
            return

        detections, infer_time = results

        # Skip if no detections available yet (first frame in async mode)
        if detections is None:
            logger.debug(f"Skipping frame {frame_count} - no detections available yet")
            return

        # Process detections and update tracking
        processed_frame, detection_results = self.detector.postprocess(vis_frame, detections)

        # Update tracker
        if not detection_results or "boxes" not in detection_results:
            logger.warning(f"No valid detection results for frame {frame_count}")
            # Skip frame if detection failed
            return

        tracking_results = self.tracker.update(
            detection_results["boxes"],
            detection_results["classes"],
            detection_results["class_names"]
        )

        # Update counter
        counting_results = self.counter.update(tracking_results)

        # Draw visualizations
        processed_frame = self._draw_visualization(processed_frame)

        # Combine all results
        results = {
            "detection": detection_results,
            "tracking": tracking_results,
            "counting": counting_results,
            "performance": self.detector.get_performance_stats()
        }

        # Log untuk debugging
        if frame_count % 30 == 0:
            logger.debug(f"Emitting processed frame #{frame_count}, shape: {processed_frame.shape}")

        # Emit processed frame - this is where Qt signal emission happens
        try:
            frame_copy = processed_frame.copy()
            self.frame_processed.emit(frame_copy, results)
        except Exception as e:
            logger.error(f"Error emitting processed frame: {str(e)}")
            logger.debug(traceback.format_exc())

    def _run_detection(self, frame: np.ndarray) -> Optional[Tuple[np.ndarray, float]]:
        """Run detection on frame and handle different return formats"""
        try:
            result = self.detector.detect(frame)

            # Handle different possible return formats
            if isinstance(result, tuple):
                if len(result) == 2:
                    # Most likely case: (detections, infer_time)
                    return result
                elif len(result) == 3:
                    # In case detector returns (processed_frame, detections, infer_time)
                    return result[1], result[2]
                else:
                    # Unexpected number of return values but still a tuple
                    logger.warning(f"Detector returned tuple with unexpected length: {len(result)}")
                    return result[0], 0.0
            else:
                # Not a tuple at all
                logger.error(f"Detector returned unexpected type: {type(result)}")
                return None

        except Exception as e:
            logger.error(f"Detection error: {str(e)}")
            return None

    def _draw_visualization(self, frame: np.ndarray) -> np.ndarray:
        """Draw visualizations on the frame"""
        try:
            # Draw tracking
            frame = self.tracker.draw_tracking(frame)

            # Draw counting
            frame = self.counter.draw_counting_info(frame)

            # Draw performance stats
            frame = self.detector.draw_stats(frame)

            return frame
        except Exception as e:
            logger.warning(f"Drawing error: {str(e)}")
            return frame

    def _handle_processing_error(self, error: Exception):
        """Handle processing error"""
        error_msg = f"Processing error: {str(error)}"
        logger.error(error_msg)
        logger.debug(traceback.format_exc())
        self.error_occurred.emit(error_msg)

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

        # Initialize state
        self.preset_path = preset_path
        self.video_source = None
        self.processing_thread = None
        self.processing_active = False

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
            self._handle_component_init_error(e)

    def _handle_component_init_error(self, error: Exception):
        """Handle component initialization error"""
        logger.error(f"Error initializing components: {str(error)}")
        logger.debug(traceback.format_exc())
        QMessageBox.critical(
            self,
            "Initialization Error",
            f"Error initializing components: {str(error)}"
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
            logger.error(f"Failed to connect signals: {str(e)}")
            logger.debug(traceback.format_exc())
            QMessageBox.critical(self, "Error", f"Failed to connect signals: {str(e)}")

    def update_ui(self):
        """Update UI components"""
        # Update status if processing thread is running
        if self.processing_thread and self.processing_thread.isRunning():
            self.control_panel.update_status("Processing")
            self.processing_active = True
        else:
            self.control_panel.update_status("Idle")
            self.processing_active = False

    @pyqtSlot(str, str, dict)
    def change_source(self, source_type: str, source_path: str, options: Dict[str, Any]):
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
            logger.error(f"Error changing source: {str(e)}")
            logger.debug(traceback.format_exc())
            QMessageBox.critical(self, "Error", f"Error changing source: {str(e)}")

    def start_processing(self):
        """Start video processing"""
        if not self.video_source or not self.video_source.is_opened:
            QMessageBox.warning(self, "Error", "No video source opened")
            return

        try:
            # Stop and cleanup any existing thread
            self.stop_and_cleanup_thread()

            # Reset core components
            self.reset_components()

            # Create new processing thread
            self.processing_thread = ProcessingThread(
                self.video_source, self.detector, self.tracker, self.counter
            )

            # Connect thread signals - use QueuedConnection for thread safety
            self.connect_thread_signals()

            # Start processing
            self.start_thread()

        except Exception as e:
            logger.error(f"Error starting processing: {str(e)}")
            logger.debug(traceback.format_exc())
            QMessageBox.critical(self, "Error", f"Error starting processing: {str(e)}")

    def stop_and_cleanup_thread(self):
        """Stop and clean up existing processing thread"""
        if self.processing_thread is not None:
            # Disconnect all signals safely to prevent memory leaks and recursive calls
            try:
                self.processing_thread.frame_processed.disconnect()
                self.processing_thread.processing_finished.disconnect()
                self.processing_thread.error_occurred.disconnect()
            except (TypeError, RuntimeError) as e:
                # More specific exception handling for Qt disconnection errors
                logger.warning(f"Signal disconnect warning (non-critical): {str(e)}")

            # Stop the thread and wait for it to finish
            self.processing_thread.stop()
            if self.processing_thread.isRunning():
                if not self.processing_thread.wait(3000):  # Wait up to 3 seconds
                    logger.warning("Warning: Processing thread did not terminate in time")

            # Delete the thread to ensure clean up
            self.processing_thread.deleteLater()
            self.processing_thread = None

    def reset_components(self):
        """Reset core components to clean state"""
        if self.tracker:
            self.tracker.reset()
        if self.counter:
            self.counter.reset()

    def connect_thread_signals(self):
        """Connect processing thread signals"""
        logger.info("Connecting thread signals")

        try:
            # Connect using QueuedConnection for thread safety
            self.processing_thread.frame_processed.connect(
                self.on_frame_processed,
                type=Qt.QueuedConnection
            )
            logger.info("Connected frame_processed signal")

            self.processing_thread.processing_finished.connect(
                self.on_processing_finished,
                type=Qt.QueuedConnection
            )
            logger.info("Connected processing_finished signal")

            self.processing_thread.error_occurred.connect(
                self.on_processing_error,
                type=Qt.QueuedConnection
            )
            logger.info("Connected error_occurred signal")
        except Exception as e:
            logger.error(f"Error connecting thread signals: {str(e)}")
            logger.debug(traceback.format_exc())
            raise

    def start_thread(self):
        """Start the processing thread"""
        try:
            self.processing_thread.start(QThread.HighPriority)
            # Update UI only after thread has successfully started
            self.control_panel.set_processing_state(True)
            self.processing_active = True
        except Exception as e:
            logger.error(f"Failed to start processing thread: {str(e)}")
            logger.debug(traceback.format_exc())
            QMessageBox.critical(self, "Thread Error", f"Failed to start processing: {str(e)}")
            self.processing_thread = None
            self.processing_active = False

    @pyqtSlot(np.ndarray, dict)
    def on_frame_processed(self, frame: np.ndarray, results: Dict[str, Any]):
        """Handle processed frame"""
        try:
            logger.debug(f"Received frame, shape: {frame.shape if frame is not None else 'None'}")

            if frame is None:
                logger.error("Received None frame in on_frame_processed")
                return

            # Update stream view directly without copying again
            self.stream_view.update_frame(frame)

            # Update statistics
            self.control_panel.update_statistics(results)
        except Exception as e:
            logger.error(f"Error in on_frame_processed: {str(e)}")
            logger.debug(traceback.format_exc())

    @pyqtSlot()
    def stop_processing(self):
        """Stop video processing"""
        if self.processing_thread and self.processing_thread.isRunning():
            self.processing_thread.stop()
            self.control_panel.set_processing_state(False)
            self.processing_active = False

    @pyqtSlot()
    def on_processing_finished(self):
        """Handle processing finished event"""
        self.control_panel.set_processing_state(False)
        self.processing_active = False

    @pyqtSlot(str)
    def on_processing_error(self, error_msg: str):
        """Handle processing error"""
        logger.error(f"Processing error: {error_msg}")
        QMessageBox.critical(self, "Processing Error", error_msg)
        self.control_panel.set_processing_state(False)
        self.processing_active = False

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
            logger.error(f"Error saving preset: {str(e)}")
            logger.debug(traceback.format_exc())
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
            logger.error(f"Error loading preset: {str(e)}")
            logger.debug(traceback.format_exc())
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
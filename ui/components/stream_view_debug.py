# stream_view_debug.py
# Tempatkan di folder ui/components/ untuk mengganti stream_view.py untuk debugging

import cv2
import numpy as np
import logging
import time
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QMessageBox, QApplication
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QRect, QSize, QTimer
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont

# Setup logger
logger = logging.getLogger(__name__)

class VideoStreamView(QWidget):
    """Video stream view component"""

    # Signals
    roi_point_added = pyqtSignal(tuple)  # (x, y)

    def __init__(self, parent=None):
        """Initialize stream view"""
        super().__init__(parent)

        # Frame data
        self.frame = None
        self.scaled_frame = None
        self.frame_size = QSize(640, 480)
        self.source_frame_size = (640, 480)

        # Display options
        self.scale_factor = 1.0
        self.maintain_aspect_ratio = True

        # Editing state
        self.editing_enabled = False
        self.editing_mode = None  # 'roi' or 'line'
        self.roi_manager = None

        # Information display
        self.source_info = {}
        self.show_info = True
        self.show_grid = False

        # Debug flag and counters
        self.debug_mode = True
        self.update_count = 0
        self.last_frame_time = time.time()
        self.fps = 0

        # Frame stats
        self.frame_stats = {
            "total_frames": 0,
            "successful_displays": 0,
            "errors": 0,
            "last_error": "",
            "last_successful_shape": None
        }

        # Initialize UI
        self.init_ui()

        # Set mouse tracking for hover effects in editing mode
        self.setMouseTracking(True)

        # Refresh timer for UI
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_display)
        self.refresh_timer.start(500)  # Refresh every 500ms

        logger.info("VideoStreamView initialized with debug mode ON")

    def init_ui(self):
        """Initialize UI components"""
        # Main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # Frame for video display
        self.frame_widget = QLabel()
        self.frame_widget.setAlignment(Qt.AlignCenter)
        self.frame_widget.setMinimumSize(320, 240)
        self.frame_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.frame_widget.setStyleSheet("background-color: black;")

        # Add click handler to frame widget
        self.frame_widget.mousePressEvent = self.on_frame_click

        self.main_layout.addWidget(self.frame_widget)

        # Status bar
        self.status_bar = QFrame()
        self.status_bar.setFrameShape(QFrame.StyledPanel)
        self.status_bar.setMaximumHeight(30)

        status_layout = QHBoxLayout(self.status_bar)
        status_layout.setContentsMargins(5, 0, 5, 0)

        self.resolution_label = QLabel("No video")
        status_layout.addWidget(self.resolution_label)

        status_layout.addStretch()

        self.status_label = QLabel("Ready")
        status_layout.addWidget(self.status_label)

        self.main_layout.addWidget(self.status_bar)

        # Debug info frame
        self.debug_frame = QFrame()
        self.debug_frame.setFrameShape(QFrame.StyledPanel)
        self.debug_frame.setStyleSheet("background-color: rgba(0,0,0,0.7); color: yellow;")
        debug_layout = QVBoxLayout(self.debug_frame)

        self.debug_label = QLabel("Debug: No frames received yet")
        self.debug_label.setStyleSheet("color: yellow; font-weight: bold;")
        debug_layout.addWidget(self.debug_label)

        self.stats_label = QLabel("Stats: waiting for frames...")
        debug_layout.addWidget(self.stats_label)

        self.main_layout.addWidget(self.debug_frame)
        self.debug_frame.setVisible(self.debug_mode)

        # Force debug frame to be shown
        self.debug_frame.show()

    def update_frame(self, frame):
        """
        Update video frame

        Args:
            frame (numpy.ndarray): Video frame to display
        """
        try:
            # Update frame stats
            self.frame_stats["total_frames"] += 1

            # Check frame validity
            if frame is None:
                logger.error("Received None frame in update_frame")
                self.frame_stats["errors"] += 1
                self.frame_stats["last_error"] = "None frame"
                self.update_debug_info()
                return

            # Check frame shape and type
            if not isinstance(frame, np.ndarray):
                logger.error(f"Invalid frame type: {type(frame)}")
                self.frame_stats["errors"] += 1
                self.frame_stats["last_error"] = f"Type: {type(frame)}"
                self.update_debug_info()
                return

            if len(frame.shape) != 3:
                logger.error(f"Invalid frame shape: {frame.shape}")
                self.frame_stats["errors"] += 1
                self.frame_stats["last_error"] = f"Shape: {frame.shape}"
                self.update_debug_info()
                return

            # Calculate FPS
            now = time.time()
            dt = now - self.last_frame_time
            if dt > 0:
                self.fps = 1.0 / dt
            self.last_frame_time = now

            # Store original frame (make copy to prevent reference issues)
            self.frame = frame.copy()

            # Get frame dimensions
            h, w, c = frame.shape
            self.source_frame_size = (w, h)
            self.frame_stats["last_successful_shape"] = (w, h, c)
            self.frame_stats["successful_displays"] += 1

            # Update resolution label
            self.resolution_label.setText(f"Resolution: {w}x{h}")

            # Update debug display
            self.update_count += 1
            self.update_debug_info()

            # Convert frame to pixmap and display it
            self.convert_frame_to_pixmap()

            # Draw ROIs if editing
            if self.editing_enabled and self.roi_manager:
                self.draw_editing_overlay()

            # Successful update
            logger.debug(f"Successfully updated frame {w}x{h}")

        except Exception as e:
            import traceback
            logger.error(f"Error in update_frame: {str(e)}")
            logger.debug(traceback.format_exc())
            self.frame_stats["errors"] += 1
            self.frame_stats["last_error"] = str(e)
            self.update_debug_info()

    def convert_frame_to_pixmap(self):
        """Convert current frame to QPixmap and display"""
        try:
            if self.frame is None:
                logger.warning("No frame to convert to pixmap")
                return

            # Make a copy of the frame
            disp_frame = self.frame.copy()

            # Draw information overlay if enabled
            if self.show_info:
                self.draw_info_overlay(disp_frame)

            # Convert BGR to RGB for Qt
            rgb_frame = cv2.cvtColor(disp_frame, cv2.COLOR_BGR2RGB)

            # Get frame dimensions
            h, w, c = rgb_frame.shape
            bytes_per_line = c * w

            # Create QImage with explicit copy of data
            q_img = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()

            # Scale image to fit widget if needed
            pixmap = QPixmap.fromImage(q_img)

            # Adjust pixmap size to fit the widget while maintaining aspect ratio
            widget_size = self.frame_widget.size()
            scaled_pixmap = pixmap.scaled(
                widget_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            self.scaled_frame = scaled_pixmap

            # Display image
            self.frame_widget.setPixmap(scaled_pixmap)

            # Force immediate update
            self.frame_widget.update()

            # Ensure widget repaints immediately
            QApplication.processEvents()

        except Exception as e:
            import traceback
            logger.error(f"Error converting frame to pixmap: {str(e)}")
            logger.debug(traceback.format_exc())
            self.frame_stats["errors"] += 1
            self.frame_stats["last_error"] = f"Pixmap: {str(e)}"
            self.update_debug_info()

    def refresh_display(self):
        """Refresh debug info and display"""
        self.update_debug_info()

        # If we have a frame but it's not displayed, try again
        if self.frame is not None and not self.is_frame_displayed():
            logger.info("Forcing frame display refresh")
            try:
                self.convert_frame_to_pixmap()
            except Exception as e:
                logger.error(f"Error in refresh_display: {str(e)}")

    def is_frame_displayed(self):
        """Check if frame is being displayed"""
        # Check if pixmap is set on the label
        return self.frame_widget.pixmap() is not None

    def update_debug_info(self):
        """Update debug information display"""
        if not self.debug_mode:
            return

        # Frame info
        frame_text = "DEBUG: "
        if self.frame is None:
            frame_text += "No frame received"
        else:
            frame_text += f"Frame #{self.update_count}: {self.frame.shape}, FPS: {self.fps:.1f}"

        self.debug_label.setText(frame_text)

        # Stats info
        stats_text = (
            f"Frames: {self.frame_stats['total_frames']}, "
            f"Displayed: {self.frame_stats['successful_displays']}, "
            f"Errors: {self.frame_stats['errors']}"
        )

        if self.frame_stats["last_error"]:
            stats_text += f"\nLast error: {self.frame_stats['last_error']}"

        if self.frame_stats["last_successful_shape"]:
            w, h, c = self.frame_stats["last_successful_shape"]
            stats_text += f"\nLast good frame: {w}x{h}x{c}"

        self.stats_label.setText(stats_text)

        # Make sure debug frame is visible
        self.debug_frame.setVisible(True)

    def draw_info_overlay(self, frame):
        """
        Draw information overlay on frame

        Args:
            frame (numpy.ndarray): Frame to draw on
        """
        try:
            h, w = frame.shape[:2]

            # Draw source info
            if self.source_info:
                y_pos = 30
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.6
                color = (255, 255, 255)
                thickness = 1

                # Draw black background
                info_text = f"Source: {self.source_info.get('source_path', 'Unknown')}"
                (text_w, text_h), _ = cv2.getTextSize(info_text, font, font_scale, thickness)
                cv2.rectangle(frame, (10, y_pos - text_h - 5), (10 + text_w + 10, y_pos + 5), (0, 0, 0), -1)

                # Draw text
                cv2.putText(frame, info_text, (15, y_pos), font, font_scale, color, thickness)

            # Draw grid if enabled
            if self.show_grid:
                # Draw vertical lines
                for x in range(0, w, 100):
                    cv2.line(frame, (x, 0), (x, h), (40, 40, 40), 1)

                # Draw horizontal lines
                for y in range(0, h, 100):
                    cv2.line(frame, (0, y), (w, y), (40, 40, 40), 1)

        except Exception as e:
            logger.error(f"Error drawing info overlay: {str(e)}")

    # [Rest of the methods remain the same]

    def set_source_info(self, info):
        """
        Set source information

        Args:
            info (dict): Source information
        """
        self.source_info = info

        # Update resolution label
        w = info.get("frame_width", 0)
        h = info.get("frame_height", 0)
        self.source_frame_size = (w, h)
        self.resolution_label.setText(f"Resolution: {w}x{h}")

        # Update debug info
        if self.debug_mode:
            self.debug_label.setText(f"Source: {info.get('source_path', 'Unknown')}, {w}x{h}")

    def toggle_debug(self):
        """Toggle debug mode"""
        self.debug_mode = not self.debug_mode
        self.debug_frame.setVisible(self.debug_mode)
        if self.debug_mode:
            self.update_debug_info()

    def paintEvent(self, event):
        """Paint event handler"""
        super().paintEvent(event)

        # If no frame is displayed but debug is on, show info
        if not self.is_frame_displayed() and self.debug_mode:
            self.update_debug_info()
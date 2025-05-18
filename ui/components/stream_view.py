# ui/components/stream_view.py
# -*- coding: utf-8 -*-

"""
Video stream view component for Vehicle Counter application
Displays video stream with detections and counting visualizations
"""
import logging
import traceback

import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QRect, QSize
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont

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

        # Initialize UI
        self.init_ui()

        # Set mouse tracking for hover effects in editing mode
        self.setMouseTracking(True)

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

    def update_frame(self, frame):
        """
        Update video frame

        Args:
            frame (numpy.ndarray): Video frame to display
        """
        if frame is None:
            logger.error("Received None frame in update_frame")
            return

        try:
            # Store original frame
            self.frame = frame.copy()  # Explicit copy to avoid reference issues

            # Get frame dimensions
            if len(frame.shape) < 3:
                logger.error(f"Invalid frame shape: {frame.shape}")
                return

            h, w, c = frame.shape
            self.source_frame_size = (w, h)

            # Update resolution label
            self.resolution_label.setText(f"Resolution: {w}x{h}")

            # Create QImage from frame
            self.convert_frame_to_pixmap()

            # Draw ROIs if editing
            if self.editing_enabled and self.roi_manager:
                self.draw_editing_overlay()
        except Exception as e:
            logger.error(f"Error in update_frame: {str(e)}")
            logger.debug(traceback.format_exc())

    def convert_frame_to_pixmap(self):
        """Convert current frame to QPixmap and display"""
        if self.frame is None:
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

        # Create QImage
        q_img = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888)

        # Scale image to fit widget if needed
        scaled_pixmap = QPixmap.fromImage(q_img)
        self.scaled_frame = scaled_pixmap

        # Display image
        self.frame_widget.setPixmap(scaled_pixmap)

    def draw_info_overlay(self, frame):
        """
        Draw information overlay on frame

        Args:
            frame (numpy.ndarray): Frame to draw on
        """
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

    def draw_editing_overlay(self):
        """Draw ROI editing overlay on displayed frame"""
        if not self.scaled_frame:
            return

        # Create painter for overlay
        painter = QPainter(self.scaled_frame)

        try:
            # Draw edit mode indicator
            font = QFont()
            font.setBold(True)
            font.setPointSize(14)
            painter.setFont(font)

            if self.editing_mode == "roi":
                painter.setPen(QColor(255, 0, 0))
                painter.drawText(QRect(10, 10, 300, 30), Qt.AlignLeft, "ROI Editing Mode")
                painter.drawText(QRect(10, 40, 400, 30), Qt.AlignLeft, "Click to add points, right-click to finish")
            elif self.editing_mode == "line":
                painter.setPen(QColor(0, 0, 255))
                painter.drawText(QRect(10, 10, 300, 30), Qt.AlignLeft, "Line Editing Mode")
                painter.drawText(QRect(10, 40, 400, 30), Qt.AlignLeft, "Click to add start/end points")

            # Draw current ROI manager points if available
            if self.roi_manager and self.roi_manager.temp_points:
                # Draw points
                for point in self.roi_manager.temp_points:
                    painter.setPen(QPen(QColor(0, 0, 255), 2))
                    painter.setBrush(QColor(0, 0, 255, 128))
                    painter.drawEllipse(QPoint(point[0], point[1]), 8, 8)

                # Draw lines connecting points
                if len(self.roi_manager.temp_points) > 1:
                    painter.setPen(QPen(QColor(255, 0, 0), 2))

                    # For ROI, draw polygon
                    if self.editing_mode == "roi":
                        for i in range(1, len(self.roi_manager.temp_points)):
                            p1 = self.roi_manager.temp_points[i-1]
                            p2 = self.roi_manager.temp_points[i]
                            painter.drawLine(QPoint(p1[0], p1[1]), QPoint(p2[0], p2[1]))

                        # Close polygon if 3+ points
                        if len(self.roi_manager.temp_points) >= 3:
                            p1 = self.roi_manager.temp_points[-1]
                            p2 = self.roi_manager.temp_points[0]
                            painter.setPen(QPen(QColor(255, 0, 0, 128), 2, Qt.DashLine))
                            painter.drawLine(QPoint(p1[0], p1[1]), QPoint(p2[0], p2[1]))

                    # For line, just connect two points
                    elif self.editing_mode == "line" and len(self.roi_manager.temp_points) == 2:
                        p1 = self.roi_manager.temp_points[0]
                        p2 = self.roi_manager.temp_points[1]
                        painter.drawLine(QPoint(p1[0], p1[1]), QPoint(p2[0], p2[1]))

        finally:
            painter.end()

        # Update display
        self.frame_widget.setPixmap(self.scaled_frame)

    def on_frame_click(self, event):
        """
        Handle mouse click on frame

        Args:
            event: Mouse event
        """
        if not self.editing_enabled or not self.roi_manager:
            return

        # Get click position
        pos = (event.x(), event.y())

        # Handle right-click to finish ROI
        if event.button() == Qt.RightButton and self.editing_mode == "roi":
            if len(self.roi_manager.temp_points) >= 3:
                self.roi_manager.finish_editing()
                return

        # Add point to ROI manager
        self.roi_manager.add_point(pos)

        # Emit signal
        self.roi_point_added.emit(pos)

        # Finish line if two points are added
        if self.editing_mode == "line" and len(self.roi_manager.temp_points) == 2:
            self.roi_manager.finish_editing()

        # Redraw
        self.draw_editing_overlay()

    def set_roi_manager(self, roi_manager):
        """
        Set ROI manager reference

        Args:
            roi_manager: ROI manager instance
        """
        self.roi_manager = roi_manager

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

    def enable_editing(self, enabled, mode=None):
        """
        Enable or disable ROI editing mode

        Args:
            enabled (bool): Whether editing is enabled
            mode (str): Editing mode ('roi' or 'line')
        """
        self.editing_enabled = enabled

        if enabled:
            self.editing_mode = mode
            self.status_label.setText(f"Editing {mode.upper()}")
        else:
            self.editing_mode = None
            self.status_label.setText("Ready")

        # Redraw if we have a frame
        if self.frame is not None:
            self.convert_frame_to_pixmap()

            if enabled and self.roi_manager:
                self.draw_editing_overlay()

    def refresh(self):
        """Refresh the view"""
        if self.frame is not None:
            self.convert_frame_to_pixmap()

            if self.editing_enabled and self.roi_manager:
                self.draw_editing_overlay()

    def toggle_grid(self):
        """Toggle grid display"""
        self.show_grid = not self.show_grid
        self.refresh()

    def toggle_info(self):
        """Toggle information overlay"""
        self.show_info = not self.show_info
        self.refresh()

    def fit_to_view(self):
        """Resize image to fit view"""
        if self.frame is None:
            return

        # Reset the frame widget to fit the parent size
        self.frame_widget.setScaledContents(False)
        self.refresh()
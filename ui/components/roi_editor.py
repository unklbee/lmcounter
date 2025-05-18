# ui/components/roi_editor.py
# -*- coding: utf-8 -*-

"""
ROI Editor component for Vehicle Counter application
Handles visual editing of ROIs and counting lines on video frames
"""

import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QDialog, QFormLayout, QLineEdit, QDialogButtonBox,
    QGroupBox, QRadioButton, QFrame, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint
from PyQt5.QtGui import QColor, QPen, QPainter, QBrush, QMouseEvent, QImage


class ROIEditorDialog(QDialog):
    """Dialog for editing ROI/Line properties"""

    def __init__(self, roi_type="roi", properties=None, parent=None):
        """
        Initialize ROI properties dialog

        Args:
            roi_type (str): Type of ROI ('roi' or 'line')
            properties (dict): Current properties or None for new
            parent: Parent widget
        """
        super().__init__(parent)

        self.roi_type = roi_type
        self.properties = properties or {}

        self.init_ui()

    def init_ui(self):
        """Initialize dialog UI"""
        if self.roi_type == "roi":
            self.setWindowTitle("Region of Interest Properties")
        else:
            self.setWindowTitle("Counting Line Properties")

        self.setMinimumWidth(300)

        # Create form layout
        layout = QFormLayout(self)

        # Name field
        self.name_edit = QLineEdit(self.properties.get("name", ""))
        layout.addRow("Name:", self.name_edit)

        # Direction options
        self.direction_group = QGroupBox("Counting Direction")
        direction_layout = QVBoxLayout()

        if self.roi_type == "roi":
            # ROI directions
            self.dir_bidirectional = QRadioButton("Bidirectional")
            self.dir_in_out = QRadioButton("In/Out")

            direction_layout.addWidget(self.dir_bidirectional)
            direction_layout.addWidget(self.dir_in_out)

            # Set current direction
            if self.properties.get("direction") == "in_out":
                self.dir_in_out.setChecked(True)
            else:
                self.dir_bidirectional.setChecked(True)
        else:
            # Line directions
            self.dir_north_south = QRadioButton("North/South")
            self.dir_east_west = QRadioButton("East/West")

            direction_layout.addWidget(self.dir_north_south)
            direction_layout.addWidget(self.dir_east_west)

            # Set current direction
            if self.properties.get("direction") == "east_west":
                self.dir_east_west.setChecked(True)
            else:
                self.dir_north_south.setChecked(True)

        self.direction_group.setLayout(direction_layout)
        layout.addRow(self.direction_group)

        # Button box
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addRow(self.button_box)

    def get_properties(self):
        """
        Get properties from dialog

        Returns:
            dict: ROI/Line properties
        """
        properties = {
            "name": self.name_edit.text() or ("ROI" if self.roi_type == "roi" else "Line")
        }

        # Get direction
        if self.roi_type == "roi":
            properties["direction"] = "in_out" if self.dir_in_out.isChecked() else "bidirectional"
        else:
            properties["direction"] = "east_west" if self.dir_east_west.isChecked() else "north_south"

        return properties


class ROIEditorWidget(QWidget):
    """ROI Editor widget for editing ROIs and lines on video frames"""

    # Signals
    roi_created = pyqtSignal(str, str, list, str)  # id, name, points, direction
    roi_updated = pyqtSignal(str, str, list, str)  # id, name, points, direction
    roi_deleted = pyqtSignal(str)  # id

    line_created = pyqtSignal(str, str, tuple, tuple, str)  # id, name, start_point, end_point, direction
    line_updated = pyqtSignal(str, str, tuple, tuple, str)  # id, name, start_point, end_point, direction
    line_deleted = pyqtSignal(str)  # id

    editing_finished = pyqtSignal()
    editing_cancelled = pyqtSignal()

    def __init__(self, roi_manager, parent=None):
        """
        Initialize ROI editor

        Args:
            roi_manager: ROI manager instance
            parent: Parent widget
        """
        super().__init__(parent)

        self.roi_manager = roi_manager
        self.editing_mode = None  # 'roi', 'line', or None
        self.current_roi_id = None
        self.current_line_id = None
        self.edit_points = []
        self.dragging_point_index = -1
        self.hovering_point_index = -1
        self.frame = None
        self.display_frame = None

        # Drawing properties
        self.point_radius = 8
        self.hover_radius = 15
        self.roi_color = QColor(255, 165, 0)  # Orange
        self.line_color = QColor(0, 255, 255)  # Yellow
        self.selected_color = QColor(255, 0, 0)  # Red
        self.hover_color = QColor(0, 255, 0)  # Green
        self.point_color = QColor(0, 0, 255)  # Blue

        self.init_ui()

        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)

    def init_ui(self):
        """Initialize widget UI"""
        self.setMinimumSize(640, 480)

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar = QHBoxLayout()

        # Create ROI button
        self.create_roi_btn = QPushButton("Create ROI")
        self.create_roi_btn.clicked.connect(self.start_create_roi)
        toolbar.addWidget(self.create_roi_btn)

        # Edit ROI button
        self.edit_roi_btn = QPushButton("Edit ROI")
        self.edit_roi_btn.clicked.connect(self.start_edit_roi)
        toolbar.addWidget(self.edit_roi_btn)

        # Create Line button
        self.create_line_btn = QPushButton("Create Line")
        self.create_line_btn.clicked.connect(self.start_create_line)
        toolbar.addWidget(self.create_line_btn)

        # Edit Line button
        self.edit_line_btn = QPushButton("Edit Line")
        self.edit_line_btn.clicked.connect(self.start_edit_line)
        toolbar.addWidget(self.edit_line_btn)

        # Delete button
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self.delete_selected)
        toolbar.addWidget(self.delete_btn)

        # Finish button
        self.finish_btn = QPushButton("Finish Editing")
        self.finish_btn.clicked.connect(self.finish_editing)
        toolbar.addWidget(self.finish_btn)

        # Cancel button
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel_editing)
        toolbar.addWidget(self.cancel_btn)

        layout.addLayout(toolbar)

        # ROI selection combobox
        roi_layout = QHBoxLayout()
        roi_layout.addWidget(QLabel("Select ROI:"))
        self.roi_combo = QComboBox()
        self.roi_combo.currentIndexChanged.connect(self.on_roi_selected)
        roi_layout.addWidget(self.roi_combo)

        # Line selection combobox
        roi_layout.addWidget(QLabel("Select Line:"))
        self.line_combo = QComboBox()
        self.line_combo.currentIndexChanged.connect(self.on_line_selected)
        roi_layout.addWidget(self.line_combo)

        layout.addLayout(roi_layout)

        # Status frame
        self.status_frame = QFrame()
        self.status_frame.setFrameShape(QFrame.StyledPanel)
        self.status_frame.setMinimumHeight(30)
        self.status_layout = QHBoxLayout(self.status_frame)
        self.status_label = QLabel("Ready")
        self.status_layout.addWidget(self.status_label)

        layout.addWidget(self.status_frame)

        # Initialize button states
        self.update_button_states()

        # Populate comboboxes
        self.update_roi_combo()
        self.update_line_combo()

    def set_frame(self, frame):
        """
        Set current frame for editing

        Args:
            frame (numpy.ndarray): Video frame
        """
        self.frame = frame
        self.update_display_frame()

    def update_display_frame(self):
        """Update display frame with ROIs and editing overlays"""
        if self.frame is None:
            return

        # Make a copy for drawing
        self.display_frame = self.frame.copy()

        # Draw all ROIs
        for roi_id, roi in self.roi_manager.rois.items():
            points = roi["points"]
            if len(points) >= 3:
                color = (0, 0, 255) if roi_id == self.current_roi_id else (255, 165, 0)
                cv2.polylines(
                    self.display_frame,
                    [np.array(points, np.int32)],
                    True,
                    color,
                    2
                )

                # Draw ROI name
                if len(points) > 0:
                    centroid = np.mean(points, axis=0).astype(int)
                    cv2.putText(
                        self.display_frame,
                        roi["name"],
                        (centroid[0], centroid[1]),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        color,
                        2
                    )

        # Draw all counting lines
        for line_id, line in self.roi_manager.counting_lines.items():
            points = line["points"]
            if len(points) == 2:
                color = (0, 0, 255) if line_id == self.current_line_id else (0, 255, 255)
                cv2.line(
                    self.display_frame,
                    points[0],
                    points[1],
                    color,
                    2
                )

                # Draw line name
                mid_x = (points[0][0] + points[1][0]) // 2
                mid_y = (points[0][1] + points[1][1]) // 2
                cv2.putText(
                    self.display_frame,
                    line["name"],
                    (mid_x, mid_y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    color,
                    2
                )

        # Draw editing points
        if self.editing_mode and self.edit_points:
            # Draw lines between points
            if self.editing_mode == "roi" and len(self.edit_points) > 1:
                # For ROI, connect all points and close if needed
                cv2.polylines(
                    self.display_frame,
                    [np.array(self.edit_points, np.int32)],
                    len(self.edit_points) >= 3,  # Close if 3+ points
                    (0, 0, 255),
                    2
                )
            elif self.editing_mode == "line" and len(self.edit_points) == 2:
                # For line, just connect the two points
                cv2.line(
                    self.display_frame,
                    self.edit_points[0],
                    self.edit_points[1],
                    (0, 0, 255),
                    2
                )

            # Draw points
            for i, point in enumerate(self.edit_points):
                color = (0, 255, 0) if i == self.hovering_point_index else (0, 0, 255)
                cv2.circle(
                    self.display_frame,
                    point,
                    self.point_radius,
                    color,
                    -1
                )

        # Request repaint
        self.update()

    def paintEvent(self, event):
        """Paint widget with current frame"""
        if self.display_frame is not None:
            painter = QPainter(self)

            # Convert frame to Qt format and draw
            h, w, c = self.display_frame.shape
            bytes_per_line = 3 * w

            # Convert BGR to RGB
            rgb_image = cv2.cvtColor(self.display_frame, cv2.COLOR_BGR2RGB)

            # Create QImage and draw
            q_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
            painter.drawImage(self.rect(), q_img)

    def mousePressEvent(self, event):
        """Handle mouse press events"""
        if not self.editing_mode or self.frame is None:
            return

        # Get mouse position
        pos = (event.x(), event.y())

        # Check if clicking on an existing point
        for i, point in enumerate(self.edit_points):
            # Calculate distance
            dist = np.sqrt((pos[0] - point[0])**2 + (pos[1] - point[1])**2)

            # If clicking on a point, start dragging
            if dist <= self.hover_radius:
                self.dragging_point_index = i
                return

        # If not clicking on a point, add a new one
        if self.editing_mode == "roi":
            # For ROI, always add point
            self.edit_points.append(pos)
            self.update_display_frame()
        elif self.editing_mode == "line" and len(self.edit_points) < 2:
            # For line, add up to 2 points
            self.edit_points.append(pos)
            self.update_display_frame()

    def mouseMoveEvent(self, event):
        """Handle mouse move events"""
        if not self.editing_mode or self.frame is None:
            return

        # Get mouse position
        pos = (event.x(), event.y())

        # If dragging a point, update its position
        if self.dragging_point_index >= 0:
            self.edit_points[self.dragging_point_index] = pos
            self.update_display_frame()
            return

        # Check if hovering over an existing point
        prev_hover_index = self.hovering_point_index
        self.hovering_point_index = -1

        for i, point in enumerate(self.edit_points):
            # Calculate distance
            dist = np.sqrt((pos[0] - point[0])**2 + (pos[1] - point[1])**2)

            # If hovering over a point
            if dist <= self.hover_radius:
                self.hovering_point_index = i
                break

        # Update display if hover state changed
        if prev_hover_index != self.hovering_point_index:
            self.update_display_frame()

    def mouseReleaseEvent(self, event):
        """Handle mouse release events"""
        # End point dragging
        self.dragging_point_index = -1

    def mouseDoubleClickEvent(self, event):
        """Handle mouse double-click events"""
        if not self.editing_mode or self.frame is None:
            return

        # For ROI, finish polygon on double-click
        if self.editing_mode == "roi" and len(self.edit_points) >= 3:
            self.finish_roi_editing()

    def start_create_roi(self):
        """Start creating a new ROI"""
        self.editing_mode = "roi"
        self.current_roi_id = None
        self.edit_points = []
        self.update_button_states()
        self.update_status("Click to add points, double-click to finish")

    def start_edit_roi(self):
        """Start editing an existing ROI"""
        if not self.roi_manager.rois:
            QMessageBox.warning(self, "Warning", "No ROIs to edit")
            return

        # Get ROI from combobox
        roi_id = self.roi_combo.currentData()
        if not roi_id or roi_id not in self.roi_manager.rois:
            return

        self.editing_mode = "roi"
        self.current_roi_id = roi_id
        self.edit_points = self.roi_manager.rois[roi_id]["points"].copy()

        self.update_button_states()
        self.update_status("Edit ROI points, double-click to finish")
        self.update_display_frame()

    def start_create_line(self):
        """Start creating a new counting line"""
        self.editing_mode = "line"
        self.current_line_id = None
        self.edit_points = []
        self.update_button_states()
        self.update_status("Click to add start point, then end point")

    def start_edit_line(self):
        """Start editing an existing counting line"""
        if not self.roi_manager.counting_lines:
            QMessageBox.warning(self, "Warning", "No counting lines to edit")
            return

        # Get line from combobox
        line_id = self.line_combo.currentData()
        if not line_id or line_id not in self.roi_manager.counting_lines:
            return

        self.editing_mode = "line"
        self.current_line_id = line_id
        self.edit_points = self.roi_manager.counting_lines[line_id]["points"].copy()

        self.update_button_states()
        self.update_status("Edit line points")
        self.update_display_frame()

    def delete_selected(self):
        """Delete selected ROI or line"""
        # Check if ROI is selected
        roi_id = self.roi_combo.currentData()
        if roi_id and roi_id in self.roi_manager.rois:
            # Confirm deletion
            reply = QMessageBox.question(self, "Confirm Deletion",
                                         f"Delete ROI '{self.roi_manager.rois[roi_id]['name']}'?",
                                         QMessageBox.Yes | QMessageBox.No)

            if reply == QMessageBox.Yes:
                self.roi_manager.delete_roi(roi_id)
                self.roi_deleted.emit(roi_id)
                self.update_roi_combo()
                self.update_display_frame()
                return

        # Check if line is selected
        line_id = self.line_combo.currentData()
        if line_id and line_id in self.roi_manager.counting_lines:
            # Confirm deletion
            reply = QMessageBox.question(self, "Confirm Deletion",
                                         f"Delete line '{self.roi_manager.counting_lines[line_id]['name']}'?",
                                         QMessageBox.Yes | QMessageBox.No)

            if reply == QMessageBox.Yes:
                self.roi_manager.delete_counting_line(line_id)
                self.line_deleted.emit(line_id)
                self.update_line_combo()
                self.update_display_frame()

    def finish_roi_editing(self):
        """Finish ROI editing"""
        if self.editing_mode != "roi" or len(self.edit_points) < 3:
            return

        # Show properties dialog
        properties = {}
        if self.current_roi_id:
            properties = self.roi_manager.rois[self.current_roi_id].copy()

        dialog = ROIEditorDialog("roi", properties, self)
        if dialog.exec_() != QDialog.Accepted:
            return

        # Get properties
        props = dialog.get_properties()

        # Create or update ROI
        if self.current_roi_id:
            # Update existing ROI
            roi_id = self.current_roi_id
            self.roi_manager.rois[roi_id]["name"] = props["name"]
            self.roi_manager.rois[roi_id]["direction"] = props["direction"]
            self.roi_manager.rois[roi_id]["points"] = self.edit_points

            # Update counter
            if self.roi_manager.counter:
                self.roi_manager.counter.remove_roi(roi_id)
                self.roi_manager.counter.add_roi(
                    roi_id,
                    props["name"],
                    self.edit_points,
                    props["direction"]
                )

            self.roi_updated.emit(roi_id, props["name"], self.edit_points, props["direction"])
        else:
            # Create new ROI
            roi_id = self.roi_manager.create_roi(
                props["name"],
                self.edit_points,
                props["direction"]
            )
            self.roi_created.emit(roi_id, props["name"], self.edit_points, props["direction"])

        # Exit editing mode
        self.editing_mode = None
        self.current_roi_id = None
        self.edit_points = []

        # Update UI
        self.update_roi_combo()
        self.update_button_states()
        self.update_status("ROI saved")
        self.update_display_frame()

    def finish_line_editing(self):
        """Finish line editing"""
        if self.editing_mode != "line" or len(self.edit_points) != 2:
            return

        # Show properties dialog
        properties = {}
        if self.current_line_id:
            properties = self.roi_manager.counting_lines[self.current_line_id].copy()

        dialog = ROIEditorDialog("line", properties, self)
        if dialog.exec_() != QDialog.Accepted:
            return

        # Get properties
        props = dialog.get_properties()

        # Create or update line
        if self.current_line_id:
            # Update existing line
            line_id = self.current_line_id
            self.roi_manager.counting_lines[line_id]["name"] = props["name"]
            self.roi_manager.counting_lines[line_id]["direction"] = props["direction"]
            self.roi_manager.counting_lines[line_id]["points"] = self.edit_points

            # Update counter
            if self.roi_manager.counter:
                self.roi_manager.counter.remove_counting_line(line_id)
                self.roi_manager.counter.add_counting_line(
                    line_id,
                    props["name"],
                    self.edit_points[0],
                    self.edit_points[1],
                    props["direction"]
                )

            self.line_updated.emit(
                line_id,
                props["name"],
                self.edit_points[0],
                self.edit_points[1],
                props["direction"]
            )
        else:
            # Create new line
            line_id = self.roi_manager.create_counting_line(
                props["name"],
                self.edit_points[0],
                self.edit_points[1],
                props["direction"]
            )

            self.line_created.emit(
                line_id,
                props["name"],
                self.edit_points[0],
                self.edit_points[1],
                props["direction"]
            )

        # Exit editing mode
        self.editing_mode = None
        self.current_line_id = None
        self.edit_points = []

        # Update UI
        self.update_line_combo()
        self.update_button_states()
        self.update_status("Counting line saved")
        self.update_display_frame()

    def finish_editing(self):
        """Finish current editing operation"""
        if not self.editing_mode:
            return

        if self.editing_mode == "roi" and len(self.edit_points) >= 3:
            self.finish_roi_editing()
        elif self.editing_mode == "line" and len(self.edit_points) == 2:
            self.finish_line_editing()
        else:
            # Not enough points
            if self.editing_mode == "roi":
                QMessageBox.warning(self, "Warning", "ROI needs at least 3 points")
            else:
                QMessageBox.warning(self, "Warning", "Line needs exactly 2 points")
            return

        # Signal that editing is done
        self.editing_finished.emit()

    def cancel_editing(self):
        """Cancel current editing operation"""
        self.editing_mode = None
        self.current_roi_id = None
        self.current_line_id = None
        self.edit_points = []

        self.update_button_states()
        self.update_status("Editing cancelled")
        self.update_display_frame()

        # Signal that editing is cancelled
        self.editing_cancelled.emit()

    def update_button_states(self):
        """Update button enabled states"""
        editing = self.editing_mode is not None

        self.create_roi_btn.setEnabled(not editing)
        self.create_line_btn.setEnabled(not editing)
        self.edit_roi_btn.setEnabled(not editing and len(self.roi_manager.rois) > 0)
        self.edit_line_btn.setEnabled(not editing and len(self.roi_manager.counting_lines) > 0)
        self.delete_btn.setEnabled(not editing)

        self.finish_btn.setEnabled(editing)
        self.cancel_btn.setEnabled(editing)

        self.roi_combo.setEnabled(not editing)
        self.line_combo.setEnabled(not editing)

    def update_roi_combo(self):
        """Update ROI selection combobox"""
        self.roi_combo.clear()

        for roi_id, roi in self.roi_manager.rois.items():
            self.roi_combo.addItem(roi["name"], roi_id)

        self.edit_roi_btn.setEnabled(self.roi_combo.count() > 0)

    def update_line_combo(self):
        """Update line selection combobox"""
        self.line_combo.clear()

        for line_id, line in self.roi_manager.counting_lines.items():
            self.line_combo.addItem(line["name"], line_id)

        self.edit_line_btn.setEnabled(self.line_combo.count() > 0)

    def on_roi_selected(self, index):
        """Handle ROI selection change"""
        roi_id = self.roi_combo.itemData(index)
        self.current_roi_id = roi_id
        self.current_line_id = None
        self.update_display_frame()

    def on_line_selected(self, index):
        """Handle line selection change"""
        line_id = self.line_combo.itemData(index)
        self.current_line_id = line_id
        self.current_roi_id = None
        self.update_display_frame()

    def update_status(self, message):
        """Update status message"""
        self.status_label.setText(message)
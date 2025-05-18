# core/roi_manager.py
# -*- coding: utf-8 -*-

"""
ROI Manager for Vehicle Counter application
Manages Regions of Interest (ROIs) and counting lines
"""

import logging
import numpy as np
import cv2
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Tuple, Optional, Union

# Setup logger
logger = logging.getLogger(__name__)

class LineDirection(Enum):
    """Direction types for counting lines"""
    NORTH_SOUTH = "north_south"
    EAST_WEST = "east_west"
    BIDIRECTIONAL = "bidirectional"


class ROIDirection(Enum):
    """Direction types for ROIs"""
    IN_OUT = "in_out"
    BIDIRECTIONAL = "bidirectional"


class EditingMode(Enum):
    """ROI Editing modes"""
    NONE = 0
    ROI = 1
    LINE = 2


class ROIManager:
    """Manages Regions of Interest (ROIs) and counting lines"""

    def __init__(self):
        """Initialize ROI manager"""
        # Storage for ROIs and counting lines
        self.rois = {}
        self.counting_lines = {}

        # Editing state
        self.editing_mode = EditingMode.NONE
        self.editing_id = None
        self.temp_points = []

        logger.info("ROI Manager initialized")

    def start_roi_editing(self):
        """Start ROI editing mode"""
        self.editing_mode = EditingMode.ROI
        self.temp_points = []
        logger.info("Started ROI editing mode")
        return True

    def start_line_editing(self):
        """Start line editing mode"""
        self.editing_mode = EditingMode.LINE
        self.temp_points = []
        logger.info("Started line editing mode")
        return True

    def add_point(self, point):
        """
        Add point during editing

        Args:
            point (tuple): Point coordinates (x, y)

        Returns:
            bool: Success status
        """
        if self.editing_mode == EditingMode.NONE:
            return False

        # Add point to temporary storage
        self.temp_points.append(point)

        # For line, limit to 2 points
        if self.editing_mode == EditingMode.LINE and len(self.temp_points) > 2:
            self.temp_points = self.temp_points[:2]

        logger.debug(f"Added point {point} in {self.editing_mode.name} mode")
        return True

    def finish_editing(self):
        """
        Finish editing and save current ROI/line

        Returns:
            tuple: (success, id) - Success status and ID of created item
        """
        if self.editing_mode == EditingMode.NONE:
            return False, None

        # Check if we have enough points
        if self.editing_mode == EditingMode.ROI and len(self.temp_points) < 3:
            logger.warning("Not enough points for ROI, need at least 3")
            return False, None

        if self.editing_mode == EditingMode.LINE and len(self.temp_points) != 2:
            logger.warning("Not enough points for line, need exactly 2")
            return False, None

        # Generate unique ID
        new_id = str(uuid.uuid4())

        # Save based on editing mode
        if self.editing_mode == EditingMode.ROI:
            # Create new ROI
            self.rois[new_id] = {
                "name": f"ROI {len(self.rois) + 1}",
                "points": self.temp_points.copy(),
                "direction": ROIDirection.BIDIRECTIONAL.value,
                "enabled": True
            }
            logger.info(f"Created new ROI with ID {new_id} and {len(self.temp_points)} points")

        elif self.editing_mode == EditingMode.LINE:
            # Create new counting line
            self.counting_lines[new_id] = {
                "name": f"Line {len(self.counting_lines) + 1}",
                "points": self.temp_points.copy(),
                "direction": LineDirection.BIDIRECTIONAL.value,
                "enabled": True
            }
            logger.info(f"Created new counting line with ID {new_id}")

        # Reset editing state
        current_mode = self.editing_mode
        self.editing_mode = EditingMode.NONE
        self.temp_points = []
        self.editing_id = None

        return True, new_id

    def cancel_editing(self):
        """
        Cancel current editing session

        Returns:
            bool: Success status
        """
        if self.editing_mode == EditingMode.NONE:
            return False

        # Reset editing state
        self.editing_mode = EditingMode.NONE
        self.temp_points = []
        self.editing_id = None

        logger.info("Cancelled editing mode")
        return True

    def delete_roi(self, roi_id):
        """
        Delete ROI by ID

        Args:
            roi_id (str): ROI ID to delete

        Returns:
            bool: Success status
        """
        if roi_id in self.rois:
            del self.rois[roi_id]
            logger.info(f"Deleted ROI with ID {roi_id}")
            return True
        return False

    def delete_line(self, line_id):
        """
        Delete counting line by ID

        Args:
            line_id (str): Line ID to delete

        Returns:
            bool: Success status
        """
        if line_id in self.counting_lines:
            del self.counting_lines[line_id]
            logger.info(f"Deleted counting line with ID {line_id}")
            return True
        return False

    def update_roi(self, roi_id, data):
        """
        Update ROI properties

        Args:
            roi_id (str): ROI ID to update
            data (dict): Updated properties

        Returns:
            bool: Success status
        """
        if roi_id not in self.rois:
            return False

        # Update properties
        roi = self.rois[roi_id]

        if "name" in data:
            roi["name"] = data["name"]

        if "direction" in data:
            roi["direction"] = data["direction"]

        if "enabled" in data:
            roi["enabled"] = data["enabled"]

        logger.info(f"Updated ROI with ID {roi_id}")
        return True

    def update_line(self, line_id, data):
        """
        Update counting line properties

        Args:
            line_id (str): Line ID to update
            data (dict): Updated properties

        Returns:
            bool: Success status
        """
        if line_id not in self.counting_lines:
            return False

        # Update properties
        line = self.counting_lines[line_id]

        if "name" in data:
            line["name"] = data["name"]

        if "direction" in data:
            line["direction"] = data["direction"]

        if "enabled" in data:
            line["enabled"] = data["enabled"]

        logger.info(f"Updated counting line with ID {line_id}")
        return True

    def is_point_in_roi(self, point, roi_id):
        """
        Check if point is inside ROI

        Args:
            point (tuple): Point coordinates (x, y)
            roi_id (str): ROI ID to check

        Returns:
            bool: True if point is inside ROI
        """
        if roi_id not in self.rois:
            return False

        # Get ROI points
        roi_points = self.rois[roi_id]["points"]

        # Convert to numpy array for cv2.pointPolygonTest
        roi_points_np = np.array(roi_points, dtype=np.int32)

        # Check if point is inside polygon
        result = cv2.pointPolygonTest(roi_points_np, point, False)

        return result >= 0

    def check_line_crossing(self, prev_point, curr_point, line_id):
        """
        Check if a line has been crossed between previous and current points

        Args:
            prev_point (tuple): Previous point coordinates (x, y)
            curr_point (tuple): Current point coordinates (x, y)
            line_id (str): Line ID to check

        Returns:
            int: Direction of crossing (1 for one direction, -1 for opposite, 0 for no crossing)
        """
        if line_id not in self.counting_lines:
            return 0

        # Get line points
        line_points = self.counting_lines[line_id]["points"]
        if len(line_points) != 2:
            return 0

        # Line segment we're checking
        p1 = line_points[0]
        p2 = line_points[1]

        # Movement line
        q1 = prev_point
        q2 = curr_point

        # Check if lines intersect
        intersection = self._check_lines_intersection(p1, p2, q1, q2)

        if not intersection:
            return 0

        # Determine crossing direction
        # For north_south lines (vertical), positive direction is from left to right
        # For east_west lines (horizontal), positive direction is from bottom to top
        direction = self.counting_lines[line_id]["direction"]

        if direction == LineDirection.NORTH_SOUTH.value:
            # Check if crossing from left to right or right to left
            if q1[0] < q2[0]:  # Moving right
                return 1
            else:  # Moving left
                return -1
        elif direction == LineDirection.EAST_WEST.value:
            # Check if crossing from bottom to top or top to bottom
            if q1[1] > q2[1]:  # Moving up (y decreases)
                return 1
            else:  # Moving down
                return -1
        else:  # Bidirectional
            # Just return 1 for any crossing
            return 1

    def _check_lines_intersection(self, p1, p2, q1, q2):
        """
        Check if two line segments intersect

        Args:
            p1, p2: Points of first line segment
            q1, q2: Points of second line segment

        Returns:
            bool: True if lines intersect
        """
        # Convert to numpy for vector operations
        p1 = np.array(p1)
        p2 = np.array(p2)
        q1 = np.array(q1)
        q2 = np.array(q2)

        def ccw(A, B, C):
            """Check if three points are counter-clockwise"""
            return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])

        # Check if lines intersect
        return ccw(p1, q1, q2) != ccw(p2, q1, q2) and ccw(p1, p2, q1) != ccw(p1, p2, q2)

    def draw_rois(self, frame):
        """
        Draw all ROIs on frame

        Args:
            frame (numpy.ndarray): Frame to draw on

        Returns:
            numpy.ndarray: Frame with ROIs drawn
        """
        # Make a copy of frame to draw on
        draw_frame = frame.copy()

        # Draw each ROI
        for roi_id, roi in self.rois.items():
            if not roi.get("enabled", True):
                continue

            # Get points
            points = np.array(roi["points"], np.int32)
            points = points.reshape((-1, 1, 2))

            # Draw filled polygon with transparency
            overlay = draw_frame.copy()
            cv2.fillPoly(overlay, [points], (0, 200, 0, 64))
            cv2.addWeighted(overlay, 0.4, draw_frame, 0.6, 0, draw_frame)

            # Draw polygon outline
            cv2.polylines(draw_frame, [points], True, (0, 255, 0), 2)

            # Draw name
            name = roi.get("name", f"ROI {roi_id[:4]}")
            text_pos = roi["points"][0]
            cv2.putText(draw_frame, name, text_pos, cv2.FONT_HERSHEY_SIMPLEX,
                        0.8, (0, 255, 0), 2)

        return draw_frame

    def draw_counting_lines(self, frame):
        """
        Draw all counting lines on frame

        Args:
            frame (numpy.ndarray): Frame to draw on

        Returns:
            numpy.ndarray: Frame with counting lines drawn
        """
        # Make a copy of frame to draw on
        draw_frame = frame.copy()

        # Draw each counting line
        for line_id, line in self.counting_lines.items():
            if not line.get("enabled", True):
                continue

            # Get points
            if len(line["points"]) != 2:
                continue

            p1 = tuple(map(int, line["points"][0]))
            p2 = tuple(map(int, line["points"][1]))

            # Draw line
            cv2.line(draw_frame, p1, p2, (0, 0, 255), 2)

            # Draw direction indicator
            direction = line.get("direction", LineDirection.BIDIRECTIONAL.value)

            # Draw arrow indicating direction
            mid_point = ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2)

            if direction == LineDirection.NORTH_SOUTH.value:
                # Draw horizontal arrows
                arrow_size = 15
                cv2.arrowedLine(draw_frame,
                                (mid_point[0] - arrow_size, mid_point[1]),
                                (mid_point[0] + arrow_size, mid_point[1]),
                                (0, 0, 255), 2, tipLength=0.3)

            elif direction == LineDirection.EAST_WEST.value:
                # Draw vertical arrows
                arrow_size = 15
                cv2.arrowedLine(draw_frame,
                                (mid_point[0], mid_point[1] + arrow_size),
                                (mid_point[0], mid_point[1] - arrow_size),
                                (0, 0, 255), 2, tipLength=0.3)

            elif direction == LineDirection.BIDIRECTIONAL.value:
                # Draw bidirectional arrows
                dx = p2[0] - p1[0]
                dy = p2[1] - p1[1]
                length = np.sqrt(dx*dx + dy*dy)

                if length > 0:
                    # Normalize
                    dx /= length
                    dy /= length

                    # Create perpendicular vector
                    perp_dx = -dy
                    perp_dy = dx

                    # Arrow size
                    arrow_size = 15

                    # Arrow points
                    arrow_p1 = (int(mid_point[0] + perp_dx * arrow_size),
                                int(mid_point[1] + perp_dy * arrow_size))

                    arrow_p2 = (int(mid_point[0] - perp_dx * arrow_size),
                                int(mid_point[1] - perp_dy * arrow_size))

                    # Draw bidirectional arrow
                    cv2.arrowedLine(draw_frame, arrow_p1, arrow_p2, (0, 0, 255), 2, tipLength=0.3)
                    cv2.arrowedLine(draw_frame, arrow_p2, arrow_p1, (0, 0, 255), 2, tipLength=0.3)

            # Draw name
            name = line.get("name", f"Line {line_id[:4]}")
            text_pos = (p1[0], p1[1] - 10)
            cv2.putText(draw_frame, name, text_pos, cv2.FONT_HERSHEY_SIMPLEX,
                        0.8, (0, 0, 255), 2)

        return draw_frame

    def get_all_rois(self):
        """
        Get all ROIs

        Returns:
            dict: Dictionary of ROIs
        """
        return self.rois.copy()

    def get_all_counting_lines(self):
        """
        Get all counting lines

        Returns:
            dict: Dictionary of counting lines
        """
        return self.counting_lines.copy()

    def clear_all(self):
        """Clear all ROIs and counting lines"""
        self.rois.clear()
        self.counting_lines.clear()
        logger.info("Cleared all ROIs and counting lines")
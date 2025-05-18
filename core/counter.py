"""
Vehicle counter module for Vehicle Counter application
Counts vehicles passing through ROIs and crossing lines
"""

import logging
import numpy as np
import cv2
import time
from collections import defaultdict

# Setup logger
logger = logging.getLogger(__name__)

class VehicleCounter:
    """Counts vehicles passing through ROIs or crossing lines"""

    def __init__(self, roi_manager):
        """
        Initialize counter

        Args:
            roi_manager: ROI manager instance
        """
        self.roi_manager = roi_manager

        # Counters
        self.roi_counts = defaultdict(int)
        self.line_counts = defaultdict(int)

        # Track objects inside ROIs
        self.objects_in_roi = defaultdict(set)

        # Track last positions
        self.last_positions = {}

        # Count events for visualization
        self.count_events = []
        self.max_events = 10
        self.event_duration = 2.0  # seconds

        logger.info("Vehicle counter initialized")

    def update(self, tracked_objects):
        """
        Update counter with tracked objects

        Args:
            tracked_objects (dict): Dictionary of tracked objects

        Returns:
            dict: Counting results
        """
        # Prepare results
        results = {
            "roi_events": [],
            "line_events": [],
            "roi_counts": dict(self.roi_counts),
            "line_counts": dict(self.line_counts),
            "roi_totals": {},
            "line_totals": {}
        }

        # Update each object
        for object_id, object_data in tracked_objects.items():
            # Skip if object has disappeared
            if object_data["disappeared"] > 0:
                continue

            # Get current position
            box = object_data["box"]
            centroid = object_data["centroid"]

            # Check ROIs
            self._check_roi_counts(object_id, centroid, box, results)

            # Check lines (needs previous position)
            prev_centroid = self.last_positions.get(object_id)
            if prev_centroid:
                self._check_line_counts(object_id, prev_centroid, centroid, results)

            # Update last position
            self.last_positions[object_id] = centroid

        # Remove old objects from tracking
        for object_id in list(self.last_positions.keys()):
            if object_id not in tracked_objects or tracked_objects[object_id]["disappeared"] > 0:
                self.last_positions.pop(object_id, None)

                # Remove from ROI tracking
                for roi_id in self.objects_in_roi:
                    self.objects_in_roi[roi_id].discard(object_id)

        # Update count totals
        for roi_id in self.roi_counts:
            results["roi_totals"][roi_id] = self.roi_counts[roi_id]

        for line_id in self.line_counts:
            results["line_totals"][line_id] = self.line_counts[line_id]

        # Update and clean up count events
        self._update_count_events()
        results["count_events"] = self.count_events.copy()

        return results

    def _check_roi_counts(self, object_id, centroid, box, results):
        """
        Check if object is entering or leaving ROIs

        Args:
            object_id (int): Object ID
            centroid (tuple): Object centroid
            box (list): Object bounding box
            results (dict): Results dictionary to update
        """
        # Check each ROI
        for roi_id, roi in self.roi_manager.get_all_rois().items():
            if not roi.get("enabled", True):
                continue

            # Check if centroid is in ROI
            in_roi = self.roi_manager.is_point_in_roi(centroid, roi_id)

            # If object was not in ROI but now is, count it
            if in_roi and object_id not in self.objects_in_roi[roi_id]:
                # Add to objects in ROI
                self.objects_in_roi[roi_id].add(object_id)

                # Increment count
                self.roi_counts[roi_id] += 1

                # Add count event
                event = {
                    "type": "roi",
                    "roi_id": roi_id,
                    "object_id": object_id,
                    "position": centroid,
                    "timestamp": time.time(),
                    "count": self.roi_counts[roi_id]
                }

                self.count_events.append(event)
                results["roi_events"].append(event)

                logger.debug(f"Object {object_id} entered ROI {roi_id}, count: {self.roi_counts[roi_id]}")

            # If object was in ROI but now isn't, track exit
            elif not in_roi and object_id in self.objects_in_roi[roi_id]:
                # Remove from objects in ROI
                self.objects_in_roi[roi_id].discard(object_id)
                logger.debug(f"Object {object_id} exited ROI {roi_id}")

    def _check_line_counts(self, object_id, prev_centroid, curr_centroid, results):
        """
        Check if object is crossing counting lines

        Args:
            object_id (int): Object ID
            prev_centroid (tuple): Previous object centroid
            curr_centroid (tuple): Current object centroid
            results (dict): Results dictionary to update
        """
        # Check each counting line
        for line_id, line in self.roi_manager.get_all_counting_lines().items():
            if not line.get("enabled", True):
                continue

            # Check if line was crossed
            crossing_direction = self.roi_manager.check_line_crossing(
                prev_centroid, curr_centroid, line_id
            )

            if crossing_direction != 0:
                # Increment count
                self.line_counts[line_id] += 1

                # Add count event
                event = {
                    "type": "line",
                    "line_id": line_id,
                    "object_id": object_id,
                    "position": curr_centroid,
                    "timestamp": time.time(),
                    "direction": crossing_direction,
                    "count": self.line_counts[line_id]
                }

                self.count_events.append(event)
                results["line_events"].append(event)

                logger.debug(f"Object {object_id} crossed line {line_id}, "
                             f"direction: {crossing_direction}, count: {self.line_counts[line_id]}")

    def _update_count_events(self):
        """Update and clean up count events"""
        current_time = time.time()

        # Remove old events
        self.count_events = [
            event for event in self.count_events
            if current_time - event["timestamp"] < self.event_duration
        ]

        # Limit number of events
        if len(self.count_events) > self.max_events:
            self.count_events = self.count_events[-self.max_events:]

    def draw_count_overlay(self, frame, show_events=True):
        """
        Draw counting information on frame

        Args:
            frame (numpy.ndarray): Frame to draw on
            show_events (bool): Whether to show counting events

        Returns:
            numpy.ndarray: Frame with count overlay
        """
        # Make a copy of frame
        draw_frame = frame.copy()

        # Draw ROI counts
        y_pos = 30
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.6
        thickness = 2

        # Draw counts in corner
        counts_text = []

        # ROI counts
        for roi_id, roi in self.roi_manager.get_all_rois().items():
            if not roi.get("enabled", True):
                continue

            name = roi.get("name", f"ROI {roi_id[:4]}")
            count = self.roi_counts.get(roi_id, 0)
            counts_text.append(f"{name}: {count}")

        # Line counts
        for line_id, line in self.roi_manager.get_all_counting_lines().items():
            if not line.get("enabled", True):
                continue

            name = line.get("name", f"Line {line_id[:4]}")
            count = self.line_counts.get(line_id, 0)
            counts_text.append(f"{name}: {count}")

        # Draw counts box
        if counts_text:
            # Calculate box size
            max_width = 0
            for text in counts_text:
                (text_w, text_h), _ = cv2.getTextSize(text, font, font_scale, thickness)
                max_width = max(max_width, text_w)

            # Draw background
            padding = 10
            box_height = len(counts_text) * 30 + padding * 2
            cv2.rectangle(draw_frame,
                          (10, 10),
                          (max_width + 20, box_height),
                          (0, 0, 0, 128), -1)

            # Draw count texts
            y = 35
            for text in counts_text:
                cv2.putText(draw_frame, text, (15, y), font, font_scale, (255, 255, 255), thickness)
                y += 30

        # Draw recent count events
        if show_events:
            current_time = time.time()

            for event in self.count_events:
                # Calculate fade based on time
                age = current_time - event["timestamp"]
                if age > self.event_duration:
                    continue

                # Fade from 1.0 to 0.0
                alpha = 1.0 - (age / self.event_duration)

                # Draw circle at event position
                position = event["position"]
                if event["type"] == "roi":
                    # Red circle for ROI events
                    color = (0, 0, int(255 * alpha))
                    radius = int(20 * alpha) + 5
                else:
                    # Blue circle for line events
                    color = (int(255 * alpha), 0, 0)
                    radius = int(15 * alpha) + 5

                cv2.circle(draw_frame, position, radius, color, 2)

                # Draw count
                count = event.get("count", 0)
                cv2.putText(draw_frame, str(count),
                            (position[0] - 10, position[1] + 5),
                            font, 0.7, color, 2)

        return draw_frame

    def reset_counts(self):
        """Reset all counters"""
        self.roi_counts.clear()
        self.line_counts.clear()
        self.objects_in_roi.clear()
        self.count_events.clear()
        logger.info("Counter reset")

    def export_counts(self):
        """
        Export counting data

        Returns:
            dict: Count data
        """
        return {
            "roi_counts": dict(self.roi_counts),
            "line_counts": dict(self.line_counts),
            "timestamp": time.time()
        }

    def reset(self):
        """Alias ke reset_counts, supaya GUI bisa panggil .reset()."""
        self.reset_counts()
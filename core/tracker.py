#core/tracker.py
# -*- coding: utf-8 -*-

"""
Vehicle tracking module
Uses simple tracking algorithm based on IoU (Intersection over Union)
"""

import cv2
import numpy as np
from collections import defaultdict, deque

from config.settings import COLORS

class VehicleTracker:
    """
    Track vehicles across frames using IoU (Intersection over Union)
    """
    def __init__(self,
                 max_disappeared=10,
                 min_iou_threshold=0.3,
                 max_distance=150,
                 track_history_size=30):
        """
        Initialize tracker

        Args:
            max_disappeared (int): Max frames before track is deleted
            min_iou_threshold (float): Min IoU to consider a match
            max_distance (int): Max distance between centroids to consider a match
            track_history_size (int): Number of positions to keep in history
        """
        self.next_object_id = 0
        self.objects = {}  # {object_id: bbox}
        self.disappeared = defaultdict(int)  # {object_id: disappeared_count}
        self.class_ids = {}  # {object_id: class_id}
        self.class_names = {}  # {object_id: class_name}
        self.trajectories = defaultdict(lambda: deque(maxlen=track_history_size))  # {object_id: deque([center_points])}

        self.max_disappeared = max_disappeared
        self.min_iou_threshold = min_iou_threshold
        self.max_distance = max_distance

    def register(self, bbox, class_id, class_name):
        """
        Register new object

        Args:
            bbox (list): [x1, y1, x2, y2]
            class_id (int): Class ID
            class_name (str): Class name
        """
        self.objects[self.next_object_id] = bbox
        self.class_ids[self.next_object_id] = class_id
        self.class_names[self.next_object_id] = class_name

        # Store center point for trajectory
        center_x = (bbox[0] + bbox[2]) // 2
        center_y = (bbox[1] + bbox[3]) // 2
        self.trajectories[self.next_object_id].append((center_x, center_y))

        self.next_object_id += 1

    def deregister(self, object_id):
        """
        Deregister an object

        Args:
            object_id (int): Object ID to deregister
        """
        del self.objects[object_id]
        del self.disappeared[object_id]
        del self.class_ids[object_id]
        del self.class_names[object_id]
        del self.trajectories[object_id]

    def get_center(self, bbox):
        """
        Get center point from bbox

        Args:
            bbox (list): [x1, y1, x2, y2]

        Returns:
            tuple: (center_x, center_y)
        """
        return ((bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2)

    def calculate_iou(self, bbox1, bbox2):
        """
        Calculate IoU between two boxes

        Args:
            bbox1 (list): [x1, y1, x2, y2]
            bbox2 (list): [x1, y1, x2, y2]

        Returns:
            float: IoU value
        """
        # Determine intersection rectangle
        x_left = max(bbox1[0], bbox2[0])
        y_top = max(bbox1[1], bbox2[1])
        x_right = min(bbox1[2], bbox2[2])
        y_bottom = min(bbox1[3], bbox2[3])

        # No intersection
        if x_right < x_left or y_bottom < y_top:
            return 0.0

        # Calculate area of intersection rectangle
        intersection_area = (x_right - x_left) * (y_bottom - y_top)

        # Calculate area of both boxes
        bbox1_area = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
        bbox2_area = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])

        # Calculate IoU
        iou = intersection_area / float(bbox1_area + bbox2_area - intersection_area)

        return iou

    def calculate_distance(self, center1, center2):
        """
        Calculate Euclidean distance between two points

        Args:
            center1 (tuple): (x, y)
            center2 (tuple): (x, y)

        Returns:
            float: Distance value
        """
        return np.sqrt((center1[0] - center2[0])**2 + (center1[1] - center2[1])**2)

    def update(self, bboxes, class_ids, class_names):
        """
        Update tracker with new detections

        Args:
            bboxes (list): List of [x1, y1, x2, y2]
            class_ids (list): List of class IDs
            class_names (list): List of class names

        Returns:
            dict: Tracking results with object IDs
        """
        # If no boxes, increment disappeared count for all objects
        if len(bboxes) == 0:
            for object_id in list(self.disappeared.keys()):
                self.disappeared[object_id] += 1

                # Deregister if object has been missing for too long
                if self.disappeared[object_id] > self.max_disappeared:
                    self.deregister(object_id)

            return self.get_tracking_results()

        # If no existing objects to track, register all as new
        if len(self.objects) == 0:
            for i, bbox in enumerate(bboxes):
                self.register(bbox, class_ids[i], class_names[i])

        else:
            # Get existing object IDs and bboxes
            object_ids = list(self.objects.keys())
            existing_bboxes = list(self.objects.values())

            # Calculate IoU and distance matrix between existing and new boxes
            iou_matrix = np.zeros((len(existing_bboxes), len(bboxes)))
            distance_matrix = np.zeros((len(existing_bboxes), len(bboxes)))

            for i, existing_bbox in enumerate(existing_bboxes):
                existing_center = self.get_center(existing_bbox)
                for j, new_bbox in enumerate(bboxes):
                    # Calculate IoU
                    iou_matrix[i, j] = self.calculate_iou(existing_bbox, new_bbox)

                    # Calculate distance
                    new_center = self.get_center(new_bbox)
                    distance_matrix[i, j] = self.calculate_distance(existing_center, new_center)

            # Create cost matrix combining IoU and distance
            # Higher IoU is better (lower cost), lower distance is better (lower cost)
            cost_matrix = (1 - iou_matrix) * (distance_matrix / self.max_distance)

            # Get matched indices with Hungarian algorithm (from IoU matrix)
            # Use negative because the algorithm finds minimum cost matching
            rows, cols = np.where(iou_matrix > self.min_iou_threshold)
            used_rows = set()
            used_cols = set()

            # Match based on cost matrix
            matches = []
            for row, col in sorted(zip(rows, cols), key=lambda x: cost_matrix[x[0], x[1]]):
                if row in used_rows or col in used_cols:
                    continue

                matches.append((row, col))
                used_rows.add(row)
                used_cols.add(col)

            # Process unmatched rows (existing objects without matches)
            unmatched_rows = set(range(len(existing_bboxes))) - used_rows
            for row in unmatched_rows:
                object_id = object_ids[row]
                self.disappeared[object_id] += 1

                # Deregister if object has been missing for too long
                if self.disappeared[object_id] > self.max_disappeared:
                    self.deregister(object_id)

            # Process unmatched columns (new detections without matches)
            unmatched_cols = set(range(len(bboxes))) - used_cols
            for col in unmatched_cols:
                self.register(bboxes[col], class_ids[col], class_names[col])

            # Update matched objects
            for row, col in matches:
                object_id = object_ids[row]
                self.objects[object_id] = bboxes[col]

                # Reset disappeared counter
                self.disappeared[object_id] = 0

                # Update class info (could change due to better detection)
                self.class_ids[object_id] = class_ids[col]
                self.class_names[object_id] = class_names[col]

                # Update trajectory
                center = self.get_center(bboxes[col])
                self.trajectories[object_id].append(center)

        # Return tracking results
        return self.get_tracking_results()

    def get_tracking_results(self):
        """
        Get current tracking results

        Returns:
            dict: Tracking results
        """
        results = {
            "object_ids": [],
            "bboxes": [],
            "class_ids": [],
            "class_names": [],
            "trajectories": [],
            "centers": []
        }

        for object_id in self.objects:
            # Skip objects that have disappeared
            if self.disappeared[object_id] > 0:
                continue

            results["object_ids"].append(object_id)
            results["bboxes"].append(self.objects[object_id])
            results["class_ids"].append(self.class_ids[object_id])
            results["class_names"].append(self.class_names[object_id])
            results["trajectories"].append(list(self.trajectories[object_id]))
            results["centers"].append(self.get_center(self.objects[object_id]))

        return results

    def draw_tracking(self, frame, draw_ids=True, draw_boxes=True, draw_trajectories=True):
        """
        Draw tracking results on frame

        Args:
            frame (numpy.ndarray): Frame to draw on
            draw_ids (bool): Draw object IDs
            draw_boxes (bool): Draw bounding boxes
            draw_trajectories (bool): Draw object trajectories

        Returns:
            numpy.ndarray: Frame with tracking visualization
        """
        results = self.get_tracking_results()

        # Draw bounding boxes and IDs
        for i, bbox in enumerate(results["bboxes"]):
            object_id = results["object_ids"][i]
            class_name = results["class_names"][i]
            color = COLORS.get(class_name, (0, 255, 0))

            # Draw bounding box
            if draw_boxes:
                x1, y1, x2, y2 = bbox
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            # Draw object ID
            if draw_ids:
                x1, y1, _, _ = bbox
                cv2.putText(frame, f"ID: {object_id}", (x1, y1 - 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            # Draw trajectories
            if draw_trajectories and len(results["trajectories"][i]) > 1:
                traj_points = results["trajectories"][i]
                # Draw lines connecting trajectory points
                for j in range(1, len(traj_points)):
                    thickness = int(np.sqrt(64 / float(j + 1)) * 2)
                    cv2.line(frame, traj_points[j - 1], traj_points[j], color, thickness)

        return frame

    def reset(self):
        """Reset tracker state"""
        self.next_object_id = 0
        self.objects.clear()
        self.disappeared.clear()
        self.class_ids.clear()
        self.class_names.clear()
        self.trajectories.clear()
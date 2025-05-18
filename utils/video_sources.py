# utils/video_sources.py
# -*- coding: utf-8 -*-

"""
Video source management for the Vehicle Counter application
Handles various video sources (RTSP, webcam, file)
"""

import cv2
import time
import threading
import queue
from enum import Enum

class SourceType(Enum):
    """Enum for video source types"""
    FILE = "file"
    RTSP = "rtsp"
    WEBCAM = "webcam"

class VideoSource:
    """Base class for video sources"""
    def __init__(self, source_path, buffer_size=10):
        """
        Initialize video source

        Args:
            source_path (str): Path or ID of video source
            buffer_size (int): Size of frame buffer for threaded capture
        """
        self.source_path = source_path
        self.buffer_size = buffer_size
        self.cap = None
        self.is_opened = False
        self.is_running = False
        self.frame_width = 0
        self.frame_height = 0
        self.fps = 0

        # Threaded capture variables
        self.thread = None
        self.frame_buffer = queue.Queue(maxsize=buffer_size)
        self.last_frame = None
        self.frame_count = 0

    def open(self):
        """Open video source"""
        try:
            self.cap = cv2.VideoCapture(self.source_path)
            self.is_opened = self.cap.isOpened()

            if self.is_opened:
                # Get video properties
                self.frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                self.frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                self.fps = self.cap.get(cv2.CAP_PROP_FPS)

                print(f"Video source opened: {self.source_path}")
                print(f"Resolution: {self.frame_width}x{self.frame_height}, FPS: {self.fps}")

                return True
            else:
                print(f"Failed to open video source: {self.source_path}")
                return False
        except Exception as e:
            print(f"Error opening video source: {str(e)}")
            self.is_opened = False
            return False

    def start(self):
        """Start threaded frame capture"""
        if not self.is_opened and not self.open():
            return False

        if self.is_running:
            return True

        self.is_running = True
        self.thread = threading.Thread(target=self._capture_thread, daemon=True)
        self.thread.start()

        return True

    def _capture_thread(self):
        """Thread function for frame capture"""
        while self.is_running:
            if not self.is_opened:
                time.sleep(0.1)
                continue

            ret, frame = self.cap.read()

            if not ret:
                # Try to reopen on failure (for RTSP)
                print("Frame capture failed, attempting to reopen source...")
                self.is_opened = False
                self.cap.release()
                time.sleep(1.0)
                self.open()
                continue

            # Update frame count
            self.frame_count += 1

            # Store frame
            self.last_frame = frame

            # Add to buffer (if not full)
            try:
                self.frame_buffer.put(frame, block=False)
            except queue.Full:
                # Skip frame if buffer is full
                self.frame_buffer.get()  # Remove oldest frame
                self.frame_buffer.put(frame)  # Add new frame

    def read(self):
        """
        Read next frame

        Returns:
            tuple: (success, frame)
        """
        if not self.is_running:
            self.start()

        if not self.is_opened:
            return False, None

        # Threaded mode
        if self.thread is not None:
            try:
                frame = self.frame_buffer.get(timeout=1.0)
                return True, frame
            except queue.Empty:
                # If buffer is empty but we have a last frame
                if self.last_frame is not None:
                    return True, self.last_frame.copy()
                return False, None

        # Non-threaded fallback
        return self.cap.read()

    def stop(self):
        """Stop video capture"""
        self.is_running = False

        if self.thread is not None:
            self.thread.join(timeout=1.0)
            self.thread = None

        # Clear buffer
        while not self.frame_buffer.empty():
            try:
                self.frame_buffer.get(block=False)
            except queue.Empty:
                break

    def release(self):
        """Release resources"""
        self.stop()

        if self.cap is not None:
            self.cap.release()
            self.cap = None

        self.is_opened = False
        self.last_frame = None
        self.frame_count = 0

    def get_info(self):
        """
        Get source information

        Returns:
            dict: Source information
        """
        return {
            "source_path": self.source_path,
            "is_opened": self.is_opened,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "fps": self.fps,
            "frames_processed": self.frame_count
        }


class FileVideoSource(VideoSource):
    """Video file source"""
    def __init__(self, file_path, loop=False, buffer_size=10):
        """
        Initialize file video source

        Args:
            file_path (str): Path to video file
            loop (bool): Whether to loop video
            buffer_size (int): Size of frame buffer
        """
        super().__init__(file_path, buffer_size)
        self.loop = loop
        self.source_type = SourceType.FILE

    def _capture_thread(self):
        """Thread function for file capture with loop support"""
        while self.is_running:
            if not self.is_opened:
                time.sleep(0.1)
                continue

            ret, frame = self.cap.read()

            if not ret:
                # End of video, reopen if looping
                if self.loop:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    # Signal end of video
                    self.is_running = False
                    break

            # Update frame count
            self.frame_count += 1

            # Store frame
            self.last_frame = frame

            # Add to buffer (if not full)
            try:
                self.frame_buffer.put(frame, block=False)
            except queue.Full:
                # Skip frame if buffer is full
                self.frame_buffer.get()  # Remove oldest frame
                self.frame_buffer.put(frame)  # Add new frame


class RTSPVideoSource(VideoSource):
    """RTSP video source with reconnection logic"""
    def __init__(self, rtsp_url, reconnect_interval=5, buffer_size=10):
        """
        Initialize RTSP video source

        Args:
            rtsp_url (str): RTSP URL
            reconnect_interval (int): Seconds to wait before reconnect
            buffer_size (int): Size of frame buffer
        """
        super().__init__(rtsp_url, buffer_size)
        self.reconnect_interval = reconnect_interval
        self.source_type = SourceType.RTSP

    def open(self):
        """Open RTSP source with optimized settings"""
        try:
            # Set OpenCV options for RTSP
            self.cap = cv2.VideoCapture(self.source_path, cv2.CAP_FFMPEG)

            # Set buffer size
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)

            self.is_opened = self.cap.isOpened()

            if self.is_opened:
                # Get video properties
                self.frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                self.frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                self.fps = self.cap.get(cv2.CAP_PROP_FPS)

                print(f"RTSP source opened: {self.source_path}")
                print(f"Resolution: {self.frame_width}x{self.frame_height}, FPS: {self.fps}")

                return True
            else:
                print(f"Failed to open RTSP source: {self.source_path}")
                return False
        except Exception as e:
            print(f"Error opening RTSP source: {str(e)}")
            self.is_opened = False
            return False


class WebcamVideoSource(VideoSource):
    """Webcam video source"""
    def __init__(self, device_id=0, buffer_size=10):
        """
        Initialize webcam source

        Args:
            device_id (int): Camera device ID
            buffer_size (int): Size of frame buffer
        """
        super().__init__(device_id, buffer_size)
        self.source_type = SourceType.WEBCAM

    def open(self):
        """Open webcam with optimized settings"""
        try:
            # Open webcam
            self.cap = cv2.VideoCapture(self.source_path)

            # Try to set some common webcam properties
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            self.cap.set(cv2.CAP_PROP_FPS, 30)

            self.is_opened = self.cap.isOpened()

            if self.is_opened:
                # Get actual video properties
                self.frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                self.frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                self.fps = self.cap.get(cv2.CAP_PROP_FPS)

                print(f"Webcam opened: {self.source_path}")
                print(f"Resolution: {self.frame_width}x{self.frame_height}, FPS: {self.fps}")

                return True
            else:
                print(f"Failed to open webcam: {self.source_path}")
                return False
        except Exception as e:
            print(f"Error opening webcam: {str(e)}")
            self.is_opened = False
            return False


def create_video_source(source_type, source_path, **kwargs):
    """
    Factory function to create appropriate video source

    Args:
        source_type (str): Type of source ('file', 'rtsp', 'webcam')
        source_path (str): Path to source
        **kwargs: Additional source-specific parameters

    Returns:
        VideoSource: Initialized video source
    """
    if source_type.lower() == 'file':
        return FileVideoSource(source_path,
                               loop=kwargs.get('loop', False),
                               buffer_size=kwargs.get('buffer_size', 10))
    elif source_type.lower() == 'rtsp':
        return RTSPVideoSource(source_path,
                               reconnect_interval=kwargs.get('reconnect_interval', 5),
                               buffer_size=kwargs.get('buffer_size', 10))
    elif source_type.lower() == 'webcam':
        try:
            device_id = int(source_path)
        except ValueError:
            device_id = 0
        return WebcamVideoSource(device_id,
                                 buffer_size=kwargs.get('buffer_size', 10))
    else:
        raise ValueError(f"Unknown source type: {source_type}")
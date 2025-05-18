# direct_video_display.py
# Tempatkan file ini di direktori root proyek

"""
Module untuk menghubungkan langsung video source ke stream view,
melewati jalur pemrosesan yang kompleks untuk debug.
"""

import cv2
import logging
import traceback
import time
from PyQt5.QtCore import QObject, QTimer, pyqtSignal, Qt

# Setup logger
logger = logging.getLogger(__name__)

class DirectVideoDisplay(QObject):
    """
    Kelas sederhana untuk langsung menampilkan video ke stream view
    tanpa pemrosesan kompleks, berguna untuk debugging
    """

    # Signal untuk update status
    status_updated = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.video_source = None
        self.stream_view = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.frame_count = 0
        self.fps = 30
        self.running = False

    def setup(self, video_source, stream_view):
        """Setup sumber video dan view target"""
        self.video_source = video_source
        self.stream_view = stream_view

        # Adjust timer interval based on source fps
        if hasattr(video_source, 'fps') and video_source.fps > 0:
            self.fps = video_source.fps
            interval_ms = int(1000 / self.fps)
            self.timer.setInterval(interval_ms)
        else:
            self.timer.setInterval(33)  # ~30 fps default

        logger.info(f"DirectVideoDisplay setup with FPS: {self.fps}")

    def start(self):
        """Mulai menampilkan video"""
        if not self.video_source or not self.stream_view:
            logger.error("Cannot start - video source or stream view not set")
            self.status_updated.emit("Error: Missing video source or stream view")
            return False

        if not self.video_source.is_opened:
            logger.error("Cannot start - video source not opened")
            self.status_updated.emit("Error: Video source not opened")
            return False

        # Reset posisi untuk file video
        if hasattr(self.video_source, 'cap'):
            try:
                self.video_source.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            except Exception as e:
                logger.warning(f"Could not reset video position: {str(e)}")

        self.running = True
        self.timer.start()
        logger.info("DirectVideoDisplay started")
        self.status_updated.emit("Direct video display started")
        return True

    def stop(self):
        """Stop menampilkan video"""
        self.running = False
        self.timer.stop()
        logger.info("DirectVideoDisplay stopped")
        self.status_updated.emit("Direct video display stopped")

    def update_frame(self):
        """Update frame dari video source ke stream view"""
        if not self.running or not self.video_source or not self.stream_view:
            return

        try:
            # Baca frame dari video source
            ret, frame = self.video_source.read()

            if not ret or frame is None:
                logger.warning("Failed to read frame or end of video")
                if hasattr(self.video_source, 'cap'):
                    # Reset untuk file video
                    self.video_source.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    # Baca frame lagi setelah reset
                    ret, frame = self.video_source.read()
                    if not ret or frame is None:
                        logger.error("Failed to read frame after reset")
                        self.status_updated.emit("Error: Failed to read video frame")
                        return
                else:
                    # Tidak bisa reset untuk sumber lain
                    self.status_updated.emit("End of video or read error")
                    return

            # Update status setiap 30 frame
            self.frame_count += 1
            if self.frame_count % 30 == 0:
                self.status_updated.emit(f"Frame: {self.frame_count}")

            # Tampilkan frame ke stream view
            self.stream_view.update_frame(frame)

        except Exception as e:
            logger.error(f"Error updating frame: {str(e)}")
            logger.debug(traceback.format_exc())
            self.status_updated.emit(f"Error: {str(e)}")
# Perbaikan Tambahan untuk Koneksi Antara Komponen

# 1. Patch script untuk mendiagnosis masalah frame (tempatkan di file baru test_pipeline.py)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test script untuk mendiagnosis alur data frame video
"""

import os
import sys
import cv2
import numpy as np
import time
from pathlib import Path

# Tambahkan root dir ke python path
root_dir = Path(__file__).resolve().parent
sys.path.append(str(root_dir))

from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QLabel
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap

class TestVideoDisplay(QMainWindow):
    """Window test sederhana untuk menampilkan frame video"""

    def __init__(self, video_path):
        super().__init__()
        self.video_path = video_path
        self.frame_count = 0

        # Setup UI
        self.setWindowTitle("Video Test")
        self.setGeometry(100, 100, 800, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Label untuk menampilkan video
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: black;")
        layout.addWidget(self.image_label)

        # Label status
        self.status_label = QLabel("Status: Ready")
        layout.addWidget(self.status_label)

        # Button untuk start/stop
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.toggle_video)
        layout.addWidget(self.start_button)

        # Video capture
        self.cap = None
        self.is_playing = False

        # Timer untuk update frame
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.setInterval(33)  # ~30 fps

    def toggle_video(self):
        """Start atau stop video"""
        if not self.is_playing:
            # Start video
            if self.cap is None or not self.cap.isOpened():
                self.cap = cv2.VideoCapture(self.video_path)
                if not self.cap.isOpened():
                    self.status_label.setText(f"Error: Could not open {self.video_path}")
                    return

            self.is_playing = True
            self.start_button.setText("Stop")
            self.timer.start()
            self.status_label.setText("Status: Playing")
        else:
            # Stop video
            self.is_playing = False
            self.timer.stop()
            self.start_button.setText("Start")
            self.status_label.setText("Status: Stopped")

    def update_frame(self):
        """Update frame dari video"""
        if self.cap is None or not self.cap.isOpened():
            return

        ret, frame = self.cap.read()
        if not ret:
            # Reset video jika sudah selesai
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            return

        self.frame_count += 1

        # Convert BGR ke RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Convert ke QImage
        h, w, ch = rgb_frame.shape
        bytes_per_line = ch * w
        q_img = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()

        # Convert ke QPixmap dan tampilkan
        pixmap = QPixmap.fromImage(q_img)

        # Resize pixmap untuk fit label
        pixmap = pixmap.scaled(
            self.image_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        # Set pixmap ke label
        self.image_label.setPixmap(pixmap)

        # Update status
        self.status_label.setText(f"Status: Playing - Frame {self.frame_count} - Size: {w}x{h}")

    def closeEvent(self, event):
        """Handle window close"""
        if self.cap is not None:
            self.cap.release()
        event.accept()


def main():
    """Main function"""
    # Parse arguments
    import argparse
    parser = argparse.ArgumentParser(description="Test video display")
    parser.add_argument("video_path", help="Path to video file")
    args = parser.parse_args()

    # Ensure video exists
    if not os.path.exists(args.video_path):
        print(f"Error: Video file not found: {args.video_path}")
        return 1

    # Create QApplication
    app = QApplication(sys.argv)

    # Create and show window
    window = TestVideoDisplay(args.video_path)
    window.show()

    # Run app
    return app.exec_()

if __name__ == "__main__":
    sys.exit(main())
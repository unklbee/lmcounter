# debug_override.py
# Tempatkan file ini di root proyek dan jalankan "python debug_override.py" sebagai alternatif

"""
Script debug untuk memaksa tampilan video dengan pendekatan sederhana
"""

import os
import sys
import time
import logging
import traceback
from pathlib import Path

# Pastikan path proyek ada di sys.path
root_dir = Path(__file__).resolve().parent
sys.path.append(str(root_dir))

# Konfigurasi logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s | %(levelname)8s | %(name)25s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Import Qt
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QLabel, QComboBox, \
    QFileDialog, QHBoxLayout
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import QImage, QPixmap

# Import komponen video
import cv2
import numpy as np

class SimpleVideoThread(QThread):
    """Thread sederhana untuk membaca video frame dan mengirimkannya ke UI"""
    frame_ready = pyqtSignal(np.ndarray)

    def __init__(self, video_path):
        super().__init__()
        self.video_path = video_path
        self.running = False

    def run(self):
        """Main thread function"""
        try:
            # Buka video
            cap = cv2.VideoCapture(self.video_path)
            if not cap.isOpened():
                logging.error(f"Failed to open video: {self.video_path}")
                return

            logging.info(f"Video opened successfully: {self.video_path}")

            # Dapatkan FPS untuk mengatur delay
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0:
                fps = 30  # Default jika tidak bisa mendapatkan FPS

            delay = 1.0 / fps

            # Mulai loop
            self.running = True
            frame_count = 0

            while self.running:
                ret, frame = cap.read()
                if not ret:
                    # Reset video ke awal
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue

                # Kirim frame ke UI
                self.frame_ready.emit(frame)
                frame_count += 1

                # Log untuk debug
                if frame_count % 30 == 0:
                    logging.info(f"Processed {frame_count} frames")

                # Delay untuk mengatur FPS
                time.sleep(delay)

            # Cleanup
            cap.release()
            logging.info("Video thread stopped")

        except Exception as e:
            logging.error(f"Error in video thread: {str(e)}")
            logging.debug(traceback.format_exc())

    def stop(self):
        """Stop thread"""
        self.running = False
        self.wait()

class SimpleVideoPlayer(QMainWindow):
    """Simple video player untuk diagnosa"""

    def __init__(self):
        super().__init__()
        self.video_thread = None
        self.setup_ui()

    def setup_ui(self):
        """Setup UI"""
        self.setWindowTitle("Debug Video Player")
        self.setGeometry(100, 100, 800, 600)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Video display
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("background-color: black;")
        layout.addWidget(self.video_label)

        # Controls
        controls_layout = QVBoxLayout()

        # File selector
        file_layout = QHBoxLayout()
        self.file_combo = QComboBox()
        self.file_combo.setEditable(True)

        # Tambahkan path dari preset gasibu
        preset_path = os.path.join(root_dir, 'config', 'presets', 'gasibu.json')
        if os.path.exists(preset_path):
            try:
                import json
                with open(preset_path, 'r') as f:
                    data = json.load(f)
                    if 'source' in data and 'path' in data['source']:
                        self.file_combo.addItem(data['source']['path'])
            except Exception as e:
                logging.error(f"Error loading preset: {str(e)}")

        file_layout.addWidget(self.file_combo)

        # Browse button
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_file)
        file_layout.addWidget(browse_btn)

        controls_layout.addLayout(file_layout)

        # Start/Stop button
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self.toggle_playback)
        controls_layout.addWidget(self.start_btn)

        # Status label
        self.status_label = QLabel("Status: Ready")
        controls_layout.addWidget(self.status_label)

        layout.addLayout(controls_layout)

    def browse_file(self):
        """Browse for video file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Video", "", "Video Files (*.mp4 *.avi *.mkv *.mov);;All Files (*.*)"
        )
        if file_path:
            self.file_combo.setCurrentText(file_path)

    def toggle_playback(self):
        """Start or stop video playback"""
        if self.video_thread and self.video_thread.isRunning():
            # Stop playback
            self.video_thread.stop()
            self.start_btn.setText("Start")
            self.status_label.setText("Status: Stopped")
        else:
            # Start playback
            file_path = self.file_combo.currentText()
            if not file_path or not os.path.exists(file_path):
                self.status_label.setText("Status: Invalid file path")
                return

            # Create and start thread
            self.video_thread = SimpleVideoThread(file_path)
            self.video_thread.frame_ready.connect(self.update_frame)
            self.video_thread.start()

            # Update UI
            self.start_btn.setText("Stop")
            self.status_label.setText(f"Status: Playing {os.path.basename(file_path)}")

    def update_frame(self, frame):
        """Update frame in UI"""
        try:
            if frame is None:
                return

            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Get dimensions
            h, w, ch = rgb_frame.shape
            bytes_per_line = ch * w

            # Create QImage and QPixmap
            image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
            pixmap = QPixmap.fromImage(image)

            # Scale to fit label while maintaining aspect ratio
            pixmap = pixmap.scaled(
                self.video_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            # Display
            self.video_label.setPixmap(pixmap)

            # Update status every 30 frames
            if not hasattr(self, '_frame_count'):
                self._frame_count = 0
            self._frame_count += 1

            if self._frame_count % 30 == 0:
                self.status_label.setText(f"Status: Playing - Frame {self._frame_count} - Size: {w}x{h}")

        except Exception as e:
            logging.error(f"Error updating frame: {str(e)}")

    def closeEvent(self, event):
        """Handle window close"""
        if self.video_thread and self.video_thread.isRunning():
            self.video_thread.stop()
        event.accept()

def main():
    """Main function"""
    app = QApplication(sys.argv)
    window = SimpleVideoPlayer()
    window.show()
    return app.exec_()

if __name__ == "__main__":
    sys.exit(main())

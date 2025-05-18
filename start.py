""" sart.py
Vehicle Counter Application Starter
Provides error handling and proper startup sequence
"""

import os
import sys
import traceback
from pathlib import Path
import logging


def setup_environment():
    """Setup application environment"""
    # Add project root to path
    root_dir = Path(__file__).resolve().parent
    sys.path.append(str(root_dir))

    # Create necessary folders if they don't exist
    os.makedirs(root_dir / "config" / "presets", exist_ok=True)
    os.makedirs(root_dir / "data" / "db", exist_ok=True)
    os.makedirs(root_dir / "logs", exist_ok=True)

    # Set environment variables
    os.environ["VEHICLE_COUNTER_ROOT"] = str(root_dir)

    # Konfigurasi logging
    log_file = root_dir / "logs" / "app.log"
    logging.basicConfig(
        filename=str(log_file),
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logging.info("Application starting - environment setup complete")


def set_memory_limits():
    """Set memory limits to prevent stack overflow"""
    try:
        # Mencoba meningkatkan stack size di platform yang mendukung
        if hasattr(sys, 'setrecursionlimit'):
            # Meningkatkan batas rekursi (default 1000)
            sys.setrecursionlimit(3000)
            logging.info("Recursion limit increased to 3000")

        # Untuk Windows, kita bisa mengatur thread stack size dengan threading dan ctypes
        if os.name == 'nt':
            try:
                import ctypes
                import threading
                # Meningkatkan working set size
                ctypes.windll.kernel32.SetProcessWorkingSetSize(-1, -1)
                # Meningkatkan stack size untuk thread utama PyQt
                threading.stack_size(0x200000)  # 2MB stack size (default biasanya 1MB)
                logging.info("Windows process memory parameters adjusted")
            except Exception as e:
                logging.warning(f"Failed to set Windows memory limits: {e}")
    except Exception as e:
        logging.warning(f"Failed to set memory limits: {e}")


def start_application():
    """Start the application with proper error handling"""
    try:
        # Setup environment first
        setup_environment()

        # Set memory limits
        set_memory_limits()

        # Delay import to reduce initial memory pressure
        logging.info("Importing PyQt5...")
        import PyQt5
        from PyQt5.QtWidgets import QApplication
        logging.info("PyQt5 imported successfully")

        # Use higher log level for OpenVINO to reduce warnings
        logging.info("Setting OpenVINO log level...")
        os.environ["OPENVINO_LOG_LEVEL"] = "WARNING"

        # Create application with safe fallback
        app = QApplication(sys.argv)
        logging.info("QApplication created")

        # Import MainWindow with exception tracking
        try:
            logging.info("Loading MainWindow...")
            from ui.components.main_window import MainWindow
            logging.info("MainWindow imported successfully")

            # Create window with safer initialization
            window = MainWindow()
            logging.info("MainWindow instance created")

            window.show()
            logging.info("MainWindow displayed")

            # Start event loop with error tracking
            exit_code = app.exec_()
            logging.info(f"Application exiting with code: {exit_code}")
            sys.exit(exit_code)

        except Exception as e:
            error_msg = f"ERROR: Failed to initialize main window: {e}"
            logging.critical(error_msg, exc_info=True)
            print(error_msg)
            traceback.print_exc()
            sys.exit(1)

    except ImportError as e:
        error_msg = f"ERROR: Failed to import required modules: {e}"
        print(error_msg)
        logging.critical(error_msg, exc_info=True)
        print("Please ensure PyQt5 is installed correctly:")
        print("  pip uninstall -y PyQt5 PyQt5-Qt5 PyQt5-sip")
        print("  pip install PyQt5==5.15.9")
        sys.exit(1)

    except Exception as e:
        error_msg = f"ERROR: Application failed to start: {e}"
        print(error_msg)
        logging.critical(error_msg, exc_info=True)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    start_application()
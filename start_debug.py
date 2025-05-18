#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Vehicle Counter Application Starter - Debug Version
Provides enhanced error handling and detailed logging for troubleshooting
"""

import os
import sys
import traceback
import time
import platform
import logging
import threading
import gc
import faulthandler
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Any, List, Tuple

# Enable fault handler to get stack traces on segfaults
faulthandler.enable()

class MemoryMonitor:
    """Monitors and reports memory usage"""

    @staticmethod
    def get_memory_usage() -> Dict[str, Any]:
        """Get current memory usage"""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            mem_info = process.memory_info()
            return {
                'rss': mem_info.rss / 1024 / 1024,  # MB
                'vms': mem_info.vms / 1024 / 1024,  # MB
            }
        except ImportError:
            return {"error": "psutil not installed"}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def take_snapshot(label: str) -> Dict[str, Any]:
        """Take a memory snapshot and log it"""
        try:
            mem_usage = MemoryMonitor.get_memory_usage()

            # Handle the case when values might be strings
            rss_value = mem_usage.get('rss', 'N/A')
            vms_value = mem_usage.get('vms', 'N/A')

            if isinstance(rss_value, (int, float)):
                rss_str = f"{rss_value:.2f} MB"
            else:
                rss_str = str(rss_value)

            if isinstance(vms_value, (int, float)):
                vms_str = f"{vms_value:.2f} MB"
            else:
                vms_str = str(vms_value)

            logging.info(f"MEMORY SNAPSHOT ({label}): RSS: {rss_str}, VMS: {vms_str}")
            return mem_usage
        except Exception as e:
            logging.warning(f"Error taking memory snapshot: {e}")
            return {}


class ThreadMonitor:
    """Monitors and logs thread stacks"""

    @staticmethod
    def print_thread_stacks() -> str:
        """Print all thread stacks for debugging"""
        try:
            stack_log = ["\n=== THREAD STACKS ==="]

            for thread_id, frame in sys._current_frames().items():
                thread_name = None
                for t in threading.enumerate():
                    if t.ident == thread_id:
                        thread_name = t.name
                        break

                stack_log.append(f"\nThread {thread_id} ({thread_name}):")
                stack_trace = traceback.format_stack(frame)
                stack_log.extend(stack_trace)

            stack_log.append("=== END THREAD STACKS ===\n")
            full_log = "\n".join(stack_log)

            logging.debug(full_log)
            print(full_log)

            return full_log
        except Exception as e:
            logging.error(f"Error printing thread stacks: {e}")
            return "Error getting thread stacks"


class LoggingSetup:
    """Handles logging configuration"""

    @staticmethod
    def configure_logging() -> Optional[Path]:
        """Configure enhanced logging for debugging"""
        try:
            # Setup root logger
            root_dir = Path(__file__).resolve().parent
            logs_dir = root_dir / "logs"
            os.makedirs(logs_dir, exist_ok=True)

            # Log filename with timestamp
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            log_file = logs_dir / f"debug_{timestamp}.log"

            # Configure root logger
            logging.basicConfig(
                level=logging.DEBUG,
                format='%(asctime)s | %(levelname)8s | %(name)25s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S',
                handlers=[
                    logging.FileHandler(log_file),
                    logging.StreamHandler()  # Also output to console
                ]
            )

            # Set higher level for verbose external libraries
            for module in ['PyQt5', 'matplotlib', 'PIL', 'cv2', 'numpy']:
                logging.getLogger(module).setLevel(logging.WARNING)

            # Inform about logging
            logging.info(f"Detailed logging configured to: {log_file}")
            print(f"Detailed logging configured to: {log_file}")

            return log_file
        except Exception as e:
            print(f"Error configuring logging: {e}")
            traceback.print_exc()
            # Fallback to basic logging
            logging.basicConfig(level=logging.DEBUG)
            return None


class DebugEnvironment:
    """Sets up and manages debug environment"""

    @staticmethod
    def setup_environment() -> None:
        """Setup application environment with detailed logging"""
        try:
            start_time = time.time()
            logging.info(f"Starting environment setup (Python {sys.version})")

            # Add project root to path
            root_dir = Path(__file__).resolve().parent
            sys.path.append(str(root_dir))
            logging.info(f"Project root: {root_dir}")

            # Create necessary folders with logging
            folders = [
                root_dir / "config" / "presets",
                root_dir / "data" / "db",
                root_dir / "logs",
                ]

            for folder in folders:
                os.makedirs(folder, exist_ok=True)
                logging.info(f"Folder created/verified: {folder}")

            # Log system information
            logging.info(f"Platform: {platform.platform()}")
            logging.info(f"Python executable: {sys.executable}")
            logging.info(f"Python path: {sys.path}")

            # Set environment variables
            os.environ["VEHICLE_COUNTER_ROOT"] = str(root_dir)

            # Report memory usage
            MemoryMonitor.take_snapshot("environment_setup")

            # Setup complete
            duration = time.time() - start_time
            logging.info(f"Environment setup completed in {duration:.2f} seconds")
        except Exception as e:
            logging.error(f"Environment setup error: {e}", exc_info=True)
            raise

    @staticmethod
    def set_memory_limits() -> None:
        """Set memory limits to prevent stack overflow with detailed logging"""
        try:
            logging.info("Configuring memory limits...")

            # Increase recursion limit
            if hasattr(sys, 'setrecursionlimit'):
                old_limit = sys.getrecursionlimit()
                new_limit = 5000  # Higher than your current setting
                sys.setrecursionlimit(new_limit)
                logging.info(f"Recursion limit increased: {old_limit} -> {new_limit}")

            # On Windows, configure thread stack size and working set
            if os.name == 'nt':
                try:
                    import ctypes

                    # Try to increase thread stack size
                    try:
                        import _thread
                        _thread.stack_size(8 * 1024 * 1024)  # 8MB
                        logging.info("Thread stack size set to 8MB")
                    except (ImportError, AttributeError) as e:
                        logging.warning(f"Unable to set thread stack size: {e}")

                    # Try to disable crash dialogs
                    try:
                        SEM_NOGPFAULTERRORBOX = 0x0002
                        ctypes.windll.kernel32.SetErrorMode(SEM_NOGPFAULTERRORBOX)
                        logging.info("Windows error mode configured to suppress crash dialogs")
                    except Exception as e:
                        logging.warning(f"Unable to set Windows error mode: {e}")

                    # Try to increase working set size
                    try:
                        min_ws_size = 100 * 1024 * 1024  # 100MB minimum
                        max_ws_size = 1024 * 1024 * 1024  # 1GB maximum
                        result = ctypes.windll.kernel32.SetProcessWorkingSetSize(-1, min_ws_size, max_ws_size)
                        logging.info(f"SetProcessWorkingSetSize result: {result}")
                    except Exception as e:
                        logging.warning(f"Unable to set process working set size: {e}")

                    logging.info("Memory limits configuration completed")
                except Exception as e:
                    logging.warning(f"Failed to set Windows-specific memory limits: {str(e)}")
                    logging.warning(traceback.format_exc())
        except Exception as e:
            logging.warning(f"Error during memory limit configuration: {e}")
            logging.warning(traceback.format_exc())


class DebugToolsInitializer:
    """Initializes debug tools and helpers for the application"""

    @staticmethod
    def add_debug_tools(window) -> None:
        """Add debug tools to the main window"""
        try:
            from PyQt5.QtWidgets import QToolBar, QAction

            debug_toolbar = QToolBar("Debug")

            # Add debug actions
            gc_action = QAction("Force GC", window)
            gc_action.triggered.connect(lambda: logging.info(f"GC stats: {gc.collect()}"))
            debug_toolbar.addAction(gc_action)

            # Add thread stack action
            stack_action = QAction("Thread Stacks", window)
            stack_action.triggered.connect(ThreadMonitor.print_thread_stacks)
            debug_toolbar.addAction(stack_action)

            # Add memory info action
            mem_action = QAction("Memory Info", window)
            mem_action.triggered.connect(lambda: MemoryMonitor.take_snapshot("user_requested"))
            debug_toolbar.addAction(mem_action)

            window.addToolBar(debug_toolbar)
            logging.info("Debug toolbar added")
        except Exception as e:
            logging.warning(f"Could not add debug toolbar: {e}")

    @staticmethod
    def register_exception_hook() -> None:
        """Register global exception hook for handling unhandled exceptions"""
        def exception_hook(exc_type, exc_value, exc_traceback):
            logging.critical("Unhandled exception:", exc_info=(exc_type, exc_value, exc_traceback))
            traceback.print_exception(exc_type, exc_value, exc_traceback)
            sys.__excepthook__(exc_type, exc_value, exc_traceback)

        sys.excepthook = exception_hook
        logging.info("Global exception hook registered")

    @staticmethod
    def add_video_processor_to_main_window(window) -> None:
        """Add video processing functionality to main window"""
        try:
            from ui.gui_app import VehicleCounterGUI

            def video_processor_start(self):
                """Start video processing"""
                try:
                    logging.info("Starting video processing")

                    # Create processor if it doesn't exist
                    if not hasattr(self, '_video_processor'):
                        self._video_processor = VehicleCounterGUI()
                        logging.info("VehicleCounterGUI created")

                    # Get source configuration from control panel
                    source_type = self.control_panel.source_type_combo.currentData()
                    source_path = self.control_panel.source_path_edit.text()
                    options = {}

                    # Configure the video processor
                    self._video_processor.change_source(source_type, source_path, options)

                    # Start processing
                    self._video_processor.start_processing()

                    logging.info("Video processing started successfully")

                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    logging.error(f"Error in video_processor_start: {str(e)}")
                    from PyQt5.QtWidgets import QMessageBox
                    QMessageBox.critical(self, "Processing Error",
                                         f"Failed to start video processing: {str(e)}")

            # Add the method to the MainWindow instance
            import types
            window.video_processor_start = types.MethodType(video_processor_start, window)
            logging.info("Added video_processor_start method to MainWindow")

        except Exception as e:
            logging.error(f"Failed to add video processing functionality: {e}")


class ApplicationStarter:
    """Manages the application startup process"""

    def __init__(self):
        self.log_file = None

    def start_application(self) -> int:
        """Start the application with comprehensive error handling"""
        # Configure logging first
        self.log_file = LoggingSetup.configure_logging()

        try:
            # Log startup info
            logging.info("=" * 50)
            logging.info(f"VEHICLE COUNTER DEBUG STARTUP - PID: {os.getpid()}")
            logging.info("=" * 50)

            # Setup environment with memory tracking
            DebugEnvironment.setup_environment()

            # Configure memory and debugging
            DebugEnvironment.set_memory_limits()

            # Force garbage collection
            gc.collect()
            MemoryMonitor.take_snapshot("after_setup")

            # Import PyQt with memory tracking
            logging.info("Importing PyQt5...")
            import_start = time.time()
            try:
                from PyQt5.QtWidgets import QApplication
                import_time = time.time() - import_start
                logging.info(f"PyQt5 imported successfully in {import_time:.2f} seconds")
                MemoryMonitor.take_snapshot("after_pyqt_import")
            except ImportError as e:
                logging.critical(f"Failed to import PyQt5: {e}")
                print("Error: PyQt5 import failed. Please ensure it's installed correctly.")
                print("  pip install PyQt5==5.15.9")
                return 1

            # Set OpenVINO log level to reduce noise
            os.environ["OPENVINO_LOG_LEVEL"] = "WARNING"

            # Create application
            logging.info("Creating QApplication...")
            app = QApplication(sys.argv)
            app.setApplicationName("VehicleCounter-Debug")
            logging.info("QApplication created")

            # Register exception hook
            DebugToolsInitializer.register_exception_hook()

            # Import MainWindow with proper error handling
            logging.info("Loading MainWindow... (this may take a moment)")
            main_window_import_start = time.time()
            try:
                from ui.components.main_window import MainWindow
                main_window_import_time = time.time() - main_window_import_start
                logging.info(f"MainWindow imported successfully in {main_window_import_time:.2f} seconds")
                MemoryMonitor.take_snapshot("after_mainwindow_import")
            except Exception as e:
                logging.critical(f"Failed to import MainWindow: {e}", exc_info=True)
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.critical(None, "Import Error", f"Failed to import MainWindow: {str(e)}")
                ThreadMonitor.print_thread_stacks()
                return 1

            # Create window with safer initialization
            logging.info("Creating MainWindow instance...")
            try:
                # Create the window
                window = MainWindow()

                # Add video processing functionality
                DebugToolsInitializer.add_video_processor_to_main_window(window)

                logging.info("MainWindow instance created successfully")
                MemoryMonitor.take_snapshot("after_mainwindow_create")

            except RuntimeError as e:
                if "recursion" in str(e).lower() or "stack" in str(e).lower():
                    logging.critical(f"Stack overflow during MainWindow creation: {e}")
                    print("CRITICAL ERROR: Stack overflow detected during window creation.")
                    ThreadMonitor.print_thread_stacks()
                    from PyQt5.QtWidgets import QMessageBox
                    QMessageBox.critical(None, "Stack Overflow",
                                         "Stack overflow during window creation.\n\n"
                                         "This is likely due to recursive signal connections or initialization.")
                    return 1
                else:
                    raise
            except Exception as e:
                logging.critical(f"Failed to create MainWindow: {e}", exc_info=True)
                ThreadMonitor.print_thread_stacks()
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.critical(None, "Window Creation Error", f"Failed to create window: {str(e)}")
                return 1

            # Show window
            try:
                window.show()
                logging.info("MainWindow displayed")
                MemoryMonitor.take_snapshot("after_mainwindow_show")
            except Exception as e:
                logging.critical(f"Failed to show MainWindow: {e}", exc_info=True)
                ThreadMonitor.print_thread_stacks()
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.critical(None, "Display Error", f"Failed to show window: {str(e)}")
                return 1

            # Add debug toolbar
            DebugToolsInitializer.add_debug_tools(window)

            # Start event loop
            logging.info("Starting event loop...")
            exit_code = app.exec_()
            logging.info(f"Application exiting with code: {exit_code}")
            return exit_code

        except Exception as e:
            error_msg = f"ERROR: Application failed to start: {e}"
            logging.critical(error_msg, exc_info=True)
            print(error_msg)
            ThreadMonitor.print_thread_stacks()

            # Try to show error in GUI
            try:
                from PyQt5.QtWidgets import QApplication, QMessageBox
                if not QApplication.instance():
                    app = QApplication(sys.argv)
                QMessageBox.critical(None, "Startup Error", f"Application failed to start: {str(e)}")
            except:
                pass

            return 1


def main():
    """Main entry point with error handling"""
    try:
        starter = ApplicationStarter()
        return starter.start_application()
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        traceback.print_exc()

        try:
            logging.critical("Fatal exception in startup", exc_info=True)
        except:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
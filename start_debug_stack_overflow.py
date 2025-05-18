#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Vehicle Counter Stack Overflow Detector
Specifically targets the stack overflow issue with instrumentation
"""

import os
import sys
import traceback
import gc
import logging
from pathlib import Path
import threading
import time

def setup_logging():
    """Set up basic logging"""
    logs_dir = Path(__file__).resolve().parent / "logs"
    os.makedirs(logs_dir, exist_ok=True)

    log_file = logs_dir / f"stack_debug_{time.strftime('%Y%m%d-%H%M%S')}.log"

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s | %(levelname)8s | %(name)25s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

    print(f"Logging to: {log_file}")
    return log_file

class StackTracer:
    """Helper class to trace function calls and detect potential recursion"""

    def __init__(self):
        self.call_counts = {}
        self.max_counts = {}
        self.active_traces = set()

    def trace_calls(self, frame, event, arg):
        """Trace function to log calls and detect potential recursion"""
        if event != 'call':
            return self.trace_calls

        # Get function information
        code = frame.f_code
        func_name = code.co_name
        filename = code.co_filename
        lineno = frame.f_lineno

        # Only trace our own code
        if ('site-packages' in filename or
                'lib\\' in filename.lower() or
                'python' in filename.lower()):
            return self.trace_calls

        # Create a key for this function
        key = f"{filename}:{func_name}"

        # Update call count
        self.call_counts[key] = self.call_counts.get(key, 0) + 1

        # Check if this is a new maximum
        if self.call_counts[key] > self.max_counts.get(key, 0):
            self.max_counts[key] = self.call_counts[key]

        # Check for potential recursion (call count > 100)
        if self.call_counts[key] > 100 and key not in self.active_traces:
            self.active_traces.add(key)
            logging.warning(f"Potential recursion detected: {key} called {self.call_counts[key]} times")
            logging.warning(f"Stack at {key} ({lineno}):")
            stack = traceback.format_stack(frame)
            for line in stack:
                logging.warning(line.strip())

        # Check for extreme recursion (call count > 1000)
        if self.call_counts[key] > 1000:
            logging.critical(f"Excessive recursion detected: {key} called {self.call_counts[key]} times")
            logging.critical("Dumping all stacks:")
            self._dump_all_stacks()
            return None  # Stop tracing to prevent further issues

        return self.trace_calls

    def _dump_all_stacks(self):
        """Dump stack traces for all threads"""
        for thread_id, frame in sys._current_frames().items():
            thread_name = None
            for t in threading.enumerate():
                if t.ident == thread_id:
                    thread_name = t.name
                    break

            logging.critical(f"Thread {thread_id} ({thread_name}):")
            stack = traceback.format_stack(frame)
            for line in stack:
                logging.critical(line.strip())

    def reset(self):
        """Reset the call counts"""
        self.call_counts = {}
        self.active_traces = set()

    def report(self):
        """Report the maximum call counts"""
        logging.info("=== Function Call Counts ===")
        sorted_counts = sorted(self.max_counts.items(), key=lambda x: x[1], reverse=True)

        for key, count in sorted_counts[:20]:  # Show top 20
            if count > 10:  # Only show functions called more than 10 times
                logging.info(f"{key}: {count} calls")

def increase_stack_size():
    """Increase thread stack size"""
    try:
        if hasattr(threading, 'stack_size'):
            old_size = threading.stack_size()
            # Set a large stack size (8MB)
            threading.stack_size(8 * 1024 * 1024)
            logging.info(f"Thread stack size changed: {old_size} -> {threading.stack_size()}")
        else:
            logging.warning("threading.stack_size not available")
    except Exception as e:
        logging.warning(f"Failed to set thread stack size: {e}")

def patch_signal_connections():
    """Patch PyQt signal connections to detect potential cycles"""
    try:
        from PyQt5.QtCore import QObject

        # Store original connect method
        original_connect = QObject.connect

        # Dictionary to track connections
        connections = {}

        # Create a wrapper that logs connections
        def connect_wrapper(self, *args, **kwargs):
            result = original_connect(self, *args, **kwargs)

            # Track this connection
            sender = self
            if len(args) >= 2:
                signal = args[0]
                receiver = args[1]

                # Create keys for sender and receiver
                sender_key = f"{sender.__class__.__name__}:{id(sender)}"

                if isinstance(receiver, QObject):
                    receiver_key = f"{receiver.__class__.__name__}:{id(receiver)}"
                else:
                    # Function receiver
                    receiver_key = f"Function:{receiver.__name__}"

                # Create connection key
                conn_key = f"{sender_key} -> {receiver_key}"
                connections[conn_key] = connections.get(conn_key, 0) + 1

                # Check for potential issues (multiple connections)
                if connections[conn_key] > 2:
                    logging.warning(f"Multiple connections detected: {conn_key} ({connections[conn_key]} times)")

                # Log connection
                logging.debug(f"Signal connection: {conn_key}")

            return result

        # Replace the connect method
        QObject.connect = connect_wrapper
        logging.info("PyQt signal connection patched for debugging")

    except Exception as e:
        logging.warning(f"Failed to patch signal connections: {e}")

def run_with_stack_tracing():
    """Run the application with stack tracing"""
    # Setup logging
    setup_logging()

    logging.info("=== VEHICLE COUNTER STACK OVERFLOW DETECTOR ===")

    try:
        # Increase stack size
        increase_stack_size()

        # Set recursion limit
        sys.setrecursionlimit(3000)
        logging.info(f"Recursion limit: {sys.getrecursionlimit()}")

        # Create a tracer
        tracer = StackTracer()

        # Setup path
        root_dir = Path(__file__).resolve().parent
        sys.path.append(str(root_dir))

        # Import PyQt first
        logging.info("Importing PyQt5...")
        from PyQt5.QtWidgets import QApplication

        # Patch signal connections
        patch_signal_connections()

        # Create application
        app = QApplication(sys.argv)

        # Enable tracing
        sys.settrace(tracer.trace_calls)

        try:
            # Import MainWindow
            logging.info("Loading MainWindow...")
            from ui.components.main_window import MainWindow

            # Create window
            logging.info("Creating MainWindow...")
            window = MainWindow()

            # Reset tracer
            tracer.reset()

            # Show window
            logging.info("Showing MainWindow...")
            window.show()

            # Start event loop
            logging.info("Starting event loop...")
            exit_code = app.exec_()

            # Report call counts
            tracer.report()

            return exit_code

        except Exception as e:
            logging.critical(f"Error: {e}", exc_info=True)

            # Report any detected recursion
            tracer.report()

            # Print current thread stacks
            logging.critical("Thread stacks at error:")
            for thread_id, frame in sys._current_frames().items():
                thread_name = "Unknown"
                for t in threading.enumerate():
                    if t.ident == thread_id:
                        thread_name = t.name
                logging.critical(f"Thread {thread_id} ({thread_name}):")
                stack = traceback.format_stack(frame)
                for line in stack:
                    logging.critical(line.strip())

            # Show error message
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(None, "Error", f"Application error: {str(e)}")
            return 1

    except Exception as e:
        logging.critical(f"Fatal error: {e}", exc_info=True)
        return 1
    finally:
        # Disable tracing
        sys.settrace(None)

if __name__ == "__main__":
    try:
        sys.exit(run_with_stack_tracing())
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
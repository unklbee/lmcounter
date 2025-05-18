#main.py
# -*- coding: utf-8 -*-

"""
Vehicle Counter Application
Entry point untuk aplikasi Vehicle Counter
"""

import os
import sys
import argparse
from pathlib import Path

from PyQt5.QtWidgets import QApplication, QMessageBox


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Vehicle Counter Application")
    parser.add_argument("--cli", action="store_true", help="Run in CLI mode")
    parser.add_argument("--gui", action="store_true", help="Run in GUI mode")
    parser.add_argument("--preset", type=str, help="Path to preset configuration file")
    parser.add_argument("--source", type=str, help="Video source (file path, RTSP URL, or webcam index)")
    parser.add_argument("--device", type=str, choices=["CPU", "GPU"], default="GPU",
                        help="Processing device")
    parser.add_argument("--output", type=str, help="Output video file path")
    parser.add_argument("--api-push", action="store_true", help="Push counting data to API")
    parser.add_argument("--api-url", type=str, default="http://localhost:8000/api/counts",
                        help="API endpoint URL")
    parser.add_argument("--db-save", action="store_true", help="Save counting data to local database")

    return parser.parse_args()

def setup_environment():
    """Setup application environment."""
    # Add project root to path
    root_dir = Path(__file__).resolve().parent
    sys.path.append(str(root_dir))

    # Create necessary folders if they don't exist
    os.makedirs(root_dir / "config" / "presets", exist_ok=True)
    os.makedirs(root_dir / "data" / "db", exist_ok=True)

    # Set environment variables
    os.environ["VEHICLE_COUNTER_ROOT"] = str(root_dir)

def main():
    """Main entry point."""
    try:
        # Setup application environment
        setup_environment()

        # Parse command line arguments
        args = parse_arguments()

        # Determine application mode
        cli_mode = args.cli
        gui_mode = args.gui or not cli_mode  # Default to GUI if not specified

        if gui_mode:
            # Import GUI components here to avoid unnecessary imports in CLI mode
            from ui.gui_app import VehicleCounterGUI

            # Create Qt application with proper exit handling
            app = QApplication(sys.argv)

            try:
                # Create main window
                main_window = VehicleCounterGUI(preset_path=args.preset)
                main_window.show()

                # Start event loop
                sys.exit(app.exec_())
            except Exception as e:
                import traceback
                traceback.print_exc()
                QMessageBox.critical(None, "Critical Error", f"Application error: {str(e)}")
                sys.exit(1)
        else:
            # Import CLI components
            from cli.cli_app import VehicleCounterCLI

            try:
                app = VehicleCounterCLI(
                    preset_path=args.preset,
                    source=args.source,
                    device=args.device,
                    output=args.output,
                    api_push=args.api_push,
                    api_url=args.api_url,
                    db_save=args.db_save
                )
                app.run()
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"Critical error: {str(e)}")
                sys.exit(1)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
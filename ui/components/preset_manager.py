# ui/components/preset_manager.py
# -*- coding: utf-8 -*-

"""
Preset Manager widget for Vehicle Counter application
Provides UI for managing configuration presets
"""

import os
from pathlib import Path
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QGroupBox, QFormLayout, QLineEdit, QTextEdit,
    QDialog, QDialogButtonBox, QMessageBox, QMenu, QAction, QFileDialog,
    QFrame, QSplitter
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QIcon

from utils.logger import get_logger

# Setup logger
logger = get_logger(__name__)

class PresetDetailsDialog(QDialog):
    """Dialog for editing preset details"""

    def __init__(self, preset_data=None, parent=None):
        """
        Initialize dialog

        Args:
            preset_data (dict): Preset data or None for new preset
            parent: Parent widget
        """
        super().__init__(parent)

        self.preset_data = preset_data or {}

        self.setWindowTitle("Preset Details")
        self.setMinimumWidth(400)

        # Layout
        layout = QVBoxLayout(self)

        form_layout = QFormLayout()

        # Name field
        self.name_edit = QLineEdit(self.preset_data.get("name", "New Preset"))
        form_layout.addRow("Name:", self.name_edit)

        # Description field
        self.desc_edit = QTextEdit()
        self.desc_edit.setText(self.preset_data.get("description", ""))
        self.desc_edit.setMaximumHeight(100)
        form_layout.addRow("Description:", self.desc_edit)

        layout.addLayout(form_layout)

        # Button box
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_data(self):
        """
        Get updated preset data

        Returns:
            dict: Updated preset data
        """
        self.preset_data["name"] = self.name_edit.text().strip() or "Unnamed Preset"
        self.preset_data["description"] = self.desc_edit.toPlainText().strip()
        self.preset_data["modified"] = datetime.now().isoformat()

        return self.preset_data


class PresetManagerWidget(QWidget):
    """Preset manager widget for managing configuration presets"""

    # Signals
    preset_selected = pyqtSignal(str)  # preset_id
    preset_loaded = pyqtSignal(str)    # preset_path
    preset_saved = pyqtSignal(str)     # preset_path
    preset_deleted = pyqtSignal(str)   # preset_id

    def __init__(self, preset_manager, parent=None):
        """
        Initialize preset manager widget

        Args:
            preset_manager: Preset manager instance
            parent: Parent widget
        """
        super().__init__(parent)

        self.preset_manager = preset_manager
        self.current_preset_id = None

        # Initialize UI
        self.init_ui()

        # Populate preset list
        self.refresh()

    def init_ui(self):
        """Initialize user interface"""
        # Main layout
        self.main_layout = QVBoxLayout(self)

        # Create splitter for list and details
        splitter = QSplitter(Qt.Vertical)
        self.main_layout.addWidget(splitter)

        # Preset list section
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)

        # Preset list
        self.preset_list = QListWidget()
        self.preset_list.setMinimumHeight(200)
        self.preset_list.currentItemChanged.connect(self.on_preset_selected)
        self.preset_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.preset_list.customContextMenuRequested.connect(self.show_context_menu)
        list_layout.addWidget(self.preset_list)

        # Buttons below list
        list_buttons = QHBoxLayout()

        self.new_btn = QPushButton("New")
        self.new_btn.clicked.connect(self.create_new_preset)
        list_buttons.addWidget(self.new_btn)

        self.import_btn = QPushButton("Import")
        self.import_btn.clicked.connect(self.import_preset)
        list_buttons.addWidget(self.import_btn)

        self.export_btn = QPushButton("Export")
        self.export_btn.clicked.connect(self.export_preset)
        self.export_btn.setEnabled(False)  # Disabled until preset is selected
        list_buttons.addWidget(self.export_btn)

        list_layout.addLayout(list_buttons)

        # Add list widget to splitter
        splitter.addWidget(list_widget)

        # Preset details section
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        details_layout.setContentsMargins(0, 0, 0, 0)

        # Details group
        self.details_group = QGroupBox("Preset Details")
        details_form = QFormLayout(self.details_group)

        self.name_label = QLabel("No preset selected")
        details_form.addRow("Name:", self.name_label)

        self.created_label = QLabel("")
        details_form.addRow("Created:", self.created_label)

        self.modified_label = QLabel("")
        details_form.addRow("Modified:", self.modified_label)

        self.description_label = QLabel("")
        self.description_label.setWordWrap(True)
        details_form.addRow("Description:", self.description_label)

        details_layout.addWidget(self.details_group)

        # Action buttons
        action_buttons = QHBoxLayout()

        self.load_btn = QPushButton("Load")
        self.load_btn.clicked.connect(self.load_selected_preset)
        self.load_btn.setEnabled(False)
        action_buttons.addWidget(self.load_btn)

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.clicked.connect(self.edit_preset)
        self.edit_btn.setEnabled(False)
        action_buttons.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self.delete_preset)
        self.delete_btn.setEnabled(False)
        action_buttons.addWidget(self.delete_btn)

        self.default_btn = QPushButton("Set as Default")
        self.default_btn.clicked.connect(self.set_as_default)
        self.default_btn.setEnabled(False)
        action_buttons.addWidget(self.default_btn)

        details_layout.addLayout(action_buttons)

        # Add details widget to splitter
        splitter.addWidget(details_widget)

        # Set initial splitter sizes (70% list, 30% details)
        splitter.setSizes([700, 300])

    def refresh(self):
        """Refresh preset list"""
        # Save current selection
        current_id = self.current_preset_id

        # Clear list
        self.preset_list.clear()

        # Reload presets
        presets = self.preset_manager.load_available_presets()

        # Add presets to list
        for preset_id, preset_info in presets.items():
            item = QListWidgetItem(preset_info["name"])
            item.setData(Qt.UserRole, preset_id)

            # Mark default preset
            if os.path.samefile(preset_info["path"], self.preset_manager.default_preset_path) if os.path.exists(self.preset_manager.default_preset_path) else False:
                item.setText(f"{preset_info['name']} (Default)")
                font = item.font()
                font.setBold(True)
                item.setFont(font)

            self.preset_list.addItem(item)

        # Restore selection if possible
        if current_id:
            for i in range(self.preset_list.count()):
                item = self.preset_list.item(i)
                if item.data(Qt.UserRole) == current_id:
                    self.preset_list.setCurrentItem(item)
                    break

        # Update UI state
        self.update_ui_state()

    def on_preset_selected(self, current, previous):
        """
        Handle preset selection changed

        Args:
            current: Current list item
            previous: Previous list item
        """
        if current:
            preset_id = current.data(Qt.UserRole)
            self.current_preset_id = preset_id

            # Get preset info
            preset_info = self.preset_manager.presets.get(preset_id, {})

            # Update details
            self.name_label.setText(preset_info.get("name", "Unnamed"))

            created = preset_info.get("created", "")
            if created:
                try:
                    # Format ISO datetime
                    created_dt = datetime.fromisoformat(created)
                    created_str = created_dt.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    created_str = created
            else:
                created_str = "Unknown"

            self.created_label.setText(created_str)

            # Similar formatting for modified date
            modified = preset_info.get("modified", created)
            if modified:
                try:
                    modified_dt = datetime.fromisoformat(modified)
                    modified_str = modified_dt.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    modified_str = modified
            else:
                modified_str = created_str

            self.modified_label.setText(modified_str)

            # Set description
            self.description_label.setText(preset_info.get("description", ""))

            # Enable buttons
            self.load_btn.setEnabled(True)
            self.edit_btn.setEnabled(True)
            self.delete_btn.setEnabled(True)
            self.default_btn.setEnabled(True)
            self.export_btn.setEnabled(True)

            # Emit signal
            self.preset_selected.emit(preset_id)
        else:
            # Clear details
            self.current_preset_id = None
            self.name_label.setText("No preset selected")
            self.created_label.setText("")
            self.modified_label.setText("")
            self.description_label.setText("")

            # Disable buttons
            self.load_btn.setEnabled(False)
            self.edit_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            self.default_btn.setEnabled(False)
            self.export_btn.setEnabled(False)

    def update_ui_state(self):
        """Update UI state based on current selection"""
        has_selection = self.current_preset_id is not None

        self.load_btn.setEnabled(has_selection)
        self.edit_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)
        self.default_btn.setEnabled(has_selection)
        self.export_btn.setEnabled(has_selection)

    def create_new_preset(self):
        """Create new preset"""
        # Show dialog to get preset name and description
        dialog = PresetDetailsDialog(parent=self)

        if dialog.exec_() == QDialog.Accepted:
            # Get preset data
            preset_data = dialog.get_data()

            # Create basic preset structure
            preset = self.preset_manager.create_empty_preset()
            preset["name"] = preset_data["name"]
            preset["description"] = preset_data["description"]

            # Save preset
            path = self.preset_manager.presets_dir / f"{preset['name'].lower().replace(' ', '_')}.json"
            if self.preset_manager.save_preset(preset, path):
                # Refresh list
                self.refresh()

                # Select new preset
                for i in range(self.preset_list.count()):
                    item = self.preset_list.item(i)
                    if item.data(Qt.UserRole) == preset["id"]:
                        self.preset_list.setCurrentItem(item)
                        break

                # Emit signal
                self.preset_saved.emit(str(path))

                QMessageBox.information(self, "Success", "New preset created successfully")
            else:
                QMessageBox.warning(self, "Error", "Failed to create preset")

    def edit_preset(self):
        """Edit selected preset"""
        if not self.current_preset_id:
            return

        # Get preset info
        preset_info = self.preset_manager.presets.get(self.current_preset_id, {})
        if not preset_info:
            return

        # Get full preset data
        preset_path = preset_info["path"]
        preset = self.preset_manager.load_preset(path=preset_path)

        if not preset:
            QMessageBox.warning(self, "Error", "Failed to load preset for editing")
            return

        # Show dialog
        dialog = PresetDetailsDialog(preset, self)

        if dialog.exec_() == QDialog.Accepted:
            # Get updated data
            updated_preset = dialog.get_data()

            # Save preset
            if self.preset_manager.save_preset(updated_preset, preset_path):
                # Refresh list
                self.refresh()

                # Emit signal
                self.preset_saved.emit(preset_path)

                QMessageBox.information(self, "Success", "Preset updated successfully")
            else:
                QMessageBox.warning(self, "Error", "Failed to update preset")

    def delete_preset(self):
        """Delete selected preset"""
        if not self.current_preset_id:
            return

        # Get preset info
        preset_info = self.preset_manager.presets.get(self.current_preset_id, {})
        if not preset_info:
            return

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete the preset '{preset_info['name']}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # Delete preset
        if self.preset_manager.delete_preset(self.current_preset_id):
            # Remember ID for signal
            deleted_id = self.current_preset_id

            # Clear selection
            self.current_preset_id = None

            # Refresh list
            self.refresh()

            # Emit signal
            self.preset_deleted.emit(deleted_id)

            QMessageBox.information(self, "Success", "Preset deleted successfully")
        else:
            QMessageBox.warning(self, "Error", "Failed to delete preset")

    def load_selected_preset(self):
        """Load selected preset"""
        if not self.current_preset_id:
            return

        # Get preset info
        preset_info = self.preset_manager.presets.get(self.current_preset_id, {})
        if not preset_info:
            return

        # Load preset
        preset_path = preset_info["path"]
        preset = self.preset_manager.load_preset(path=preset_path)

        if preset:
            # Emit signal
            self.preset_loaded.emit(preset_path)

            QMessageBox.information(self, "Success", f"Preset '{preset_info['name']}' loaded successfully")
        else:
            QMessageBox.warning(self, "Error", "Failed to load preset")

    def set_as_default(self):
        """Set selected preset as default"""
        if not self.current_preset_id:
            return

        # Get preset info
        preset_info = self.preset_manager.presets.get(self.current_preset_id, {})
        if not preset_info:
            return

        # Load preset
        preset_path = preset_info["path"]
        preset = self.preset_manager.load_preset(path=preset_path)

        if not preset:
            QMessageBox.warning(self, "Error", "Failed to load preset")
            return

        # Save as default
        if self.preset_manager.save_preset(preset, self.preset_manager.default_preset_path, False):
            # Refresh list to update default marking
            self.refresh()

            QMessageBox.information(self, "Success", f"'{preset_info['name']}' set as default preset")
        else:
            QMessageBox.warning(self, "Error", "Failed to set as default preset")

    def import_preset(self):
        """Import preset from file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Preset", str(Path.home()),
            "JSON Files (*.json);;All Files (*.*)"
        )

        if not file_path:
            return

        try:
            # Load preset
            preset = self.preset_manager.load_preset(path=file_path)

            if not preset:
                QMessageBox.warning(self, "Error", "Invalid preset file format")
                return

            # Generate new name for imported preset
            import_name = f"Imported_{Path(file_path).stem}"
            preset["name"] = import_name

            # Generate path for imported preset
            import_path = self.preset_manager.presets_dir / f"{import_name.lower().replace(' ', '_')}.json"

            # Save imported preset
            if self.preset_manager.save_preset(preset, import_path):
                # Refresh list
                self.refresh()

                # Select imported preset
                for i in range(self.preset_list.count()):
                    item = self.preset_list.item(i)
                    if item.data(Qt.UserRole) == preset["id"]:
                        self.preset_list.setCurrentItem(item)
                        break

                # Emit signal
                self.preset_saved.emit(str(import_path))

                QMessageBox.information(self, "Success", "Preset imported successfully")
            else:
                QMessageBox.warning(self, "Error", "Failed to import preset")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error importing preset: {str(e)}")

    def export_preset(self):
        """Export selected preset to file"""
        if not self.current_preset_id:
            return

        # Get preset info
        preset_info = self.preset_manager.presets.get(self.current_preset_id, {})
        if not preset_info:
            return

        # Get save path
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Preset", str(Path.home() / f"{preset_info['name']}.json"),
            "JSON Files (*.json);;All Files (*.*)"
        )

        if not file_path:
            return

        try:
            # Load preset
            preset_path = preset_info["path"]
            preset = self.preset_manager.load_preset(path=preset_path)

            if not preset:
                QMessageBox.warning(self, "Error", "Failed to load preset")
                return

            # Save to export path
            if self.preset_manager.save_preset(preset, file_path, False):
                QMessageBox.information(self, "Success", "Preset exported successfully")
            else:
                QMessageBox.warning(self, "Error", "Failed to export preset")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error exporting preset: {str(e)}")

    def show_context_menu(self, position):
        """
        Show context menu for preset list

        Args:
            position: Position where right-click occurred
        """
        # Get item at position
        item = self.preset_list.itemAt(position)
        if not item:
            return

        # Create context menu
        menu = QMenu(self)

        # Add actions
        load_action = QAction("Load", self)
        load_action.triggered.connect(self.load_selected_preset)
        menu.addAction(load_action)

        edit_action = QAction("Edit", self)
        edit_action.triggered.connect(self.edit_preset)
        menu.addAction(edit_action)

        export_action = QAction("Export", self)
        export_action.triggered.connect(self.export_preset)
        menu.addAction(export_action)

        menu.addSeparator()

        default_action = QAction("Set as Default", self)
        default_action.triggered.connect(self.set_as_default)
        menu.addAction(default_action)

        menu.addSeparator()

        delete_action = QAction("Delete", self)
        delete_action.triggered.connect(self.delete_preset)
        menu.addAction(delete_action)

        # Show menu
        menu.exec_(self.preset_list.mapToGlobal(position))
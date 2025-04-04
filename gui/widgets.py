#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# gui/widgets.py - Custom widgets for Turdus Merula GUI

from PyQt6.QtWidgets import QPushButton, QWidget, QHBoxLayout, QLabel, QLineEdit, QToolButton, QFileDialog

from config import COLOR_GREY, TEXT_LIGHT, BG_MEDIUM


class OperationButton(QPushButton):
    """Custom button class for operations with status indicator"""

    def __init__(self, text, description=None, parent=None):
        super().__init__(text, parent)
        self.setMinimumHeight(30)
        self.description = description
        self.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                padding: 6px 10px;
                border-radius: 3px;
                background-color: #3D3D3D;
                color: #E0E0E0;
                border: 1px solid #505050;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #4D4D4D;
            }
            QPushButton:pressed {
                background-color: #606060;
            }
            QPushButton:disabled {
                background-color: #353535;
                color: #707070;
                border: 1px solid #404040;
            }
        """)

        # Status variables
        self.status = "Ready"
        self.status_color = COLOR_GREY

        # Add retry button if needed
        self.retry_button = None


class FilePathWidget(QWidget):
    """Widget for displaying and selecting file paths"""

    def __init__(self, label_text, file_type, parent=None):
        super().__init__(parent)
        self.file_type = file_type

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # Label
        self.label = QLabel(label_text)
        self.label.setStyleSheet(f"color: {TEXT_LIGHT};")
        layout.addWidget(self.label)

        # Path field
        self.path_field = QLineEdit()
        self.path_field.setReadOnly(True)
        self.path_field.setStyleSheet(f"""
            QLineEdit {{
                background-color: {BG_MEDIUM};
                color: {TEXT_LIGHT};
                border: 1px solid #505050;
                border-radius: 3px;
                padding: 4px;
            }}
        """)
        layout.addWidget(self.path_field, 1)  # Stretch

        # Browse button
        self.browse_button = QToolButton()
        self.browse_button.setText("...")
        self.browse_button.setStyleSheet(f"""
            QToolButton {{
                background-color: {BG_MEDIUM};
                color: {TEXT_LIGHT};
                border: 1px solid #505050;
                border-radius: 3px;
                padding: 4px;
                min-width: 20px;
            }}
            QToolButton:hover {{
                background-color: #4D4D4D;
            }}
        """)
        self.browse_button.clicked.connect(self.browse_file)
        layout.addWidget(self.browse_button)

    def browse_file(self):
        """Open file dialog to select a file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, f"Select {self.file_type} File", "", f"{self.file_type} Files (*.bin);;All Files (*.*)"
        )
        if file_path:
            self.set_path(file_path)

    def set_path(self, path):
        """Set the file path"""
        self.path_field.setText(path)

    def get_path(self):
        """Get the current file path"""
        return self.path_field.text()

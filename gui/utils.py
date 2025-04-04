#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# gui/utils.py - Utility functions for GUI

import re
from PyQt6.QtGui import QColor, QTextCursor

from config import TEXT_LIGHT, COLOR_GREEN, COLOR_BLUE, COLOR_RED, COLOR_YELLOW, COLOR_GREY, HIGHLIGHT_COLOR


def log_message(text_edit, message, color_tag=None):
    """Add message to log area

    Args:
        text_edit (QTextEdit): The text edit widget to log to
        message (str): Message to log
        color_tag (str, optional): Color tag for message coloring
    """
    # Define color mapping
    colors = {
        "RED": QColor(COLOR_RED),
        "GREEN": QColor(COLOR_GREEN),
        "BLUE": QColor(COLOR_BLUE),
        "YELLOW": QColor(COLOR_YELLOW),
        "GREY": QColor(COLOR_GREY)
    }

    # Clean ANSI color codes from message
    # This will remove codes like [36m, [39m, [32m, etc.
    message = re.sub(r'\x1B\[[0-9;]*[mK]', '', message)

    # Ensure message ends with newline
    if not message.endswith('\n'):
        message += '\n'

    # Set color and add text
    cursor = text_edit.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)

    text_format = cursor.charFormat()
    if color_tag and color_tag in colors:
        text_format.setForeground(colors[color_tag])
    else:
        text_format.setForeground(QColor(TEXT_LIGHT))

    cursor.setCharFormat(text_format)
    cursor.insertText(message)

    # Scroll to bottom
    text_edit.setTextCursor(cursor)
    text_edit.ensureCursorVisible()


def update_button_status(button, status, color):
    """Update button status and appearance

    Args:
        button (OperationButton): Button to update
        status (str): New status
        color (str): Color for the status
    """
    button.status = status
    button.status_color = color

    # Add status indicator to button text
    original_text = button.text().split(" [")[0]  # Remove any existing status
    button.setText(f"{original_text} [{status}]")

    # Update button appearance based on status
    if status == "Completed":
        button.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                padding: 6px 10px;
                border-radius: 3px;
                background-color: #006600;
                color: white;
                border: 2px solid #008800;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #007700;
            }
        """)

        # Hide retry button if visible
        if button.retry_button:
            button.retry_button.setVisible(False)

    elif status == "Failed":
        button.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                padding: 6px 10px;
                border-radius: 3px;
                background-color: #990000;
                color: white;
                border: 2px solid #BB0000;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #BB0000;
            }
        """)

        # Show retry button
        if button.retry_button:
            button.retry_button.setVisible(True)

    elif status == "Restart Here":
        button.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                padding: 6px 10px;
                border-radius: 3px;
                background-color: #FFA500;
                color: black;
                border: 2px solid #FFB700;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #FFB700;
            }
        """)

        # Hide retry button if visible
        if button.retry_button:
            button.retry_button.setVisible(False)

    elif status == "In Progress":
        # 使用更亮的边框，不使用box-shadow
        button.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                padding: 6px 10px;
                border-radius: 3px;
                background-color: #0066CC;
                color: white;
                border: 3px solid #4499FF;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #0077DD;
            }
        """)

        # Hide retry button if visible
        if button.retry_button:
            button.retry_button.setVisible(False)

    elif status == "Partial":
        button.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                padding: 6px 10px;
                border-radius: 3px;
                background-color: #CCAA00;
                color: black;
                border: 2px solid #DDBB00;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #DDBB00;
            }
        """)

        # Hide retry button if visible
        if button.retry_button:
            button.retry_button.setVisible(False)

    else:  # Ready or other states
        button.setStyleSheet("""
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

        # Hide retry button if visible
        if button.retry_button:
            button.retry_button.setVisible(False)


def highlight_next_step_button(button):
    """Highlight a button as the next step

    Args:
        button (OperationButton): Button to highlight
    """
    # 使用更粗的边框和不同的颜色突出显示，而不是box-shadow
    button.setStyleSheet(f"""
        QPushButton {{
            font-weight: bold;
            padding: 6px 10px;
            border-radius: 3px;
            background-color: {HIGHLIGHT_COLOR};
            color: white;
            border: 3px solid #FF8C00;
            text-align: left;
        }}
        QPushButton:hover {{
            background-color: #FF8533;
            border: 3px solid #FFA500;
        }}
        QPushButton:pressed {{
            background-color: #E65C00;
        }}
    """)

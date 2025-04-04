#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# main.py - Entry point for Turdus Merula GUI application

import sys
import traceback

from PyQt6.QtWidgets import QApplication, QMessageBox
from gui.main_window import TurdusGUI


def main():
    """Main function to start the application"""
    app = QApplication(sys.argv)

    # Set application style
    app.setStyle("Fusion")

    # Create and show main window
    window = TurdusGUI()
    window.show()

    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        QMessageBox.critical(None, "Error", f"Application error: {str(e)}")
        print(f"Error: {str(e)}")
        traceback.print_exc()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import glob
import os
import signal
import subprocess
import sys

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton, QLabel, QProgressBar, QTextEdit,
    QFrame, QFileDialog, QMessageBox, QGroupBox, QGridLayout,
    QLineEdit, QSplitter, QToolButton
)

# Color constants - Using deeper colors for better visibility
COLOR_GREEN = "#00B300"  # Darker green
COLOR_YELLOW = "#FFA500"  # Orange-yellow
COLOR_RED = "#DC143C"  # Crimson red
COLOR_BLUE = "#0066CC"  # Darker blue
COLOR_GREY = "#707070"  # Darker grey
BG_DARK = "#2E2E2E"  # Dark background
BG_MEDIUM = "#3D3D3D"  # Medium background
TEXT_LIGHT = "#E0E0E0"  # Light text
HIGHLIGHT_COLOR = "#FF6600"  # Highlight color for next steps


class CommandThread(QThread):
    """Thread for executing commands"""
    commandComplete = pyqtSignal(bool, str)
    logOutput = pyqtSignal(str, str)
    timedOut = pyqtSignal()

    def __init__(self, command, timeout=None, check_output=False, retry_with_ED=False, max_retries=2, dfu_timeout=5):
        super().__init__()
        self.command = command
        self.timeout = timeout
        self.check_output = check_output
        self.retry_with_ED = retry_with_ED
        self.max_retries = max_retries
        self.process = None
        self.terminated = False
        self.dfu_timeout = dfu_timeout
        self.is_dfu_command = "turdusra1n -ED" in command

    def run(self):
        retry_count = 0
        output_lines = []
        success = False
        output = None

        while retry_count <= self.max_retries and not success and not self.terminated:
            if retry_count > 0:
                self.logOutput.emit(f"Retry #{retry_count}...", "YELLOW")

            self.logOutput.emit(f"Executing command: {self.command}", "GREEN")

            self.process = subprocess.Popen(
                self.command,
                shell=isinstance(self.command, str),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            output_lines = []

            # Special handling for DFU commands with auto-retry
            if self.is_dfu_command:
                dfu_timer = QTimer()
                dfu_timer.setSingleShot(True)
                dfu_timer.timeout.connect(self.handle_dfu_timeout)
                dfu_timer.start(self.dfu_timeout * 1000)  # Convert seconds to milliseconds

            # Read output
            for line in iter(self.process.stdout.readline, ""):
                if self.terminated:
                    break
                self.logOutput.emit(line, None)  # Regular log, no color
                if self.check_output:
                    output_lines.append(line)

                # If we're getting output and this is a DFU command, stop the timer
                if self.is_dfu_command and dfu_timer.isActive():
                    dfu_timer.stop()

            try:
                if not self.terminated:
                    self.process.wait(timeout=self.timeout)
                    if self.process.returncode != 0:
                        self.logOutput.emit(f"Command failed with return code: {self.process.returncode}", "RED")
                    else:
                        success = True
            except subprocess.TimeoutExpired:
                self.logOutput.emit(f"Command timed out ({self.timeout} seconds)", "RED")
                self.process.kill()
                self.process.wait()

            if success:
                if self.check_output:
                    output = "".join(output_lines)
                break

            # If retry is needed and the command failed
            if self.retry_with_ED and retry_count < self.max_retries and not self.terminated:
                self.logOutput.emit(f"Command failed, attempting to restart with ./bin/turdusra1n -ED...", "YELLOW")
                # Run turdusra1n -ED
                ed_success = self._run_turdusra1n_ED()
                if not ed_success:
                    self.logOutput.emit("turdusra1n -ED failed, cannot continue retrying", "RED")
                    break

            retry_count += 1

        self.commandComplete.emit(success, output if self.check_output else "")

    def handle_dfu_timeout(self):
        """Handle DFU command timeout - emits signal to trigger auto-retry"""
        if not self.terminated and self.process:
            self.logOutput.emit("DFU command not responding, will auto-retry...", "YELLOW")
            self.timedOut.emit()
            self.terminate()

    def _run_turdusra1n_ED(self):
        """Run turdusra1n -ED command synchronously"""
        max_attempts = 3
        attempt = 1

        while attempt <= max_attempts and not self.terminated:
            self.logOutput.emit(f"Attempt {attempt}/{max_attempts}: Running ./bin/turdusra1n -ED", "BLUE")

            ed_process = subprocess.Popen(
                "./bin/turdusra1n -ED",
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            self.process = ed_process

            # Read output
            for line in iter(ed_process.stdout.readline, ""):
                if self.terminated:
                    break
                self.logOutput.emit(line, None)

            try:
                if not self.terminated:
                    ed_process.wait(timeout=5)
                    if ed_process.returncode == 0:
                        return True
            except subprocess.TimeoutExpired:
                self.logOutput.emit("turdusra1n -ED command timed out", "RED")
                ed_process.kill()
                ed_process.wait()

            if self.terminated:
                return False

            self.logOutput.emit(f"Attempt {attempt} failed, retrying...", "YELLOW")
            attempt += 1

        self.logOutput.emit("Failed after multiple attempts", "RED")
        return False

    def terminate(self):
        """Terminate command execution"""
        self.terminated = True
        if self.process:
            try:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.process.pid)])
                else:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except Exception as e:
                print(f"Error terminating process: {str(e)}")
        super().terminate()


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


class TurdusGUI(QMainWindow):
    """Turdus Merula GUI main window"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Turdus Merula GUI")
        self.resize(1200, 700)
        self.setMinimumSize(900, 600)

        # Initialize variables
        self.firmware_path = None
        self.shcblock_path = None
        self.pteblock_path = None
        self.command_thread = None
        self.next_step_button = None  # Keep track of the next button to highlight

        # Set dark application style
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {BG_DARK};
                color: {TEXT_LIGHT};
            }}
            QGroupBox {{
                font-weight: bold;
                border: 1px solid #505050;
                border-radius: 3px;
                margin-top: 6px;
                padding-top: 6px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
            }}
            QLabel {{
                color: {TEXT_LIGHT};
            }}
            QComboBox {{
                background-color: {BG_MEDIUM};
                color: {TEXT_LIGHT};
                border: 1px solid #505050;
                border-radius: 3px;
                padding: 4px;
            }}
            QProgressBar {{
                border: 1px solid #505050;
                border-radius: 3px;
                background-color: {BG_MEDIUM};
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: {COLOR_BLUE};
            }}
            QScrollBar {{
                background-color: {BG_DARK};
            }}
            QScrollBar::handle {{
                background-color: #505050;
                border-radius: 4px;
            }}
        """)

        # Create main widget and layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # Create main horizontal layout
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(5)

        # Create left and right panels
        self.left_panel = QWidget()
        self.right_panel = QWidget()

        # Create splitter to allow resizing
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.right_panel)

        # Set initial splitter sizes (left:right = 55:45)
        self.splitter.setSizes([550, 450])

        # Create layouts for panels
        self.left_layout = QVBoxLayout(self.left_panel)
        self.right_layout = QVBoxLayout(self.right_panel)
        self.left_layout.setContentsMargins(2, 2, 2, 2)
        self.left_layout.setSpacing(8)
        self.right_layout.setContentsMargins(2, 2, 2, 2)
        self.right_layout.setSpacing(5)

        # Add splitter to main layout
        self.main_layout.addWidget(self.splitter)

        # Create UI components
        self.create_firmware_selector()
        self.create_file_path_widgets()
        self.create_operation_panel()
        self.create_log_area()
        self.create_status_bar()

        # Ensure necessary directories exist
        self.ensure_directories_exist()

        # Get firmware list
        self.refresh_firmware_list()

        # Highlight first step
        self.update_next_step_highlight()

    def ensure_directories_exist(self):
        """Ensure necessary directories exist"""
        os.makedirs("./ipsw", exist_ok=True)
        os.makedirs("./block", exist_ok=True)

    def create_firmware_selector(self):
        """Create firmware selector area"""
        firmware_frame = QFrame()
        firmware_layout = QHBoxLayout(firmware_frame)
        firmware_layout.setContentsMargins(5, 5, 5, 5)
        firmware_layout.setSpacing(5)

        firmware_label = QLabel("Firmware:")
        firmware_label.setStyleSheet("font-weight: bold;")
        firmware_layout.addWidget(firmware_label)

        self.firmware_combo = QComboBox()
        self.firmware_combo.setMinimumWidth(300)
        firmware_layout.addWidget(self.firmware_combo, 1)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_firmware_list)
        refresh_button.setFixedWidth(80)
        refresh_button.setStyleSheet("""
            QPushButton {
                background-color: #3D3D3D;
                color: #E0E0E0;
                border: 1px solid #505050;
                border-radius: 3px;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #4D4D4D;
            }
        """)
        firmware_layout.addWidget(refresh_button)

        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self.browse_firmware)
        browse_button.setFixedWidth(80)
        browse_button.setStyleSheet("""
            QPushButton {
                background-color: #3D3D3D;
                color: #E0E0E0;
                border: 1px solid #505050;
                border-radius: 3px;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #4D4D4D;
            }
        """)
        firmware_layout.addWidget(browse_button)

        # Add to left panel
        self.left_layout.addWidget(firmware_frame)

    def create_file_path_widgets(self):
        """Create widgets for displaying and selecting file paths"""
        file_paths_frame = QFrame()
        file_paths_layout = QGridLayout(file_paths_frame)
        file_paths_layout.setContentsMargins(5, 5, 5, 5)
        file_paths_layout.setSpacing(8)

        # SHC Block path selector
        self.shcblock_path_widget = FilePathWidget("SHC Block:", "SHC Block")
        file_paths_layout.addWidget(self.shcblock_path_widget, 0, 0)

        # PTE Block path selector
        self.pteblock_path_widget = FilePathWidget("PTE Block:", "PTE Block")
        file_paths_layout.addWidget(self.pteblock_path_widget, 1, 0)

        # Add to left panel
        self.left_layout.addWidget(file_paths_frame)

    def create_operation_panel(self):
        """Create operation panel with all operation buttons"""
        # Container for all operations
        operations_container = QWidget()
        operations_layout = QVBoxLayout(operations_container)
        operations_layout.setSpacing(8)
        operations_layout.setContentsMargins(0, 0, 0, 0)

        # PHASE 1: Enter Pwned DFU Mode
        self.phase1_group = QGroupBox("Phase 1: Enter Pwned DFU Mode")
        self.phase1_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
            }
        """)
        phase1_layout = QVBoxLayout(self.phase1_group)
        phase1_layout.setSpacing(8)
        phase1_layout.setContentsMargins(10, 20, 10, 10)

        # Operation descriptions and buttons
        p1_desc_layout = QGridLayout()
        p1_desc_layout.setColumnStretch(0, 1)  # Description column stretches
        p1_desc_layout.setColumnStretch(1, 0)  # Button column fixed
        p1_desc_layout.setColumnStretch(2, 0)  # Retry button column fixed

        # Step 1 description and button
        step1_desc = QLabel("Set permissions for turdusra1n and turdus_merula tools")
        step1_desc.setWordWrap(True)
        p1_desc_layout.addWidget(step1_desc, 0, 0)

        self.btn_set_permissions = OperationButton("1. Set Tool Permissions")
        self.btn_set_permissions.clicked.connect(self.set_tool_permissions)
        p1_desc_layout.addWidget(self.btn_set_permissions, 0, 1)

        retry_btn1 = QPushButton("Retry")
        retry_btn1.clicked.connect(self.set_tool_permissions)
        retry_btn1.setFixedWidth(60)
        retry_btn1.setStyleSheet("""
            QPushButton {
                background-color: #FFA500;
                color: black;
                border-radius: 3px;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #FFB52E;
            }
        """)
        retry_btn1.setVisible(False)
        self.btn_set_permissions.retry_button = retry_btn1
        p1_desc_layout.addWidget(retry_btn1, 0, 2)

        # Step 2 description and button
        step2_desc = QLabel("Put your device in DFU mode and exploit it with checkm8")
        step2_desc.setWordWrap(True)
        p1_desc_layout.addWidget(step2_desc, 1, 0)

        self.btn_enter_pwnedDFU = OperationButton("2. Enter Pwned DFU Mode")
        self.btn_enter_pwnedDFU.clicked.connect(self.enter_pwned_dfu)
        p1_desc_layout.addWidget(self.btn_enter_pwnedDFU, 1, 1)

        retry_btn2 = QPushButton("Retry")
        retry_btn2.clicked.connect(self.enter_pwned_dfu)
        retry_btn2.setFixedWidth(60)
        retry_btn2.setStyleSheet("""
            QPushButton {
                background-color: #FFA500;
                color: black;
                border-radius: 3px;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #FFB52E;
            }
        """)
        retry_btn2.setVisible(False)
        self.btn_enter_pwnedDFU.retry_button = retry_btn2
        p1_desc_layout.addWidget(retry_btn2, 1, 2)

        phase1_layout.addLayout(p1_desc_layout)
        operations_layout.addWidget(self.phase1_group)

        # PHASE 2: Extract SHC Block
        self.phase2_group = QGroupBox("Phase 2: Extract SHC Block")
        self.phase2_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
            }
        """)
        phase2_layout = QVBoxLayout(self.phase2_group)
        phase2_layout.setSpacing(8)
        phase2_layout.setContentsMargins(10, 20, 10, 10)

        # Operation descriptions and buttons
        p2_desc_layout = QGridLayout()
        p2_desc_layout.setColumnStretch(0, 1)  # Description column stretches
        p2_desc_layout.setColumnStretch(1, 0)  # Button column fixed
        p2_desc_layout.setColumnStretch(2, 0)  # Retry button column fixed

        # Step 3 description and button
        step3_desc = QLabel("Extract SHC from device")
        step3_desc.setWordWrap(True)
        p2_desc_layout.addWidget(step3_desc, 0, 0)

        self.btn_get_shcblock = OperationButton("3. Extract SHC Block")
        self.btn_get_shcblock.clicked.connect(self.extract_shcblock)
        p2_desc_layout.addWidget(self.btn_get_shcblock, 0, 1)

        retry_btn3 = QPushButton("Retry")
        retry_btn3.clicked.connect(self.extract_shcblock)
        retry_btn3.setFixedWidth(60)
        retry_btn3.setStyleSheet("""
            QPushButton {
                background-color: #FFA500;
                color: black;
                border-radius: 3px;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #FFB52E;
            }
        """)
        retry_btn3.setVisible(False)
        self.btn_get_shcblock.retry_button = retry_btn3
        p2_desc_layout.addWidget(retry_btn3, 0, 2)

        phase2_layout.addLayout(p2_desc_layout)
        operations_layout.addWidget(self.phase2_group)

        # PHASE 3: Extract PTE Block
        self.phase3_group = QGroupBox("Phase 3: Extract PTE Block")
        self.phase3_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
            }
        """)
        phase3_layout = QVBoxLayout(self.phase3_group)
        phase3_layout.setSpacing(8)
        phase3_layout.setContentsMargins(10, 20, 10, 10)

        # Operation descriptions and buttons
        p3_desc_layout = QGridLayout()
        p3_desc_layout.setColumnStretch(0, 1)  # Description column stretches
        p3_desc_layout.setColumnStretch(1, 0)  # Button column fixed
        p3_desc_layout.setColumnStretch(2, 0)  # Retry button column fixed

        # Step 4 description and button
        step4_desc = QLabel("Re-enter DFU mode")
        step4_desc.setWordWrap(True)
        p3_desc_layout.addWidget(step4_desc, 0, 0)

        self.btn_enter_pwnedDFU2 = OperationButton("4. Re-enter Pwned DFU Mode")
        self.btn_enter_pwnedDFU2.clicked.connect(self.reenter_pwned_dfu)
        p3_desc_layout.addWidget(self.btn_enter_pwnedDFU2, 0, 1)

        retry_btn4 = QPushButton("Retry")
        retry_btn4.clicked.connect(self.reenter_pwned_dfu)
        retry_btn4.setFixedWidth(60)
        retry_btn4.setStyleSheet("""
            QPushButton {
                background-color: #FFA500;
                color: black;
                border-radius: 3px;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #FFB52E;
            }
        """)
        retry_btn4.setVisible(False)
        self.btn_enter_pwnedDFU2.retry_button = retry_btn4
        p3_desc_layout.addWidget(retry_btn4, 0, 2)

        # Step 5 description and button
        step5_desc = QLabel("Extract PTE using SHC")
        step5_desc.setWordWrap(True)
        p3_desc_layout.addWidget(step5_desc, 1, 0)

        self.btn_get_pteblock = OperationButton("5. Extract PTE Block")
        self.btn_get_pteblock.clicked.connect(self.extract_pteblock)
        p3_desc_layout.addWidget(self.btn_get_pteblock, 1, 1)

        retry_btn5 = QPushButton("Retry")
        retry_btn5.clicked.connect(self.extract_pteblock)
        retry_btn5.setFixedWidth(60)
        retry_btn5.setStyleSheet("""
            QPushButton {
                background-color: #FFA500;
                color: black;
                border-radius: 3px;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #FFB52E;
            }
        """)
        retry_btn5.setVisible(False)
        self.btn_get_pteblock.retry_button = retry_btn5
        p3_desc_layout.addWidget(retry_btn5, 1, 2)

        phase3_layout.addLayout(p3_desc_layout)
        operations_layout.addWidget(self.phase3_group)

        # PHASE 4 and 5: Combined in a horizontal layout to save space
        phases_row = QHBoxLayout()
        phases_row.setSpacing(8)

        # PHASE 4: Restore Device
        self.phase4_group = QGroupBox("Phase 4: Restore Device")
        self.phase4_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
            }
        """)
        phase4_layout = QVBoxLayout(self.phase4_group)
        phase4_layout.setSpacing(8)
        phase4_layout.setContentsMargins(10, 20, 10, 10)

        # Operation descriptions and buttons
        p4_desc_layout = QGridLayout()
        p4_desc_layout.setColumnStretch(0, 1)  # Description column stretches
        p4_desc_layout.setColumnStretch(1, 0)  # Button column fixed
        p4_desc_layout.setColumnStretch(2, 0)  # Retry button column fixed

        # Step 6 description and button
        step6_desc = QLabel("Put device back in DFU")
        step6_desc.setWordWrap(True)
        p4_desc_layout.addWidget(step6_desc, 0, 0)

        self.btn_enter_pwnedDFU3 = OperationButton("6. Re-enter Pwned DFU Mode")
        self.btn_enter_pwnedDFU3.clicked.connect(self.reenter_pwned_dfu_for_restore)
        p4_desc_layout.addWidget(self.btn_enter_pwnedDFU3, 0, 1)

        retry_btn6 = QPushButton("Retry")
        retry_btn6.clicked.connect(self.reenter_pwned_dfu_for_restore)
        retry_btn6.setFixedWidth(60)
        retry_btn6.setStyleSheet("""
            QPushButton {
                background-color: #FFA500;
                color: black;
                border-radius: 3px;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #FFB52E;
            }
        """)
        retry_btn6.setVisible(False)
        self.btn_enter_pwnedDFU3.retry_button = retry_btn6
        p4_desc_layout.addWidget(retry_btn6, 0, 2)

        # Step 7 description and button
        step7_desc = QLabel("Restore to selected firmware")
        step7_desc.setWordWrap(True)
        p4_desc_layout.addWidget(step7_desc, 1, 0)

        self.btn_restore_device = OperationButton("7. Restore Device")
        self.btn_restore_device.clicked.connect(self.restore_device)
        p4_desc_layout.addWidget(self.btn_restore_device, 1, 1)

        retry_btn7 = QPushButton("Retry")
        retry_btn7.clicked.connect(self.restore_device)
        retry_btn7.setFixedWidth(60)
        retry_btn7.setStyleSheet("""
            QPushButton {
                background-color: #FFA500;
                color: black;
                border-radius: 3px;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #FFB52E;
            }
        """)
        retry_btn7.setVisible(False)
        self.btn_restore_device.retry_button = retry_btn7
        p4_desc_layout.addWidget(retry_btn7, 1, 2)

        phase4_layout.addLayout(p4_desc_layout)
        phases_row.addWidget(self.phase4_group)

        # PHASE 5: Boot Device
        self.phase5_group = QGroupBox("Phase 5: Boot Device")
        self.phase5_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
            }
        """)
        phase5_layout = QVBoxLayout(self.phase5_group)
        phase5_layout.setSpacing(8)
        phase5_layout.setContentsMargins(10, 20, 10, 10)

        # Operation descriptions and buttons
        p5_desc_layout = QGridLayout()
        p5_desc_layout.setColumnStretch(0, 1)  # Description column stretches
        p5_desc_layout.setColumnStretch(1, 0)  # Button column fixed
        p5_desc_layout.setColumnStretch(2, 0)  # Retry button column fixed

        # Step 8 description and button (directly boot the device)
        step8_desc = QLabel("Boot with restored firmware")
        step8_desc.setWordWrap(True)
        p5_desc_layout.addWidget(step8_desc, 0, 0)

        self.btn_boot_device = OperationButton("8. Boot Device")
        self.btn_boot_device.clicked.connect(self.boot_device)
        p5_desc_layout.addWidget(self.btn_boot_device, 0, 1)

        retry_btn8 = QPushButton("Retry")
        retry_btn8.clicked.connect(self.boot_device)
        retry_btn8.setFixedWidth(60)
        retry_btn8.setStyleSheet("""
            QPushButton {
                background-color: #FFA500;
                color: black;
                border-radius: 3px;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #FFB52E;
            }
        """)
        retry_btn8.setVisible(False)
        self.btn_boot_device.retry_button = retry_btn8
        p5_desc_layout.addWidget(retry_btn8, 0, 2)

        phase5_layout.addLayout(p5_desc_layout)
        phases_row.addWidget(self.phase5_group)

        operations_layout.addLayout(phases_row)

        # Add control buttons at the bottom
        control_frame = QFrame()
        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(5, 10, 5, 5)
        control_layout.setSpacing(10)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        control_layout.addWidget(self.progress_bar, 1)

        # Cancel button
        self.cancel_button = QPushButton("Cancel Operation")
        self.cancel_button.clicked.connect(self.cancel_operation)
        self.cancel_button.setEnabled(False)
        self.cancel_button.setStyleSheet("""
            QPushButton {
                padding: 8px 12px;
                background-color: #B22222;
                color: white;
                border-radius: 3px;
                border: none;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #DC143C;
            }
            QPushButton:disabled {
                background-color: #802020;
                color: #D0D0D0;
            }
        """)
        self.cancel_button.setFixedWidth(140)
        control_layout.addWidget(self.cancel_button)

        # Run all button
        self.run_all_button = QPushButton("Run All Operations")
        self.run_all_button.clicked.connect(self.run_all_operations)
        self.run_all_button.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                padding: 8px 12px;
                background-color: #0066CC;
                color: white;
                border-radius: 3px;
                border: none;
            }
            QPushButton:hover {
                background-color: #0077DD;
            }
            QPushButton:disabled {
                background-color: #004488;
                color: #D0D0D0;
            }
        """)
        self.run_all_button.setFixedWidth(150)
        self.run_all_button.setEnabled(False)
        control_layout.addWidget(self.run_all_button)

        operations_layout.addWidget(control_frame)

        # Add operations container to left panel
        self.left_layout.addWidget(operations_container, 1)  # Stretch to fill remaining space

    def create_log_area(self):
        """Create log area"""
        log_frame = QFrame()
        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(5, 5, 5, 5)
        log_layout.setSpacing(5)

        # Log header with title and clear button
        log_header = QFrame()
        header_layout = QHBoxLayout(log_header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        log_title = QLabel("Operation Log")
        log_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(log_title)

        header_layout.addStretch(1)

        # Clear log button
        clear_log_button = QPushButton("Clear Log")
        clear_log_button.clicked.connect(self.clear_log)
        clear_log_button.setFixedWidth(80)
        clear_log_button.setStyleSheet("""
            QPushButton {
                background-color: #3D3D3D;
                color: #E0E0E0;
                border: 1px solid #505050;
                border-radius: 3px;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #4D4D4D;
            }
        """)
        header_layout.addWidget(clear_log_button)

        log_layout.addWidget(log_header)

        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #252525;
                color: #E0E0E0;
                border: 1px solid #505050;
                font-family: Consolas, Courier, monospace;
                font-size: 12px;
            }
        """)
        log_layout.addWidget(self.log_text)

        # Add to right panel
        self.right_layout.addWidget(log_frame, 1)

    def create_status_bar(self):
        """Create status bar"""
        self.statusBar().showMessage("Ready")
        self.statusBar().setStyleSheet(f"QStatusBar {{ background-color: {BG_MEDIUM}; color: {TEXT_LIGHT}; }}")

    def refresh_firmware_list(self):
        """Refresh firmware file list"""
        ipsw_files = self.find_firmware_files()
        self.firmware_combo.clear()

        if ipsw_files:
            for file_path in ipsw_files:
                file_name = os.path.basename(file_path)
                self.firmware_combo.addItem(file_name, file_path)

            # Set the first file as current selection
            self.firmware_path = ipsw_files[0]
            self.btn_set_permissions.setEnabled(True)
            self.btn_enter_pwnedDFU.setEnabled(True)
            self.run_all_button.setEnabled(True)
            self.log_message("Firmware files found. Ready to start.", "BLUE")

            # Update step highlighting
            self.update_next_step_highlight()
        else:
            self.firmware_combo.addItem("No firmware files found")
            self.firmware_path = None
            self.btn_set_permissions.setEnabled(False)
            self.btn_enter_pwnedDFU.setEnabled(False)
            self.run_all_button.setEnabled(False)
            self.log_message(
                "No firmware files found. Please add an IPSW file to the ipsw folder or use the Browse button.",
                "YELLOW")

        # Connect selection change event
        self.firmware_combo.currentIndexChanged.connect(self.on_firmware_selected)

    def on_firmware_selected(self, index):
        """Handle firmware selection change"""
        if index >= 0 and self.firmware_combo.itemData(index):
            self.firmware_path = self.firmware_combo.itemData(index)
            self.log_message(f"Selected firmware: {os.path.basename(self.firmware_path)}", "GREEN")

            # Update step highlighting
            self.update_next_step_highlight()

    def find_firmware_files(self):
        """Find firmware files in the ipsw folder"""
        ipsw_dir = "./ipsw"
        if not os.path.exists(ipsw_dir):
            os.makedirs(ipsw_dir)

        ipsw_files = glob.glob(f"{ipsw_dir}/*.ipsw")
        return ipsw_files

    def browse_firmware(self):
        """Browse to select firmware file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Firmware File", "", "Firmware Files (*.ipsw);;All Files (*.*)"
        )

        if file_path:
            # Copy file to ipsw directory
            dest_dir = "./ipsw"
            os.makedirs(dest_dir, exist_ok=True)

            filename = os.path.basename(file_path)
            dest_path = os.path.join(dest_dir, filename)

            if file_path != dest_path:
                self.log_message(f"Copying file to ipsw directory: {filename}", "BLUE")

                try:
                    # Use system command to copy with progress indication
                    if sys.platform.startswith('win'):
                        subprocess.run(["copy", file_path, dest_path], shell=True, check=True)
                    else:
                        subprocess.run(["cp", file_path, dest_path], check=True)
                    self.log_message(f"File copy completed: {filename}", "GREEN")
                except subprocess.CalledProcessError:
                    self.log_message(f"Failed to copy file. Please manually copy the file to the ipsw directory.",
                                     "RED")
                    return

            self.refresh_firmware_list()

    def log_message(self, message, color_tag=None):
        """Add message to log area"""
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
        import re
        message = re.sub(r'\x1B\[[0-9;]*[mK]', '', message)

        # Ensure message ends with newline
        if not message.endswith('\n'):
            message += '\n'

        # Set color and add text
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        text_format = cursor.charFormat()
        if color_tag and color_tag in colors:
            text_format.setForeground(colors[color_tag])
        else:
            text_format.setForeground(QColor(TEXT_LIGHT))

        cursor.setCharFormat(text_format)
        cursor.insertText(message)

        # Scroll to bottom
        self.log_text.setTextCursor(cursor)
        self.log_text.ensureCursorVisible()

    def clear_log(self):
        """Clear log"""
        self.log_text.clear()
        self.log_message("Log cleared", "GREY")

    def find_latest_block(self, block_type):
        """Find the latest block file"""
        block_dirs = ["./block", "./blocks"]
        all_block_files = []

        for blocks_dir in block_dirs:
            if os.path.exists(blocks_dir):
                pattern = f"*-{block_type}.bin"
                block_files = glob.glob(os.path.join(blocks_dir, pattern))
                all_block_files.extend(block_files)

        if not all_block_files:
            self.log_message(f"No {block_type} files found in block/blocks folders!", "RED")
            return None

        # Sort by modification time
        latest_block = max(all_block_files, key=os.path.getmtime)
        self.log_message(f"Found latest {block_type} file: {os.path.basename(latest_block)}", "GREEN")
        return latest_block

    def run_command(self, command, callback=None, timeout=None, check_output=False, retry_with_ED=False, max_retries=2):
        """Run command"""
        if self.command_thread and self.command_thread.isRunning():
            self.log_message("A command is already running. Please wait for it to complete.", "YELLOW")
            return

        # Create and start thread
        self.command_thread = CommandThread(
            command, timeout, check_output, retry_with_ED, max_retries
        )

        # Connect signals
        self.command_thread.logOutput.connect(self.on_log_output)
        self.command_thread.commandComplete.connect(
            lambda success, output: self.on_command_complete(success, output, callback)
        )
        self.command_thread.timedOut.connect(self.handle_command_timeout)

        # Update UI status
        self.progress_bar.setRange(0, 0)  # Set to indeterminate mode
        self.cancel_button.setEnabled(True)
        self.disable_all_buttons()

        # Update status bar
        command_display = command[:50] + "..." if len(command) > 50 else command
        self.statusBar().showMessage(f"Running: {command_display}")

        # Start thread
        self.command_thread.start()

    def on_log_output(self, message, color_tag):
        """Handle command output log"""
        self.log_message(message, color_tag)

    def on_command_complete(self, success, output, callback):
        """Handle command completion"""
        self.progress_bar.setRange(0, 100)  # Restore normal mode
        self.progress_bar.setValue(100 if success else 0)
        self.cancel_button.setEnabled(False)
        self.statusBar().showMessage("Ready")

        # Enable appropriate buttons
        self.update_button_states()

        # Call callback function
        if callback:
            callback(success, output)

        # Update next step highlight
        self.update_next_step_highlight()

    def handle_command_timeout(self):
        """Handle command timeout for auto-retry"""
        self.log_message("Command timed out and will be automatically retried", "YELLOW")
        # The operation that called this command will be responsible for retrying

    def disable_all_buttons(self):
        """Disable all operation buttons"""
        # self.btn_set_permissions.setEnabled(False)
        # self.btn_enter_pwnedDFU.setEnabled(False)
        # self.btn_get_shcblock.setEnabled(False)
        # self.btn_enter_pwnedDFU2.setEnabled(False)
        # self.btn_get_pteblock.setEnabled(False)
        # self.btn_enter_pwnedDFU3.setEnabled(False)
        # self.btn_restore_device.setEnabled(False)
        # self.btn_boot_device.setEnabled(False)
        # self.run_all_button.setEnabled(False)

        # Hide retry buttons
        if self.btn_set_permissions.retry_button:
            self.btn_set_permissions.retry_button.setVisible(False)
        if self.btn_enter_pwnedDFU.retry_button:
            self.btn_enter_pwnedDFU.retry_button.setVisible(False)
        if self.btn_get_shcblock.retry_button:
            self.btn_get_shcblock.retry_button.setVisible(False)
        if self.btn_enter_pwnedDFU2.retry_button:
            self.btn_enter_pwnedDFU2.retry_button.setVisible(False)
        if self.btn_get_pteblock.retry_button:
            self.btn_get_pteblock.retry_button.setVisible(False)
        if self.btn_enter_pwnedDFU3.retry_button:
            self.btn_enter_pwnedDFU3.retry_button.setVisible(False)
        if self.btn_restore_device.retry_button:
            self.btn_restore_device.retry_button.setVisible(False)
        if self.btn_boot_device.retry_button:
            self.btn_boot_device.retry_button.setVisible(False)

    def update_button_states(self):
        """Update button states based on current progress"""
        # If no command is running, enable buttons based on progress
        if not (self.command_thread and self.command_thread.isRunning()):
            if self.firmware_path:
                self.btn_set_permissions.setEnabled(True)
                self.btn_enter_pwnedDFU.setEnabled(True)
                self.run_all_button.setEnabled(True)

                # Phase 2 button depends on Phase 1
                if self.btn_enter_pwnedDFU.status == "Completed":
                    self.btn_get_shcblock.setEnabled(True)

                # Phase 3 buttons depend on Phase 2
                if self.shcblock_path:
                    self.btn_enter_pwnedDFU2.setEnabled(True)
                    if self.btn_enter_pwnedDFU2.status == "Completed":
                        self.btn_get_pteblock.setEnabled(True)

                # Phase 4 buttons depend on Phase 3
                if self.pteblock_path:
                    self.btn_enter_pwnedDFU3.setEnabled(True)
                    if self.btn_enter_pwnedDFU3.status == "Completed":
                        self.btn_restore_device.setEnabled(True)

                    # Phase 5 boot button depends on Phase 4 restore complete
                    if self.btn_restore_device.status == "Completed":
                        self.btn_boot_device.setEnabled(True)

            # Set retry buttons visible for failed operations
            if self.btn_set_permissions.status == "Failed" and self.btn_set_permissions.retry_button:
                self.btn_set_permissions.retry_button.setVisible(True)

            if self.btn_enter_pwnedDFU.status == "Failed" and self.btn_enter_pwnedDFU.retry_button:
                self.btn_enter_pwnedDFU.retry_button.setVisible(True)

            if self.btn_get_shcblock.status == "Failed" and self.btn_get_shcblock.retry_button:
                self.btn_get_shcblock.retry_button.setVisible(True)

            if self.btn_enter_pwnedDFU2.status == "Failed" and self.btn_enter_pwnedDFU2.retry_button:
                self.btn_enter_pwnedDFU2.retry_button.setVisible(True)

            if self.btn_get_pteblock.status == "Failed" and self.btn_get_pteblock.retry_button:
                self.btn_get_pteblock.retry_button.setVisible(True)

            if self.btn_enter_pwnedDFU3.status == "Failed" and self.btn_enter_pwnedDFU3.retry_button:
                self.btn_enter_pwnedDFU3.retry_button.setVisible(True)

            if self.btn_restore_device.status == "Failed" and self.btn_restore_device.retry_button:
                self.btn_restore_device.retry_button.setVisible(True)

            if self.btn_enter_pwnedDFU.status == "Failed" and self.btn_enter_pwnedDFU.retry_button:
                self.btn_enter_pwnedDFU.retry_button.setVisible(True)

            if self.btn_boot_device.status == "Failed" and self.btn_boot_device.retry_button:
                self.btn_boot_device.retry_button.setVisible(True)

    def update_next_step_highlight(self):
        """Highlight the next step button to guide user workflow"""
        # Clear previous highlights
        buttons = [
            self.btn_set_permissions,
            self.btn_enter_pwnedDFU,
            self.btn_get_shcblock,
            self.btn_enter_pwnedDFU2,
            self.btn_get_pteblock,
            self.btn_enter_pwnedDFU3,
            self.btn_restore_device,
            self.btn_boot_device
        ]

        for button in buttons:
            if button.status != "Completed" and button.status != "Failed":
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

        # Find next step to highlight
        next_step = None
        if not self.firmware_path:
            # No firmware, user needs to select one
            return

        if self.btn_set_permissions.status != "Completed":
            next_step = self.btn_set_permissions
        elif self.btn_enter_pwnedDFU.status != "Completed":
            next_step = self.btn_enter_pwnedDFU
        elif self.btn_get_shcblock.status != "Completed":
            next_step = self.btn_get_shcblock
        elif not self.shcblock_path:
            # Waiting for SHC block
            pass
        elif self.btn_enter_pwnedDFU2.status != "Completed":
            next_step = self.btn_enter_pwnedDFU2
        elif self.btn_get_pteblock.status != "Completed":
            next_step = self.btn_get_pteblock
        elif not self.pteblock_path:
            # Waiting for PTE block
            pass
        elif self.btn_enter_pwnedDFU3.status != "Completed":
            next_step = self.btn_enter_pwnedDFU3
        elif self.btn_restore_device.status != "Completed":
            next_step = self.btn_restore_device
        elif self.btn_boot_device.status != "Completed":
            next_step = self.btn_boot_device

        # Highlight next step
        if next_step and next_step.isEnabled():
            next_step.setStyleSheet(f"""
                QPushButton {{
                    font-weight: bold;
                    padding: 6px 10px;
                    border-radius: 3px;
                    background-color: {HIGHLIGHT_COLOR};
                    color: white;
                    border: 1px solid {HIGHLIGHT_COLOR};
                    text-align: left;
                }}
                QPushButton:hover {{
                    background-color: #FF8533;
                }}
                QPushButton:pressed {{
                    background-color: #E65C00;
                }}
            """)

            self.next_step_button = next_step

    def update_button_status(self, button, status, color):
        """Update button status"""
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
                    border: none;
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
                    border: none;
                    text-align: left;
                }
                QPushButton:hover {
                    background-color: #BB0000;
                }
            """)

            # Show retry button
            if button.retry_button:
                button.retry_button.setVisible(True)

        elif status == "In Progress":
            button.setStyleSheet("""
                QPushButton {
                    font-weight: bold;
                    padding: 6px 10px;
                    border-radius: 3px;
                    background-color: #004488;
                    color: white;
                    border: none;
                    text-align: left;
                }
                QPushButton:hover {
                    background-color: #0055AA;
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

    def cancel_operation(self):
        """Cancel current operation"""
        if self.command_thread and self.command_thread.isRunning():
            self.log_message("Canceling current operation...", "YELLOW")
            try:
                # Properly terminate the thread
                self.command_thread.terminated = True

                # If process exists, terminate it gracefully
                if self.command_thread.process:
                    try:
                        if sys.platform == "win32":
                            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.command_thread.process.pid)],
                                           shell=True, check=False)
                        else:
                            self.command_thread.process.terminate()
                            self.command_thread.process.wait(timeout=2)
                    except (subprocess.SubprocessError, TimeoutError):
                        # If termination fails, try to kill
                        try:
                            self.command_thread.process.kill()
                        except:
                            pass

                # Wait for thread to finish but with timeout
                self.command_thread.wait(500)  # Wait up to 500ms for thread to finish

                if self.command_thread.isRunning():
                    self.log_message("Thread termination taking longer than expected...", "YELLOW")

            except Exception as e:
                self.log_message(f"Error during operation cancellation: {str(e)}", "RED")

            # Update UI regardless of termination success
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.cancel_button.setEnabled(False)
            self.statusBar().showMessage("Operation canceled")

            # Mark the current operation as failed if it exists
            if hasattr(self, "current_operation_button") and self.current_operation_button:
                self.update_button_status(self.current_operation_button, "Failed", COLOR_RED)
                self.current_operation_button = None

            # Re-enable buttons
            self.update_button_states()

            # Update next step highlight
            self.update_next_step_highlight()

    # Individual operation methods
    def set_tool_permissions(self):
        """Set permissions for the tools"""
        self.current_operation_button = self.btn_set_permissions
        self.update_button_status(self.btn_set_permissions, "In Progress", COLOR_BLUE)
        self.log_message("\n===== Setting tool permissions =====", "BLUE")

        # Run xattr command
        self.run_command(
            "/usr/bin/xattr -c ./bin/turdusra1n && /usr/bin/xattr -c ./bin/turdus_merula",
            callback=self._after_set_permissions
        )

    def _after_set_permissions(self, success, _):
        """Callback after setting permissions"""
        if success:
            self.log_message("Tool permissions set successfully", "GREEN")
            self.update_button_status(self.btn_set_permissions, "Completed", COLOR_GREEN)
        else:
            self.log_message("Failed to set tool permissions, but will continue...", "YELLOW")
            self.update_button_status(self.btn_set_permissions, "Warning", COLOR_YELLOW)

        # Automatically move to the next step if running all operations
        if hasattr(self, "_running_all") and self._running_all:
            self.enter_pwned_dfu()

    def enter_pwned_dfu(self):
        """Enter pwned DFU mode"""
        self.current_operation_button = self.btn_enter_pwnedDFU
        self.update_button_status(self.btn_enter_pwnedDFU, "In Progress", COLOR_BLUE)
        self.log_message("\n===== Entering pwned DFU mode =====", "BLUE")

        if not hasattr(self, "_running_all") or not self._running_all:
            # In manual mode, show confirmation dialog
            result = QMessageBox.question(
                self, "Enter DFU Mode",
                "Please make sure your device is connected and in DFU mode.\n\nReady to continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if result != QMessageBox.StandardButton.Yes:
                self.update_button_status(self.btn_enter_pwnedDFU, "Canceled", COLOR_GREY)
                self.current_operation_button = None
                self.update_next_step_highlight()
                return

        # Run turdusra1n -ED
        self.run_command(
            "./bin/turdusra1n -ED",
            callback=self._after_enter_pwned_dfu
        )

    def _after_enter_pwned_dfu(self, success, _):
        """Callback after entering pwned DFU mode"""
        if success:
            self.log_message("Successfully entered pwned DFU mode", "GREEN")
            self.update_button_status(self.btn_enter_pwnedDFU, "Completed", COLOR_GREEN)
            self.btn_get_shcblock.setEnabled(True)

            # Automatically move to the next step if running all operations
            if hasattr(self, "_running_all") and self._running_all:
                self.extract_shcblock()
        else:
            self.log_message("Failed to enter pwned DFU mode", "RED")
            self.update_button_status(self.btn_enter_pwnedDFU, "Failed", COLOR_RED)

            # Show error message in auto mode
            if hasattr(self, "_running_all") and self._running_all:
                QMessageBox.critical(
                    self, "Error",
                    "Failed to enter pwned DFU mode. Please check your device connection and try again."
                )
                delattr(self, "_running_all")

        self.current_operation_button = None

    def extract_shcblock(self):
        """Extract SHC block"""
        if not self.firmware_path:
            QMessageBox.critical(self, "Error", "No firmware selected. Please select a firmware file first.")
            return

        self.current_operation_button = self.btn_get_shcblock
        self.update_button_status(self.btn_get_shcblock, "In Progress", COLOR_BLUE)
        self.log_message("\n===== Extracting SHC block =====", "BLUE")

        # Run turdus_merula to get shcblock
        cmd = f"./bin/turdus_merula --get-shcblock \"{self.firmware_path}\""
        self.run_command(
            cmd,
            callback=self._after_extract_shcblock,
            retry_with_ED=True
        )

    def _after_extract_shcblock(self, success, _):
        """Callback after extracting SHC block"""
        if not success:
            self.log_message("Failed to extract SHC block after multiple attempts", "RED")
            self.update_button_status(self.btn_get_shcblock, "Failed", COLOR_RED)

            # Show error message in auto mode
            if hasattr(self, "_running_all") and self._running_all:
                QMessageBox.critical(
                    self, "Error",
                    "Failed to extract SHC block. Please try again."
                )
                delattr(self, "_running_all")

            self.current_operation_button = None
            return

        # Check if shcblock file was generated
        self.shcblock_path = self.find_latest_block("shcblock")
        if not self.shcblock_path:
            self.log_message("No SHC block file was generated", "RED")
            self.update_button_status(self.btn_get_shcblock, "Failed", COLOR_RED)

            # Show error message in auto mode
            if hasattr(self, "_running_all") and self._running_all:
                QMessageBox.critical(
                    self, "Error",
                    "No SHC block file was generated. Please try again."
                )
                delattr(self, "_running_all")

            self.current_operation_button = None
            return

        # Update SHC block path in the UI
        self.shcblock_path_widget.set_path(self.shcblock_path)

        self.log_message(f"Successfully extracted SHC block: {os.path.basename(self.shcblock_path)}", "GREEN")
        self.log_message("Device will restart. Please put it back in DFU mode for the next step.", "GREEN")
        self.update_button_status(self.btn_get_shcblock, "Completed", COLOR_GREEN)

        # Enable next button
        self.btn_enter_pwnedDFU2.setEnabled(True)

        # Automatically move to the next step if running all operations
        if hasattr(self, "_running_all") and self._running_all:
            self.log_message("Waiting 5 seconds for device to restart...", "BLUE")
            QTimer.singleShot(5000, self.prompt_for_dfu_reentry)

        self.current_operation_button = None

    def reenter_pwned_dfu(self):
        """Re-enter pwned DFU mode for PTE block extraction"""
        self.prompt_for_dfu_reentry()

    def prompt_for_dfu_reentry(self):
        """Prompt user to re-enter DFU mode"""
        self.current_operation_button = self.btn_enter_pwnedDFU2
        self.update_button_status(self.btn_enter_pwnedDFU2, "In Progress", COLOR_BLUE)
        self.log_message("\n===== Re-entering pwned DFU mode for PTE block extraction =====", "BLUE")

        if not hasattr(self, "_running_all") or not self._running_all:
            # In manual mode, show confirmation dialog
            result = QMessageBox.question(
                self, "Re-enter DFU Mode",
                "Please put your device back in DFU mode after restart.\n\nReady to continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if result != QMessageBox.StandardButton.Yes:
                self.update_button_status(self.btn_enter_pwnedDFU2, "Canceled", COLOR_GREY)
                self.current_operation_button = None
                self.update_next_step_highlight()
                return

        # Run turdusra1n -ED
        self.run_command(
            "./bin/turdusra1n -ED",
            callback=self._after_reenter_pwned_dfu
        )

    def _after_reenter_pwned_dfu(self, success, _):
        """Callback after re-entering pwned DFU mode"""
        if success:
            self.log_message("Successfully re-entered pwned DFU mode", "GREEN")
            self.update_button_status(self.btn_enter_pwnedDFU2, "Completed", COLOR_GREEN)
            self.btn_get_pteblock.setEnabled(True)

            # Automatically move to the next step if running all operations
            if hasattr(self, "_running_all") and self._running_all:
                self.extract_pteblock()
        else:
            self.log_message("Failed to re-enter pwned DFU mode", "RED")
            self.update_button_status(self.btn_enter_pwnedDFU2, "Failed", COLOR_RED)

            # Show error message in auto mode
            if hasattr(self, "_running_all") and self._running_all:
                QMessageBox.critical(
                    self, "Error",
                    "Failed to re-enter pwned DFU mode. Please check your device connection and try again."
                )
                delattr(self, "_running_all")

        self.current_operation_button = None

    def extract_pteblock(self):
        """Extract PTE block"""
        if not self.shcblock_path:
            QMessageBox.critical(self, "Error", "SHC block not found. Please extract the SHC block first.")
            return

        self.current_operation_button = self.btn_get_pteblock
        self.update_button_status(self.btn_get_pteblock, "In Progress", COLOR_BLUE)
        self.log_message("\n===== Extracting PTE block =====", "BLUE")

        # Get custom SHC block path if user changed it
        custom_shcblock_path = self.shcblock_path_widget.get_path()
        if custom_shcblock_path and custom_shcblock_path != self.shcblock_path:
            self.shcblock_path = custom_shcblock_path
            self.log_message(f"Using custom SHC block path: {custom_shcblock_path}", "BLUE")

        # Run turdus_merula to get pteblock
        cmd = f"./bin/turdus_merula --get-pteblock --load-shcblock \"{self.shcblock_path}\" \"{self.firmware_path}\""
        self.run_command(
            cmd,
            callback=self._after_extract_pteblock,
            retry_with_ED=True
        )

    def _after_extract_pteblock(self, success, _):
        """Callback after extracting PTE block"""
        if not success:
            self.log_message("Failed to extract PTE block after multiple attempts", "RED")
            self.update_button_status(self.btn_get_pteblock, "Failed", COLOR_RED)

            # Show error message in auto mode
            if hasattr(self, "_running_all") and self._running_all:
                QMessageBox.critical(
                    self, "Error",
                    "Failed to extract PTE block. Please try again."
                )
                delattr(self, "_running_all")

            self.current_operation_button = None
            return

        # Check if pteblock file was generated
        self.pteblock_path = self.find_latest_block("pteblock")
        if not self.pteblock_path:
            self.log_message("No PTE block file was generated", "RED")
            self.update_button_status(self.btn_get_pteblock, "Failed", COLOR_RED)

            # Show error message in auto mode
            if hasattr(self, "_running_all") and self._running_all:
                QMessageBox.critical(
                    self, "Error",
                    "No PTE block file was generated. Please try again."
                )
                delattr(self, "_running_all")

            self.current_operation_button = None
            return

        # Update PTE block path in the UI
        self.pteblock_path_widget.set_path(self.pteblock_path)

        self.log_message(f"Successfully extracted PTE block: {os.path.basename(self.pteblock_path)}", "GREEN")
        self.update_button_status(self.btn_get_pteblock, "Completed", COLOR_GREEN)

        # Enable next button
        self.btn_enter_pwnedDFU3.setEnabled(True)

        # Automatically move to the next step if running all operations
        if hasattr(self, "_running_all") and self._running_all:
            self.prompt_for_dfu_reentry_restore()

        self.current_operation_button = None

    def reenter_pwned_dfu_for_restore(self):
        """Re-enter pwned DFU mode for device restoration"""
        self.prompt_for_dfu_reentry_restore()

    def prompt_for_dfu_reentry_restore(self):
        """Prompt user to re-enter DFU mode for restoration"""
        self.current_operation_button = self.btn_enter_pwnedDFU3
        self.update_button_status(self.btn_enter_pwnedDFU3, "In Progress", COLOR_BLUE)
        self.log_message("\n===== Re-entering pwned DFU mode for device restoration =====", "BLUE")

        if not hasattr(self, "_running_all") or not self._running_all:
            # In manual mode, show confirmation dialog
            result = QMessageBox.question(
                self, "Re-enter DFU Mode",
                "Please put your device back in DFU mode.\n\nReady to continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if result != QMessageBox.StandardButton.Yes:
                self.update_button_status(self.btn_enter_pwnedDFU3, "Canceled", COLOR_GREY)
                self.current_operation_button = None
                self.update_next_step_highlight()
                return

        # Run turdusra1n -ED
        self.run_command(
            "./bin/turdusra1n -ED",
            callback=self._after_reenter_pwned_dfu_restore
        )

    def _after_reenter_pwned_dfu_restore(self, success, _):
        """Callback after re-entering pwned DFU mode for restoration"""
        if success:
            self.log_message("Successfully re-entered pwned DFU mode", "GREEN")
            self.update_button_status(self.btn_enter_pwnedDFU3, "Completed", COLOR_GREEN)
            self.btn_restore_device.setEnabled(True)

            # Automatically move to the next step if running all operations
            if hasattr(self, "_running_all") and self._running_all:
                self.restore_device()
        else:
            self.log_message("Failed to re-enter pwned DFU mode", "RED")
            self.update_button_status(self.btn_enter_pwnedDFU3, "Failed", COLOR_RED)

            # Show error message in auto mode
            if hasattr(self, "_running_all") and self._running_all:
                QMessageBox.critical(
                    self, "Error",
                    "Failed to re-enter pwned DFU mode. Please check your device connection and try again."
                )
                delattr(self, "_running_all")

        self.current_operation_button = None

    def restore_device(self):
        """Restore device"""
        # Check both the internal path and the widget path
        custom_pteblock_path = self.pteblock_path_widget.get_path()

        if not self.pteblock_path and not custom_pteblock_path:
            QMessageBox.critical(self, "Error", "PTE block not found. Please extract the PTE block first or select a PTE block file manually.")
            return

        self.current_operation_button = self.btn_restore_device
        self.update_button_status(self.btn_restore_device, "In Progress", COLOR_BLUE)
        self.log_message("\n===== Restoring device =====", "BLUE")

        # Use the manually selected path if available, otherwise use the internal path
        if custom_pteblock_path:
            self.pteblock_path = custom_pteblock_path
            self.log_message(f"Using custom PTE block path: {custom_pteblock_path}", "BLUE")

        # Run turdus_merula to restore device
        cmd = f"./bin/turdus_merula -o --load-pteblock \"{self.pteblock_path}\" \"{self.firmware_path}\""
        self.run_command(
            cmd,
            callback=self._after_restore_device,
            retry_with_ED=True
        )

    def _after_restore_device(self, success, _):
        """Callback after restoring device"""
        if not success:
            self.log_message("Failed to restore device after multiple attempts", "RED")
            self.update_button_status(self.btn_restore_device, "Failed", COLOR_RED)

            # Show error message in auto mode
            if hasattr(self, "_running_all") and self._running_all:
                QMessageBox.critical(
                    self, "Error",
                    "Failed to restore device. Please try again."
                )
                delattr(self, "_running_all")

            self.current_operation_button = None
            return

        self.log_message("Please follow any additional steps shown in the terminal", "GREEN")
        self.log_message("Device restoration completed successfully", "GREEN")
        self.update_button_status(self.btn_restore_device, "Completed", COLOR_GREEN)

        # Enable boot button directly
        self.btn_boot_device.setEnabled(True)

        # Automatically move to the next step if running all operations
        if hasattr(self, "_running_all") and self._running_all:
            self.boot_device()

        self.current_operation_button = None

    def reenter_pwned_dfu_for_boot(self):
        """Re-enter pwned DFU mode for device boot"""
        self.prompt_for_dfu_reentry_boot()

    def prompt_for_dfu_reentry_boot(self):
        """Prompt user to re-enter DFU mode for boot"""
        self.current_operation_button = self.btn_enter_pwnedDFU4
        self.update_button_status(self.btn_enter_pwnedDFU4, "In Progress", COLOR_BLUE)
        self.log_message("\n===== Re-entering pwned DFU mode for device boot =====", "BLUE")

        if not hasattr(self, "_running_all") or not self._running_all:
            # In manual mode, show confirmation dialog
            result = QMessageBox.question(
                self, "Re-enter DFU Mode",
                "Please put your device back in DFU mode.\n\nReady to continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if result != QMessageBox.StandardButton.Yes:
                self.update_button_status(self.btn_enter_pwnedDFU4, "Canceled", COLOR_GREY)
                self.current_operation_button = None
                self.update_next_step_highlight()
                return

        # Run turdusra1n -ED
        self.run_command(
            "./bin/turdusra1n -ED",
            callback=self._after_reenter_pwned_dfu_boot
        )

    def _after_reenter_pwned_dfu_boot(self, success, _):
        """Callback after re-entering pwned DFU mode for boot"""
        if success:
            self.log_message("Successfully re-entered pwned DFU mode", "GREEN")
            self.update_button_status(self.btn_enter_pwnedDFU4, "Completed", COLOR_GREEN)
            self.btn_boot_device.setEnabled(True)

            # Automatically move to the next step if running all operations
            if hasattr(self, "_running_all") and self._running_all:
                self.boot_device()
        else:
            self.log_message("Failed to re-enter pwned DFU mode", "RED")
            self.update_button_status(self.btn_enter_pwnedDFU4, "Failed", COLOR_RED)

            # Show error message in auto mode
            if hasattr(self, "_running_all") and self._running_all:
                QMessageBox.critical(
                    self, "Error",
                    "Failed to re-enter pwned DFU mode. Please check your device connection and try again."
                )
                delattr(self, "_running_all")

        self.current_operation_button = None

    def boot_device(self):
        """Boot device"""
        # Check both the internal path and the widget path
        custom_pteblock_path = self.pteblock_path_widget.get_path()

        if not self.pteblock_path and not custom_pteblock_path:
            QMessageBox.critical(self, "Error", "PTE block not found. Please restore the device first or select a PTE block file manually.")
            return

        self.current_operation_button = self.btn_boot_device
        self.update_button_status(self.btn_boot_device, "In Progress", COLOR_BLUE)
        self.log_message("\n===== Booting device =====", "BLUE")

        # Use the manually selected path if available, otherwise use the internal path
        if custom_pteblock_path:
            self.pteblock_path = custom_pteblock_path
            self.log_message(f"Using custom PTE block path: {custom_pteblock_path}", "BLUE")

        # Run turdusra1n -TP (no need to be in pwnd DFU mode for this)
        cmd = f"./bin/turdusra1n -TP \"{self.pteblock_path}\""
        self.run_command(
            cmd,
            callback=self._after_boot_device,
            retry_with_ED=True
        )

    def _after_boot_device(self, success, _):
        """Callback after booting device"""
        if not success:
            self.log_message("Failed to boot device after multiple attempts", "RED")
            self.update_button_status(self.btn_boot_device, "Failed", COLOR_RED)
        else:
            self.log_message("Device has been booted successfully!", "GREEN")
            self.update_button_status(self.btn_boot_device, "Completed", COLOR_GREEN)

        self.log_message("\n====== Process complete! ======", "GREEN")
        self.log_message("Your device should now be running the restored iOS version", "GREEN")

        # If running all operations, reset flag and show success message
        if hasattr(self, "_running_all") and self._running_all:
            delattr(self, "_running_all")
            QMessageBox.information(
                self, "Complete",
                "All operations completed successfully!\n\nYour device should now be running the restored iOS version."
            )

        self.current_operation_button = None

    def run_all_operations(self):
        """Run all operations in sequence"""
        if not self.firmware_path:
            self.log_message("Please select a firmware file first", "RED")
            return

        # Set flag indicating we're running all operations
        self._running_all = True

        # Confirmation dialog
        result = QMessageBox.question(
            self, "Run All Operations",
            "This will automatically execute all operations in sequence.\n\n"
            "You will be prompted when device interaction is required.\n\n"
            "Ready to begin?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if result == QMessageBox.StandardButton.Yes:
            # Start with first operation
            self.set_tool_permissions()


def main():
    """Main function"""
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
        import traceback

        traceback.print_exc()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import glob
import os
import signal
import subprocess
import sys
import shutil
import time

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton, QLabel, QProgressBar, QTextEdit,
    QFrame, QFileDialog, QMessageBox, QGroupBox, QGridLayout,
    QLineEdit, QSplitter, QToolButton, QRadioButton, QButtonGroup, QInputDialog
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
BUTTON_HIGHLIGHT_BORDER = "#FFB700"  # Border color for highlighted buttons
BUTTON_HIGHLIGHT_GLOW = "0 0 8px #FF8C00"  # Glow effect for highlighted buttons

# Paths
WORK_DIR = "./downgrade_work"


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
        self.process = None
        self.terminated = False
        self.dfu_timeout = dfu_timeout
        self.is_dfu_command = "turdusra1n -ED" in command
        self.last_output_time = 0
        self.dfu_auto_retry_count = 0
        self.max_dfu_retries = 3

    def run(self):
        output_lines = []
        success = False
        output = None

        # turdusra1n -ED 命令特殊处理，允许自动重试
        while (
                self.is_dfu_command and self.dfu_auto_retry_count < self.max_dfu_retries and not success and not self.terminated) or (
                not self.is_dfu_command and not self.terminated):
            if self.is_dfu_command and self.dfu_auto_retry_count > 0:
                self.logOutput.emit(
                    f"自动重试 turdusra1n -ED (尝试 {self.dfu_auto_retry_count + 1}/{self.max_dfu_retries})...",
                    "YELLOW")

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
            self.last_output_time = time.time()

            # 创建DFU命令监控定时器
            if self.is_dfu_command:
                dfu_timer = QTimer()
                dfu_timer.setSingleShot(False)  # 连续运行
                dfu_timer.timeout.connect(self.check_dfu_output)
                dfu_timer.start(1000)  # 每秒检查一次输出状态

            # Read output
            for line in iter(self.process.stdout.readline, ""):
                if self.terminated:
                    break
                self.logOutput.emit(line, None)  # Regular log, no color
                if self.check_output:
                    output_lines.append(line)

                # 更新最后输出时间
                self.last_output_time = time.time()

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

            # 停止DFU监控定时器
            if self.is_dfu_command and 'dfu_timer' in locals() and dfu_timer.isActive():
                dfu_timer.stop()

            # 如果不是DFU命令或者DFU命令成功，跳出循环
            if not self.is_dfu_command or success:
                break

            # DFU命令失败，增加重试计数
            self.dfu_auto_retry_count += 1

            # 如果已经达到最大重试次数，跳出循环
            if self.dfu_auto_retry_count >= self.max_dfu_retries:
                self.logOutput.emit(f"turdusra1n -ED 命令在 {self.max_dfu_retries} 次尝试后仍然失败", "RED")
                break

        if success and self.check_output:
            output = "".join(output_lines)

        self.commandComplete.emit(success, output if self.check_output else "")

    def check_dfu_output(self):
        """检查DFU命令是否有一段时间没有输出，如果是则尝试重启"""
        if not self.is_dfu_command or self.terminated or not self.process:
            return

        current_time = time.time()
        if current_time - self.last_output_time > 5:  # 5秒无输出
            self.logOutput.emit("turdusra1n -ED 命令已经 5 秒没有输出，正在自动重启...", "YELLOW")

            # 终止当前进程
            self.terminate_process()

            # 在run中会自动启动新的进程

    def terminate_process(self):
        """终止当前进程但不终止线程"""
        if self.process:
            try:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.process.pid)])
                else:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                self.process.wait(timeout=1)
            except Exception as e:
                print(f"Error terminating process: {str(e)}")
                try:
                    self.process.kill()
                except:
                    pass

    def terminate(self):
        """Terminate command execution"""
        self.terminated = True
        self.terminate_process()
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
        self.shsh_path = None
        self.shcblock_path = None
        self.pteblock_path = None
        self.command_thread = None
        self.next_step_button = None  # Keep track of the next button to highlight
        self.restart_from_phase = None  # Track which phase to restart from after a failure
        self.workflow_type = "a9_tether"  # 默认工作流类型
        self.generator = None  # 存储nonce generator

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

        # Highlight first step
        self.update_next_step_highlight()

    def ensure_directories_exist(self):
        """Ensure necessary directories exist"""
        os.makedirs(WORK_DIR, exist_ok=True)
        os.makedirs(os.path.join(WORK_DIR, "ipsw"), exist_ok=True)
        os.makedirs(os.path.join(WORK_DIR, "block"), exist_ok=True)

    def create_firmware_selector(self):
        """Create firmware selector area"""
        firmware_frame = QFrame()
        firmware_layout = QVBoxLayout(firmware_frame)
        firmware_layout.setContentsMargins(5, 5, 5, 5)
        firmware_layout.setSpacing(5)

        # Firmware selector
        firmware_row = QHBoxLayout()
        firmware_label = QLabel("Firmware:")
        firmware_label.setStyleSheet("font-weight: bold;")
        firmware_row.addWidget(firmware_label)

        self.firmware_path_label = QLineEdit()
        self.firmware_path_label.setReadOnly(True)
        self.firmware_path_label.setStyleSheet(f"""
            QLineEdit {{
                background-color: {BG_MEDIUM};
                color: {TEXT_LIGHT};
                border: 1px solid #505050;
                border-radius: 3px;
                padding: 4px;
            }}
        """)
        firmware_row.addWidget(self.firmware_path_label, 1)

        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self.browse_firmware)
        browse_button.setFixedWidth(100)
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
        firmware_row.addWidget(browse_button)
        firmware_layout.addLayout(firmware_row)

        # SHSH Blob selector
        shsh_row = QHBoxLayout()
        shsh_label = QLabel("SHSH Blob:")
        shsh_label.setStyleSheet("font-weight: bold;")
        shsh_row.addWidget(shsh_label)

        self.shsh_path_label = QLineEdit()
        self.shsh_path_label.setReadOnly(True)
        self.shsh_path_label.setStyleSheet(f"""
            QLineEdit {{
                background-color: {BG_MEDIUM};
                color: {TEXT_LIGHT};
                border: 1px solid #505050;
                border-radius: 3px;
                padding: 4px;
            }}
        """)
        shsh_row.addWidget(self.shsh_path_label, 1)

        shsh_browse_button = QPushButton("Browse...")
        shsh_browse_button.clicked.connect(self.browse_shsh)
        shsh_browse_button.setFixedWidth(100)
        shsh_browse_button.setStyleSheet("""
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
        shsh_row.addWidget(shsh_browse_button)
        firmware_layout.addLayout(shsh_row)

        # Add to left panel
        self.left_layout.addWidget(firmware_frame)

    def browse_shsh(self):
        """浏览选择SHSH文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select SHSH Blob File", "", "SHSH Files (*.shsh;*.shsh2);;All Files (*.*)"
        )

        if file_path:
            self.shsh_path = file_path
            self.shsh_path_label.setText(file_path)
            self.log_message(f"Selected SHSH blob: {os.path.basename(file_path)}", "GREEN")

    def update_workflow(self):
        """根据CPU类型和降级方式更新工作流程"""
        cpu_type = "A9" if self.radio_a9.isChecked() else "A10"
        downgrade_type = "tethered" if self.radio_tether.isChecked() else "untethered"

        workflow_msg = f"Workflow updated: {cpu_type} + {downgrade_type} downgrade"
        self.log_message(f"\n===== {workflow_msg} =====", "BLUE")

        # 根据不同的组合更新界面提示
        if cpu_type == "A9" and downgrade_type == "tethered":
            self.workflow_type = "a9_tether"
            self.log_message("A9+tethered降级流程: 将引导您提取SHC、PTE block并进行tethered降级", "GREEN")
            self.log_message("此降级方式需要在每次开机时连接电脑进行引导", "YELLOW")
        elif cpu_type == "A10" and downgrade_type == "tethered":
            self.workflow_type = "a10_tether"
            self.log_message("A10+tethered降级流程: 将直接进行固件还原和引导操作", "GREEN")
            self.log_message("此降级方式需要在每次开机时连接电脑进行引导", "YELLOW")
        elif cpu_type == "A9" and downgrade_type == "untethered":
            self.workflow_type = "a9_untether"
            self.log_message("A9+untethered降级流程: 将使用SHSH blob和SHC block进行untethered降级", "GREEN")
            self.log_message("请确保您已经选择了有效的SHSH blob文件", "YELLOW")
        else:  # A10 + untethered
            self.workflow_type = "a10_untether"
            self.log_message("A10+untethered降级流程: 将使用SHSH blob进行untethered降级", "GREEN")
            self.log_message("请确保您已经选择了有效的SHSH blob文件", "YELLOW")

        # 更新SHSH文件选择器的可见性
        # untethered 模式需要SHSH文件
        self.shsh_path_label.setEnabled(downgrade_type == "untethered")

        if downgrade_type == "untethered" and not self.shsh_path:
            self.log_message("请先选择SHSH blob文件再继续操作", "RED")

        # 重置未完成步骤的按钮状态以便重新高亮
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
                button.status = "Ready"

        # 更新按钮颜色高亮
        self.update_next_step_highlight()

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
        self.phase1_group = QGroupBox("Phase 1: Set Tool Permissions")
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

        # Step 2 description and button (moved from Phase 1)
        step2_desc = QLabel("Put your device in DFU mode and exploit it with checkm8")
        step2_desc.setWordWrap(True)
        p2_desc_layout.addWidget(step2_desc, 0, 0)

        self.btn_enter_pwnedDFU = OperationButton("2. Enter Pwned DFU Mode")
        self.btn_enter_pwnedDFU.clicked.connect(self.enter_pwned_dfu)
        p2_desc_layout.addWidget(self.btn_enter_pwnedDFU, 0, 1)

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
        p2_desc_layout.addWidget(retry_btn2, 0, 2)

        # Step 3 description and button
        step3_desc = QLabel("Extract SHC from device")
        step3_desc.setWordWrap(True)
        p2_desc_layout.addWidget(step3_desc, 1, 0)

        self.btn_get_shcblock = OperationButton("3. Extract SHC Block")
        self.btn_get_shcblock.clicked.connect(self.extract_shcblock)
        p2_desc_layout.addWidget(self.btn_get_shcblock, 1, 1)

        retry_btn3 = QPushButton("Retry")
        retry_btn3.clicked.connect(self.extract_shcblock)  # 直接重试，不再自动进入DFU
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
        p2_desc_layout.addWidget(retry_btn3, 1, 2)

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
        retry_btn5.clicked.connect(self.enter_pwned_dfu)  # Restart from Enter Pwned DFU
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
        retry_btn7.clicked.connect(self.enter_pwned_dfu)  # Restart from Enter Pwned DFU
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

        # Exit button (replacing run_all button)
        self.exit_button = QPushButton("Exit Program")
        self.exit_button.clicked.connect(self.close)
        self.exit_button.setStyleSheet("""
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
        """)
        self.exit_button.setFixedWidth(120)
        control_layout.addWidget(self.exit_button)

        operations_layout.addWidget(control_frame)

        # Add operations container to left panel
        self.left_layout.addWidget(operations_container, 1)  # Stretch to fill remaining space

    def create_log_area(self):
        """Create log area"""
        log_frame = QFrame()
        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(5, 5, 5, 5)
        log_layout.setSpacing(5)

        # 设备类型和降级方式选择
        options_frame = QFrame()
        options_layout = QHBoxLayout(options_frame)
        options_layout.setContentsMargins(5, 5, 5, 5)
        options_layout.setSpacing(8)

        # CPU 类型选择
        cpu_group_box = QGroupBox("CPU Type")
        cpu_group_box.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #505050;
                border-radius: 3px;
                margin-top: 6px;
                padding: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
            }
        """)
        cpu_layout = QHBoxLayout(cpu_group_box)

        self.cpu_type_group = QButtonGroup(cpu_group_box)
        self.radio_a9 = QRadioButton("A9(X)")
        self.radio_a10 = QRadioButton("A10(X)")
        self.radio_a9.setChecked(True)  # 默认选择A9

        radio_style = """
            QRadioButton {
                color: #E0E0E0;
                padding: 4px;
            }
            QRadioButton::indicator {
                width: 15px;
                height: 15px;
            }
        """
        self.radio_a9.setStyleSheet(radio_style)
        self.radio_a10.setStyleSheet(radio_style)

        self.cpu_type_group.addButton(self.radio_a9, 1)
        self.cpu_type_group.addButton(self.radio_a10, 2)

        cpu_layout.addWidget(self.radio_a9)
        cpu_layout.addWidget(self.radio_a10)

        # 降级方式选择
        downgrade_group_box = QGroupBox("Downgrade Type")
        downgrade_group_box.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #505050;
                border-radius: 3px;
                margin-top: 6px;
                padding: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
            }
        """)
        downgrade_layout = QHBoxLayout(downgrade_group_box)

        self.downgrade_type_group = QButtonGroup(downgrade_group_box)
        self.radio_tether = QRadioButton("Tethered")
        self.radio_untether = QRadioButton("Untethered")
        self.radio_tether.setChecked(True)  # 默认选择Tethered

        self.radio_tether.setStyleSheet(radio_style)
        self.radio_untether.setStyleSheet(radio_style)

        self.downgrade_type_group.addButton(self.radio_tether, 1)
        self.downgrade_type_group.addButton(self.radio_untether, 2)

        downgrade_layout.addWidget(self.radio_tether)
        downgrade_layout.addWidget(self.radio_untether)

        # 将选择框添加到选项布局中
        options_layout.addWidget(cpu_group_box)
        options_layout.addWidget(downgrade_group_box)

        # 连接选择变化信号
        self.cpu_type_group.buttonClicked.connect(self.update_workflow)
        self.downgrade_type_group.buttonClicked.connect(self.update_workflow)

        log_layout.addWidget(options_frame)

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

    def browse_firmware(self):
        """Browse to select firmware file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Firmware File", "", "Firmware Files (*.ipsw);;All Files (*.*)"
        )

        if file_path:
            self.firmware_path = file_path
            self.firmware_path_label.setText(file_path)
            self.log_message(f"Selected firmware: {os.path.basename(file_path)}", "GREEN")

            # Copy file to working directory if user wants
            if QMessageBox.question(
                    self, "Copy Firmware",
                    f"Would you like to copy {os.path.basename(file_path)} to the working directory?\n\n"
                    f"This will create a backup in {WORK_DIR}/ipsw/",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
            ) == QMessageBox.StandardButton.Yes:
                try:
                    dest_dir = os.path.join(WORK_DIR, "ipsw")
                    os.makedirs(dest_dir, exist_ok=True)
                    dest_path = os.path.join(dest_dir, os.path.basename(file_path))

                    self.log_message(f"Copying firmware to working directory...", "BLUE")
                    shutil.copy2(file_path, dest_path)
                    self.log_message(f"Firmware copied to: {dest_path}", "GREEN")
                except Exception as e:
                    self.log_message(f"Error copying firmware: {str(e)}", "RED")

            # Update next step highlight
            self.update_next_step_highlight()

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
        block_dirs = [os.path.join(WORK_DIR, "block"), os.path.join(WORK_DIR, "blocks"), "./block", "./blocks"]
        all_block_files = []

        for blocks_dir in block_dirs:
            if os.path.exists(blocks_dir):
                pattern = f"*-{block_type}.bin"
                block_files = glob.glob(os.path.join(blocks_dir, pattern))
                all_block_files.extend(block_files)

        if not all_block_files:
            self.log_message(f"No {block_type} files found in any directory.", "YELLOW")
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
            command, timeout, check_output, retry_with_ED=False, max_retries=1  # 禁用自动重试
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

        # Call callback function
        if callback:
            callback(success, output)

        # Enable appropriate buttons
        self.update_button_states()

        # Update next step highlight
        self.update_next_step_highlight()

    def handle_command_timeout(self):
        """Handle command timeout for auto-retry"""
        self.log_message("Command timed out and will be automatically retried", "YELLOW")
        # The operation that called this command will be responsible for retrying

    def disable_all_buttons(self):
        """Hide retry buttons during operations"""
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
        # If no command is running, show retry buttons for failed operations
        if not (self.command_thread and self.command_thread.isRunning()):
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

        # 清除所有按钮的高亮
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

        # Find next step to highlight based on current progress and workflow type
        next_step = None
        next_step_description = ""

        # 检查固件是否已选择
        if not self.firmware_path:
            self.log_message("请首先选择固件文件", "YELLOW")
            return

        # 检查untethered模式是否已选择SHSH文件
        if ("untether" in self.workflow_type) and not self.shsh_path:
            self.log_message("Untethered降级模式需要选择SHSH blob文件", "YELLOW")
            return

        # 根据不同工作流程确定下一步
        if self.workflow_type == "a9_tether":
            # A9 Tethered 工作流程
            if self.btn_set_permissions.status != "Completed":
                next_step = self.btn_set_permissions
                next_step_description = "A9+tethered降级: 首先设置工具权限"
            elif self.btn_enter_pwnedDFU.status != "Completed":
                next_step = self.btn_enter_pwnedDFU
                next_step_description = "A9+tethered降级: 进入Pwned DFU模式"
            elif self.btn_get_shcblock.status != "Completed":
                next_step = self.btn_get_shcblock
                next_step_description = "A9+tethered降级: 提取SHC Block"
            elif not self.shcblock_path and not self.shcblock_path_widget.get_path():
                # 提示选择 SHC block
                self.log_message("A9+tethered降级: 请选择一个SHC block文件以继续", "YELLOW")
                return
            elif self.btn_enter_pwnedDFU2.status != "Completed":
                next_step = self.btn_enter_pwnedDFU2
                next_step_description = "A9+tethered降级: 重新进入Pwned DFU模式提取PTE Block"
            elif self.btn_get_pteblock.status != "Completed":
                next_step = self.btn_get_pteblock
                next_step_description = "A9+tethered降级: 提取PTE Block"
            elif not self.pteblock_path and not self.pteblock_path_widget.get_path():
                # 提示选择 PTE block
                self.log_message("A9+tethered降级: 请选择一个PTE block文件以继续", "YELLOW")
                return
            elif self.btn_enter_pwnedDFU3.status != "Completed":
                next_step = self.btn_enter_pwnedDFU3
                next_step_description = "A9+tethered降级: 重新进入Pwned DFU模式准备还原设备"
            elif self.btn_restore_device.status != "Completed":
                next_step = self.btn_restore_device
                next_step_description = "A9+tethered降级: 还原设备到选定的固件"
            elif self.btn_boot_device.status != "Completed":
                next_step = self.btn_boot_device
                next_step_description = "A9+tethered降级: 引导设备启动"

        elif self.workflow_type == "a10_tether":
            # A10 Tethered 工作流程
            if self.btn_set_permissions.status != "Completed":
                next_step = self.btn_set_permissions
                next_step_description = "A10+tethered降级: 首先设置工具权限"
            elif self.btn_enter_pwnedDFU.status != "Completed":
                next_step = self.btn_enter_pwnedDFU
                next_step_description = "A10+tethered降级: 进入Pwned DFU模式"
            elif self.btn_restore_device.status != "Completed":
                next_step = self.btn_restore_device
                next_step_description = "A10+tethered降级: 还原设备到选定的固件"
            elif self.btn_enter_pwnedDFU2.status != "Completed":
                next_step = self.btn_enter_pwnedDFU2
                next_step_description = "A10+tethered降级: 重新进入Pwned DFU模式准备引导"
            elif self.btn_boot_device.status != "Completed":
                next_step = self.btn_boot_device
                next_step_description = "A10+tethered降级: 引导设备启动"

        elif self.workflow_type == "a9_untether":
            # A9 Untethered 工作流程
            if self.btn_set_permissions.status != "Completed":
                next_step = self.btn_set_permissions
                next_step_description = "A9+untethered降级: 首先设置工具权限"
            elif self.btn_enter_pwnedDFU.status != "Completed":
                next_step = self.btn_enter_pwnedDFU
                next_step_description = "A9+untethered降级: 进入Pwned DFU模式并输入Generator"
            elif self.btn_get_shcblock.status != "Completed":
                next_step = self.btn_get_shcblock
                next_step_description = "A9+untethered降级: 提取SHC Block"
            elif not self.shcblock_path and not self.shcblock_path_widget.get_path():
                # 提示选择 SHC block
                self.log_message("A9+untethered降级: 请选择一个SHC block文件以继续", "YELLOW")
                return
            elif self.btn_enter_pwnedDFU2.status != "Completed":
                next_step = self.btn_enter_pwnedDFU2
                next_step_description = "A9+untethered降级: 重新进入Pwned DFU模式准备还原"
            elif self.btn_restore_device.status != "Completed":
                next_step = self.btn_restore_device
                next_step_description = "A9+untethered降级: 使用SHSH和SHC还原设备"

        else:  # a10_untether
            # A10 Untethered 工作流程
            if self.btn_set_permissions.status != "Completed":
                next_step = self.btn_set_permissions
                next_step_description = "A10+untethered降级: 首先设置工具权限"
            elif self.btn_enter_pwnedDFU.status != "Completed":
                next_step = self.btn_enter_pwnedDFU
                next_step_description = "A10+untethered降级: 进入Pwned DFU模式并输入Generator"
            elif self.btn_restore_device.status != "Completed":
                next_step = self.btn_restore_device
                next_step_description = "A10+untethered降级: 使用SHSH还原设备"

        # 高亮下一步按钮并显示日志提示
        if next_step:
            # 使用更醒目的亮橙色作为下一步按钮的高亮颜色
            next_step.setStyleSheet(f"""
                QPushButton {{
                    font-weight: bold;
                    padding: 6px 10px;
                    border-radius: 3px;
                    background-color: {HIGHLIGHT_COLOR};
                    color: white;
                    border: 2px solid #FF8C00;
                    text-align: left;
                    box-shadow: 0 0 5px #FF8C00;
                }}
                QPushButton:hover {{
                    background-color: #FF8533;
                    border: 2px solid #FFA500;
                }}
                QPushButton:pressed {{
                    background-color: #E65C00;
                }}
            """)

            self.next_step_button = next_step

            # 在日志中显示下一步操作提示
            if next_step_description:
                self.log_message(f"\n下一步操作: {next_step_description}", "BLUE")

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
            # 闪烁效果在PyQt中需要使用定时器实现，这里使用动态的颜色变化
            button.setStyleSheet("""
                QPushButton {
                    font-weight: bold;
                    padding: 6px 10px;
                    border-radius: 3px;
                    background-color: #0066CC;
                    color: white;
                    border: 2px solid #4499FF;
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

                # If there's a restart point, show message
                if self.restart_from_phase:
                    QMessageBox.warning(
                        self, "Operation Failed",
                        f"The current operation has been canceled.\n\n"
                        f"You should restart from the {self.restart_from_phase} phase."
                    )

                self.current_operation_button = None

            # Re-enable buttons
            self.update_button_states()

            # Update next step highlight
            self.update_next_step_highlight()

    # Individual operation methods
    def set_tool_permissions(self):
        """Set permissions for the tools"""
        # Check if there's already a command running
        if self.command_thread and self.command_thread.isRunning():
            QMessageBox.warning(self, "Operation in Progress",
                                "Another operation is currently running. Please wait for it to complete.")
            return

        self.current_operation_button = self.btn_set_permissions
        self.update_button_status(self.btn_set_permissions, "In Progress", COLOR_BLUE)
        self.log_message("\n===== Setting tool permissions =====", "BLUE")

        # Run xattr command
        self.run_command(
            "/usr/bin/xattr -c ./bin/turdusra1n && /usr/bin/xattr -c ./bin/turdus_merula && chmod +x ./bin/turdusra1n && chmod +x ./bin/turdus_merula",
            callback=self._after_set_permissions
        )

    def _after_set_permissions(self, success, _):
        """Callback after setting permissions"""
        if success:
            self.log_message("Tool permissions set successfully", "GREEN")
            self.update_button_status(self.btn_set_permissions, "Completed", COLOR_GREEN)
        else:
            self.log_message("Failed to set tool permissions", "RED")
            self.update_button_status(self.btn_set_permissions, "Failed", COLOR_RED)
            QMessageBox.critical(
                self, "Error",
                "Failed to set tool permissions. Please check that the tools exist and try again."
            )

        self.current_operation_button = None

    def enter_pwned_dfu(self):
        """Enter pwned DFU mode"""
        if not self.firmware_path:
            QMessageBox.critical(self, "Error", "No firmware selected. Please select a firmware file first.")
            return

        # 对于untethered模式，检查是否有SHSH文件
        if ("untether" in self.workflow_type) and not self.shsh_path:
            QMessageBox.critical(self, "Error",
                                 "No SHSH blob selected. Please select an SHSH blob file for untethered downgrade.")
            return

        # 检查是否已经有命令在运行
        if self.command_thread and self.command_thread.isRunning():
            QMessageBox.warning(self, "Operation in Progress",
                                "Another operation is currently running. Please wait for it to complete.")
            return

        self.current_operation_button = self.btn_enter_pwnedDFU
        self.update_button_status(self.btn_enter_pwnedDFU, "In Progress", COLOR_BLUE)
        self.log_message("\n===== Entering pwned DFU mode =====", "BLUE")

        # 手动模式，显示确认对话框
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

        # 根据不同工作流程执行不同命令
        if "untether" in self.workflow_type:
            # 输入generator
            generator, ok = QInputDialog.getText(
                self, "Generator Input",
                "Enter the generator value from your SHSH blob:",
                QLineEdit.EchoMode.Normal
            )

            if not ok or not generator:
                self.update_button_status(self.btn_enter_pwnedDFU, "Canceled", COLOR_GREY)
                self.current_operation_button = None
                self.update_next_step_highlight()
                return

            self.generator = generator
            cmd = f"./bin/turdusra1n -EDb {generator}"
            self.log_message(f"Using generator: {generator}", "BLUE")
        else:
            cmd = "./bin/turdusra1n -ED"

        self.run_command(
            cmd,
            callback=self._after_enter_pwned_dfu
        )

    def _after_enter_pwned_dfu(self, success, _):
        """Callback after entering pwned DFU mode"""
        if success:
            self.log_message("Successfully entered pwned DFU mode", "GREEN")
            self.update_button_status(self.btn_enter_pwnedDFU, "Completed", COLOR_GREEN)
            self.btn_get_shcblock.setEnabled(True)
        else:
            self.log_message("Failed to enter pwned DFU mode", "RED")
            self.update_button_status(self.btn_enter_pwnedDFU, "Failed", COLOR_RED)
            QMessageBox.critical(
                self, "Error",
                "Failed to enter pwned DFU mode. Please check your device connection and try again."
            )

        self.current_operation_button = None

    def extract_shcblock(self):
        """Extract SHC block"""
        if not self.firmware_path:
            QMessageBox.critical(self, "Error", "No firmware selected. Please select a firmware file first.")
            return

        # Check if there's already a command running
        if self.command_thread and self.command_thread.isRunning():
            QMessageBox.warning(self, "Operation in Progress",
                                "Another operation is currently running. Please wait for it to complete.")
            return

        self.current_operation_button = self.btn_get_shcblock
        self.update_button_status(self.btn_get_shcblock, "In Progress", COLOR_BLUE)
        self.log_message("\n===== Extracting SHC block =====", "BLUE")

        # Create working directory for blocks
        block_dir = os.path.join(WORK_DIR, "block")
        os.makedirs(block_dir, exist_ok=True)

        # Run turdus_merula to get shcblock
        cmd = f"./bin/turdus_merula --get-shcblock \"{self.firmware_path}\""
        self.run_command(
            cmd,
            callback=self._after_extract_shcblock
        )

    def _after_extract_shcblock(self, success, _):
        """Callback after extracting SHC block"""
        if not success:
            self.log_message("Failed to extract SHC block", "RED")
            self.update_button_status(self.btn_get_shcblock, "Failed", COLOR_RED)

            QMessageBox.critical(
                self, "Error",
                "Failed to extract SHC block. Please try again after re-entering Pwned DFU mode."
            )
            self.current_operation_button = None
            return

        # Check if shcblock file was generated
        self.shcblock_path = self.find_latest_block("shcblock")
        if not self.shcblock_path:
            # Try to copy any SHC block found to our working directory
            found_blocks = []
            for path in ["./block", "./blocks"]:
                if os.path.exists(path):
                    blocks = glob.glob(os.path.join(path, "*-shcblock.bin"))
                    found_blocks.extend(blocks)

            if found_blocks:
                latest_block = max(found_blocks, key=os.path.getmtime)
                dest_path = os.path.join(WORK_DIR, "block", os.path.basename(latest_block))
                try:
                    shutil.copy2(latest_block, dest_path)
                    self.shcblock_path = dest_path
                    self.log_message(f"Copied SHC block to working directory: {os.path.basename(dest_path)}", "GREEN")
                except Exception as e:
                    self.log_message(f"Error copying SHC block: {str(e)}", "RED")

        if not self.shcblock_path:
            self.log_message("No SHC block file found - you need to select one manually.", "YELLOW")
            self.update_button_status(self.btn_get_shcblock, "Partial", COLOR_YELLOW)
            QMessageBox.warning(
                self, "Warning",
                "No SHC block file was found automatically. You can proceed but will need to select an SHC block file manually."
            )
            self.current_operation_button = None
            return

        # Update SHC block path in the UI
        self.shcblock_path_widget.set_path(self.shcblock_path)

        self.log_message(f"Successfully extracted SHC block: {os.path.basename(self.shcblock_path)}", "GREEN")
        self.log_message("Device will restart. Please put it back in DFU mode for the next step.", "GREEN")
        self.update_button_status(self.btn_get_shcblock, "Completed", COLOR_GREEN)

        # Enable next button
        self.current_operation_button = None

    def reenter_pwned_dfu(self):
        """Re-enter pwned DFU mode for PTE block extraction"""
        # Check if there's already a command running
        if self.command_thread and self.command_thread.isRunning():
            QMessageBox.warning(self, "Operation in Progress",
                                "Another operation is currently running. Please wait for it to complete.")
            return

        self.prompt_for_dfu_reentry()

    def prompt_for_dfu_reentry(self):
        """Prompt user to re-enter DFU mode"""
        self.current_operation_button = self.btn_enter_pwnedDFU2
        self.update_button_status(self.btn_enter_pwnedDFU2, "In Progress", COLOR_BLUE)
        self.log_message("\n===== Re-entering pwned DFU mode for PTE block extraction =====", "BLUE")

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
        else:
            self.log_message("Failed to re-enter pwned DFU mode", "RED")
            self.update_button_status(self.btn_enter_pwnedDFU2, "Failed", COLOR_RED)
            QMessageBox.critical(
                self, "Error",
                "Failed to re-enter pwned DFU mode. Please check your device connection and try again."
            )

        self.current_operation_button = None

    def extract_pteblock(self):
        """Extract PTE block"""
        if not self.firmware_path:
            QMessageBox.critical(self, "Error", "No firmware selected. Please select a firmware file first.")
            return

        # Check if there's already a command running
        if self.command_thread and self.command_thread.isRunning():
            QMessageBox.warning(self, "Operation in Progress",
                                "Another operation is currently running. Please wait for it to complete.")
            return

        # Check for SHC block, but allow custom path from widget
        custom_shcblock_path = self.shcblock_path_widget.get_path()
        if not self.shcblock_path and not custom_shcblock_path:
            QMessageBox.critical(self, "Error",
                                 "SHC block not found. Please extract the SHC block first or select an SHC block file manually.")
            return

        self.current_operation_button = self.btn_get_pteblock
        self.update_button_status(self.btn_get_pteblock, "In Progress", COLOR_BLUE)
        self.log_message("\n===== Extracting PTE block =====", "BLUE")

        # Get custom SHC block path if user changed it
        if custom_shcblock_path:
            self.shcblock_path = custom_shcblock_path
            self.log_message(f"Using custom SHC block path: {custom_shcblock_path}", "BLUE")

        # Create working directory for blocks
        block_dir = os.path.join(WORK_DIR, "block")
        os.makedirs(block_dir, exist_ok=True)

        # Run turdus_merula to get pteblock
        cmd = f"./bin/turdus_merula --get-pteblock --load-shcblock \"{self.shcblock_path}\" \"{self.firmware_path}\""
        self.run_command(
            cmd,
            callback=self._after_extract_pteblock
        )

    def _after_extract_pteblock(self, success, _):
        """Callback after extracting PTE block"""
        if not success:
            self.log_message("Failed to extract PTE block", "RED")
            self.update_button_status(self.btn_get_pteblock, "Failed", COLOR_RED)

            QMessageBox.critical(
                self, "Error",
                "Failed to extract PTE block. Please try again after re-entering Pwned DFU mode."
            )
            self.current_operation_button = None
            return

        # Check if pteblock file was generated
        self.pteblock_path = self.find_latest_block("pteblock")
        if not self.pteblock_path:
            # Try to copy any PTE block found to our working directory
            found_blocks = []
            for path in ["./block", "./blocks"]:
                if os.path.exists(path):
                    blocks = glob.glob(os.path.join(path, "*-pteblock.bin"))
                    found_blocks.extend(blocks)

            if found_blocks:
                latest_block = max(found_blocks, key=os.path.getmtime)
                dest_path = os.path.join(WORK_DIR, "block", os.path.basename(latest_block))
                try:
                    shutil.copy2(latest_block, dest_path)
                    self.pteblock_path = dest_path
                    self.log_message(f"Copied PTE block to working directory: {os.path.basename(dest_path)}", "GREEN")
                except Exception as e:
                    self.log_message(f"Error copying PTE block: {str(e)}", "RED")

        if not self.pteblock_path:
            self.log_message("No PTE block file found - you need to select one manually.", "YELLOW")
            self.update_button_status(self.btn_get_pteblock, "Partial", COLOR_YELLOW)
            QMessageBox.warning(
                self, "Warning",
                "No PTE block file was found automatically. You can proceed but will need to select a PTE block file manually."
            )
            self.current_operation_button = None
            return

        # Update PTE block path in the UI
        self.pteblock_path_widget.set_path(self.pteblock_path)

        self.log_message(f"Successfully extracted PTE block: {os.path.basename(self.pteblock_path)}", "GREEN")
        self.update_button_status(self.btn_get_pteblock, "Completed", COLOR_GREEN)

        # Enable next button
        self.current_operation_button = None

    def reenter_pwned_dfu_for_restore(self):
        """Re-enter pwned DFU mode for device restoration"""
        # Check if there's already a command running
        if self.command_thread and self.command_thread.isRunning():
            QMessageBox.warning(self, "Operation in Progress",
                                "Another operation is currently running. Please wait for it to complete.")
            return

        self.prompt_for_dfu_reentry_restore()

    def prompt_for_dfu_reentry_restore(self):
        """Prompt user to re-enter DFU mode for restoration"""
        self.current_operation_button = self.btn_enter_pwnedDFU3
        self.update_button_status(self.btn_enter_pwnedDFU3, "In Progress", COLOR_BLUE)
        self.log_message("\n===== Re-entering pwned DFU mode for device restoration =====", "BLUE")

        # In manual mode, show confirmation dialog
        result = QMessageBox.question(
            self, "Re-enter DFU Mode",
            "请将您的设备重新进入DFU模式准备进行还原。\n\n准备好继续吗?",
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
            self.log_message("成功重新进入Pwned DFU模式，准备进行设备还原", "GREEN")
            self.update_button_status(self.btn_enter_pwnedDFU3, "Completed", COLOR_GREEN)
            self.btn_restore_device.setEnabled(True)
        else:
            self.log_message("重新进入Pwned DFU模式失败", "RED")
            self.update_button_status(self.btn_enter_pwnedDFU3, "Failed", COLOR_RED)
            QMessageBox.critical(
                self, "错误",
                "进入Pwned DFU模式失败。请检查设备连接后重试。"
            )

        self.current_operation_button = None

    def restore_device(self):
        """Restore device"""
        if not self.firmware_path:
            QMessageBox.critical(self, "错误", "未选择固件。请先选择固件文件。")
            return

        # Check if there's already a command running
        if self.command_thread and self.command_thread.isRunning():
            QMessageBox.warning(self, "操作进行中",
                                "另一个操作正在进行。请等待其完成。")
            return

        # 根据不同工作流程检查所需文件
        if self.workflow_type == "a9_tether":
            # Check both the internal path and the widget path
            custom_pteblock_path = self.pteblock_path_widget.get_path()

            if not self.pteblock_path and not custom_pteblock_path:
                QMessageBox.critical(self, "错误",
                                     "未找到PTE block。请先提取PTE block或手动选择PTE block文件。")
                return

            # Use the manually selected path if available, otherwise use the internal path
            if custom_pteblock_path:
                self.pteblock_path = custom_pteblock_path

        elif self.workflow_type == "a9_untether":
            # 检查SHSH和SHC block
            if not self.shsh_path:
                QMessageBox.critical(self, "错误", "未选择SHSH blob文件。请选择SHSH blob文件。")
                return

            custom_shcblock_path = self.shcblock_path_widget.get_path()
            if not self.shcblock_path and not custom_shcblock_path:
                QMessageBox.critical(self, "错误",
                                     "未找到SHC block。请先提取SHC block或手动选择SHC block文件。")
                return

            # Use the manually selected path if available
            if custom_shcblock_path:
                self.shcblock_path = custom_shcblock_path

        elif self.workflow_type == "a10_untether":
            # 检查SHSH
            if not self.shsh_path:
                QMessageBox.critical(self, "错误", "未选择SHSH blob文件。请选择SHSH blob文件。")
                return

        # A10_tether不需要特殊检查

        self.current_operation_button = self.btn_restore_device
        self.update_button_status(self.btn_restore_device, "In Progress", COLOR_BLUE)
        self.log_message("\n===== 正在还原设备 =====", "BLUE")

        # 根据不同工作流程执行不同命令
        if self.workflow_type == "a9_tether":
            self.log_message(f"使用PTE block: {os.path.basename(self.pteblock_path)}", "BLUE")
            cmd = f"./bin/turdus_merula -o --load-pteblock \"{self.pteblock_path}\" \"{self.firmware_path}\""

        elif self.workflow_type == "a10_tether":
            cmd = f"./bin/turdus_merula -o \"{self.firmware_path}\""

        elif self.workflow_type == "a9_untether":
            self.log_message(f"使用SHC block: {os.path.basename(self.shcblock_path)}", "BLUE")
            self.log_message(f"使用SHSH blob: {os.path.basename(self.shsh_path)}", "BLUE")
            cmd = f"./bin/turdus_merula -w --load-shsh \"{self.shsh_path}\" --load-shcblock \"{self.shcblock_path}\" \"{self.firmware_path}\""

        else:  # a10_untether
            self.log_message(f"使用SHSH blob: {os.path.basename(self.shsh_path)}", "BLUE")
            cmd = f"./bin/turdus_merula -w --load-shsh \"{self.shsh_path}\" \"{self.firmware_path}\""

        self.run_command(
            cmd,
            callback=self._after_restore_device
        )

    def _after_restore_device(self, success, _):
        """Callback after restoring device"""
        if not success:
            self.log_message("设备还原失败", "RED")
            self.update_button_status(self.btn_restore_device, "Failed", COLOR_RED)

            QMessageBox.critical(
                self, "错误",
                "设备还原失败。请在重新进入Pwned DFU模式后再次尝试。"
            )
            self.current_operation_button = None
            return

        self.log_message("请按照终端窗口中显示的任何其他步骤进行操作", "GREEN")
        self.log_message("设备还原成功完成", "GREEN")
        self.update_button_status(self.btn_restore_device, "Completed", COLOR_GREEN)

        # 不需要显式启用，所有按钮都是可点击的
        self.current_operation_button = None

    def boot_device(self):
        """Boot device"""
        # Check if there's already a command running
        if self.command_thread and self.command_thread.isRunning():
            QMessageBox.warning(self, "操作进行中",
                                "另一个操作正在进行。请等待其完成。")
            return

        self.current_operation_button = self.btn_boot_device
        self.update_button_status(self.btn_boot_device, "In Progress", COLOR_BLUE)
        self.log_message("\n===== 正在引导设备启动 =====", "BLUE")

        # 根据不同工作流程执行不同命令
        if self.workflow_type == "a9_tether" or self.workflow_type == "a9_untether":
            # Check both the internal path and the widget path
            custom_pteblock_path = self.pteblock_path_widget.get_path()

            if not self.pteblock_path and not custom_pteblock_path:
                QMessageBox.critical(self, "错误",
                                     "未找到PTE block。请先完成设备还原或手动选择PTE block文件。")
                return

            # Use the manually selected path if available, otherwise use the internal path
            if custom_pteblock_path:
                self.pteblock_path = custom_pteblock_path
                self.log_message(f"使用自定义PTE block路径: {custom_pteblock_path}", "BLUE")

            # Run turdusra1n -TP
            cmd = f"./bin/turdusra1n -TP \"{self.pteblock_path}\""

        elif self.workflow_type == "a10_tether":
            # 检查image4文件夹中的文件
            image4_dir = "./image4"
            if not os.path.exists(image4_dir):
                QMessageBox.critical(self, "错误",
                                     "未找到image4文件夹。请检查还原操作是否成功完成。")
                self.update_button_status(self.btn_boot_device, "Failed", COLOR_RED)
                self.current_operation_button = None
                return

            # 查找需要的文件
            iboot_files = glob.glob(os.path.join(image4_dir, "*iBoot*.img4"))
            sep_signed_files = glob.glob(os.path.join(image4_dir, "*signed-SEP*.img4"))
            sep_target_files = glob.glob(os.path.join(image4_dir, "*target-SEP*.im4p"))

            if not iboot_files or not sep_signed_files or not sep_target_files:
                QMessageBox.critical(self, "错误",
                                     "未找到所需的image4文件。请检查还原操作是否成功完成。")
                self.update_button_status(self.btn_boot_device, "Failed", COLOR_RED)
                self.current_operation_button = None
                return

            iboot_file = iboot_files[0]
            sep_signed_file = sep_signed_files[0]
            sep_target_file = sep_target_files[0]

            self.log_message(f"使用iBoot文件: {os.path.basename(iboot_file)}", "BLUE")
            self.log_message(f"使用signed SEP文件: {os.path.basename(sep_signed_file)}", "BLUE")
            self.log_message(f"使用target SEP文件: {os.path.basename(sep_target_file)}", "BLUE")

            # Run turdusra1n -t -i -p
            cmd = f"./bin/turdusra1n -t \"{iboot_file}\" -i \"{sep_signed_file}\" -p \"{sep_target_file}\""

        else:  # a10_untether
            QMessageBox.information(self, "信息",
                                    "对于A10(X) untethered降级，设备将在还原后自动启动。")
            self.update_button_status(self.btn_boot_device, "Completed", COLOR_GREEN)
            self.current_operation_button = None
            return

        self.run_command(
            cmd,
            callback=self._after_boot_device
        )

    def _after_boot_device(self, success, _):
        """Callback after booting device"""
        if not success:
            self.log_message("设备引导失败", "RED")
            self.update_button_status(self.btn_boot_device, "Failed", COLOR_RED)
            QMessageBox.critical(
                self, "错误",
                "设备引导失败。请检查设备连接后重试。"
            )
        else:
            self.log_message("设备已成功引导启动！", "GREEN")
            self.update_button_status(self.btn_boot_device, "Completed", COLOR_GREEN)
            QMessageBox.information(
                self, "成功",
                "设备已成功引导启动！\n\n您的设备现在应该正在运行已还原的iOS版本。"
            )

        self.log_message("\n====== 流程完成！ ======", "GREEN")
        self.log_message("您的设备现在应该正在运行已还原的iOS版本", "GREEN")
        self.current_operation_button = None


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
        QMessageBox.critical(None, "错误", f"应用程序错误: {str(e)}")
        print(f"Error: {str(e)}")
        import traceback

        traceback.print_exc()

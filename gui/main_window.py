# -*- coding: utf-8 -*-

# gui/main_window.py - Main window implementation

import glob
import os
import shutil
import sys
import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QTextEdit,
    QFrame, QFileDialog, QMessageBox, QGroupBox, QGridLayout,
    QSplitter, QRadioButton, QButtonGroup, QInputDialog, QLineEdit,
    QApplication
)

from config import (
    COLOR_GREEN, COLOR_YELLOW, COLOR_RED, COLOR_BLUE, COLOR_GREY,
    BG_DARK, BG_MEDIUM, TEXT_LIGHT, HIGHLIGHT_COLOR, WORK_DIR,
    TURDUSRA1N_PATH, TURDUS_MERULA_PATH
)
from core.command import CommandThread
from core.utils import find_latest_block, ensure_directories_exist, copy_firmware_to_workdir
from core.workflows import (
    get_workflow, CPUType, DowngradeType, WorkflowStep,
    A9TetheredWorkflow, A10TetheredWorkflow, A9UntetheredWorkflow, A10UntetheredWorkflow
)
from gui.widgets import OperationButton, FilePathWidget
from gui.utils import log_message, update_button_status, highlight_next_step_button


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
        self.workflow = A9TetheredWorkflow()  # Default workflow
        self.generator = None  # Store nonce generator
        self.current_operation_button = None  # Track current operation button
        self.current_step = None  # Current workflow step

        # Button map for easier access
        self.button_map = {}

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
        ensure_directories_exist(WORK_DIR)

        # Highlight first step
        self.update_next_step_highlight()

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

        # Save button to button map for easy access by index
        self.button_map[1] = self.btn_set_permissions

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

        # Save button to button map
        self.button_map[2] = self.btn_enter_pwnedDFU

        # Step 3 description and button
        step3_desc = QLabel("Extract SHC from device")
        step3_desc.setWordWrap(True)
        p2_desc_layout.addWidget(step3_desc, 1, 0)

        self.btn_get_shcblock = OperationButton("3. Extract SHC Block")
        self.btn_get_shcblock.clicked.connect(self.extract_shcblock)
        p2_desc_layout.addWidget(self.btn_get_shcblock, 1, 1)

        retry_btn3 = QPushButton("Retry")
        retry_btn3.clicked.connect(self.extract_shcblock)  # Direct retry without auto-entering DFU
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

        # Save button to button map
        self.button_map[3] = self.btn_get_shcblock

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

        # Save button to button map
        self.button_map[4] = self.btn_enter_pwnedDFU2

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

        # Save button to button map
        self.button_map[5] = self.btn_get_pteblock

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

        # Save button to button map
        self.button_map[6] = self.btn_enter_pwnedDFU3

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

        # Save button to button map
        self.button_map[7] = self.btn_restore_device

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

        # Save button to button map
        self.button_map[8] = self.btn_boot_device

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

        # Device type and downgrade method selection
        options_frame = QFrame()
        options_layout = QHBoxLayout(options_frame)
        options_layout.setContentsMargins(5, 5, 5, 5)
        options_layout.setSpacing(8)

        # CPU type selection
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
        self.radio_a9.setChecked(True)  # Default select A9

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

        # Downgrade method selection
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
        self.radio_tether.setChecked(True)  # Default select Tethered

        self.radio_tether.setStyleSheet(radio_style)
        self.radio_untether.setStyleSheet(radio_style)

        self.downgrade_type_group.addButton(self.radio_tether, 1)
        self.downgrade_type_group.addButton(self.radio_untether, 2)

        downgrade_layout.addWidget(self.radio_tether)
        downgrade_layout.addWidget(self.radio_untether)

        # Add selection boxes to options layout
        options_layout.addWidget(cpu_group_box)
        options_layout.addWidget(downgrade_group_box)

        # Connect selection change signals
        self.cpu_type_group.buttonClicked.connect(self.update_workflow)
        self.downgrade_type_group.buttonClicked.connect(self.update_workflow)

        log_layout.addWidget(options_frame)

        # Log header with title and buttons
        log_header = QFrame()
        header_layout = QHBoxLayout(log_header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        log_title = QLabel("Operation Log")
        log_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(log_title)

        header_layout.addStretch(1)

        # Generate log button
        generate_log_button = QPushButton("Generate Log")
        generate_log_button.clicked.connect(self.generate_log_file)
        generate_log_button.setFixedWidth(120)
        generate_log_button.setStyleSheet("""
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
        header_layout.addWidget(generate_log_button)

        # Add spacing between buttons
        header_layout.addSpacing(5)

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
                font-family: "Courier New", monospace, Courier;
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

            # 直接使用选择的固件文件，不再复制到工作目录

            # 更新工作流按钮状态
            self.update_workflow_buttons()

    def browse_shsh(self):
        """Browse and select SHSH file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select SHSH Blob File", "", "SHSH Files (*.shsh;*.shsh2);;All Files (*.*)"
        )

        if file_path:
            self.shsh_path = file_path
            self.shsh_path_label.setText(file_path)
            self.log_message(f"Selected SHSH blob: {os.path.basename(file_path)}", "GREEN")
            # 更新工作流按钮状态
            self.update_workflow_buttons()

    def log_message(self, message, color_tag=None):
        """Add formatted message to log area with timestamp if not already present"""
        # Add timestamp if not already in message
        if not message.startswith("[20"):  # Check if message already has timestamp
            current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            if color_tag == "RED":
                prefix = "[ERROR] "
            elif color_tag == "YELLOW":
                prefix = "[WARN] "
            elif color_tag == "GREEN":
                prefix = "[INFO] "
            elif color_tag == "BLUE":
                prefix = "[SYSTEM] "
            else:
                prefix = "[LOG] "

            # Only add timestamp for messages without it
            if not message.startswith(prefix):
                message = f"[{current_time}] {prefix}{message}"

        # Use the utility function to log the message
        log_message(self.log_text, message, color_tag)

    def clear_log(self):
        """Clear log and add header"""
        self.log_text.clear()
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        self.log_message(f"[{current_time}] Log cleared - Starting new session", "GREY")

    def generate_log_file(self):
        """Generate a log file with current content"""
        # Create logs directory if it doesn't exist
        log_dir = os.path.join(WORK_DIR, "logs")
        os.makedirs(log_dir, exist_ok=True)

        # Generate filename with timestamp
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        log_filename = os.path.join(log_dir, f"turdus_log_{timestamp}.txt")

        try:
            # Write log content to file
            with open(log_filename, 'w', encoding='utf-8') as f:
                f.write(self.log_text.toPlainText())

            # Add confirmation to log
            self.log_message(f"Log file saved to: {log_filename}", "GREEN")

            # Show confirmation dialog
            QMessageBox.information(
                self, "Log Generated",
                f"Log file has been saved to:\n{log_filename}"
            )

        except Exception as e:
            error_msg = f"Error saving log file: {str(e)}"
            self.log_message(error_msg, "RED")
            QMessageBox.critical(self, "Error", error_msg)

    def update_workflow(self):
        """Update workflow based on CPU type and downgrade method"""
        # Get selected CPU type
        cpu_type = CPUType.A9 if self.radio_a9.isChecked() else CPUType.A10

        # Get selected downgrade type
        downgrade_type = DowngradeType.TETHERED if self.radio_tether.isChecked() else DowngradeType.UNTETHERED

        # Get the corresponding workflow
        self.workflow = get_workflow(cpu_type.value, downgrade_type.value)

        # Auto clear log when workflow changes
        self.clear_log()

        # Log workflow change with timestamp
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        workflow_msg = f"Workflow updated: {cpu_type.value} + {downgrade_type.value} downgrade"
        self.log_message(f"[{current_time}] ===== {workflow_msg} =====", "BLUE")

        # Log workflow information
        self.log_message(f"[INFO] {self.workflow.log_message}", "GREEN")
        self.log_message(f"[WARN] {self.workflow.warning_message}", "YELLOW")

        # Update SHSH file selector visibility - untethered mode needs SHSH file
        self.shsh_path_label.setEnabled(downgrade_type == DowngradeType.UNTETHERED)

        if downgrade_type == DowngradeType.UNTETHERED and not self.shsh_path:
            self.log_message("[ERROR] Please select an SHSH blob file before continuing", "RED")

        # Reset button status, but preserve completed steps
        for button_index, button in self.button_map.items():
            # Check if button corresponds to a step in current workflow
            button_is_relevant = False
            for step_info in self.workflow.steps.values():
                if step_info.button_index == button_index:
                    button_is_relevant = True
                    break

            # Only modify status of relevant buttons
            if button_is_relevant:
                # If button is already completed, keep that status
                if button.status != "Completed" and button.status != "Failed":
                    button.status = "Ready"
                button.setVisible(True)  # Ensure relevant buttons are visible
            else:
                # For irrelevant buttons, hide them
                button.setVisible(False)

        # Reset current step to determine where to start
        self.current_step = None

        # Update button highlights, showing next step in new workflow
        self.update_workflow_buttons()

    def run_command(self, command, callback=None, timeout=None, check_output=False, retry_with_ED=False, max_retries=2):
        """Run command with improved safety"""
        try:
            # 检查是否有命令正在运行
            if self.command_thread and self.command_thread.isRunning():
                self.log_message("A command is already running. Please wait for it to complete or cancel it.", "YELLOW")
                return

            # 先更新UI状态，确保UI响应
            self.progress_bar.setRange(0, 0)  # Set to indeterminate mode
            self.cancel_button.setEnabled(True)
            self.disable_all_buttons()

            command_display = command[:50] + "..." if len(command) > 50 else command
            self.statusBar().showMessage(f"Running: {command_display}")

            # 立即处理事件队列，确保UI更新被处理
            QApplication.processEvents()

            # 如果之前的线程存在但已经停止，断开所有之前的连接
            if self.command_thread and not self.command_thread.isRunning():
                try:
                    # 断开之前的信号连接以防止内存泄漏
                    self.command_thread.logOutput.disconnect()
                    self.command_thread.commandComplete.disconnect()
                    self.command_thread.timedOut.disconnect()
                except Exception:
                    # 忽略断开连接时的异常
                    pass

            # 创建新线程
            self.command_thread = CommandThread(
                command, timeout, check_output, retry_with_ED=False, max_retries=1  # Disable auto-retry
            )

            # 使用try-except以确保连接信号时的安全
            try:
                # Connect signals
                self.command_thread.logOutput.connect(self.on_log_output)
                self.command_thread.commandComplete.connect(
                    lambda success, output: self.on_command_complete(success, output, callback)
                )
                self.command_thread.timedOut.connect(self.handle_command_timeout)
            except Exception as e:
                self.log_message(f"Warning: Signal connection issue: {str(e)}", "RED")
                self.progress_bar.setRange(0, 100)
                self.cancel_button.setEnabled(False)
                return

            # 使用延迟启动的方式，确保UI状态已完全更新
            QTimer.singleShot(100, self.command_thread.start)

        except Exception as e:
            # 捕获所有异常，确保UI保持响应
            self.log_message(f"Error starting command: {str(e)}", "RED")
            self.progress_bar.setRange(0, 100)
            self.cancel_button.setEnabled(False)

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

        # 不清除线程引用，让Qt自己处理线程对象的生命周期
        # self.command_thread = None  # 这行可能导致崩溃

        # Enable appropriate buttons
        self.update_button_states()

        # 更新工作流按钮状态
        self.update_workflow_buttons()

    def handle_command_timeout(self):
        """Handle command timeout for auto-retry"""
        self.log_message("Command timed out and will be automatically retried", "YELLOW")
        # The operation that called this command will be responsible for retrying

    def disable_all_buttons(self):
        """Hide retry buttons during operations"""
        # Hide all retry buttons
        for button_index in self.button_map:
            button = self.button_map[button_index]
            if hasattr(button, 'retry_button') and button.retry_button:
                button.retry_button.setVisible(False)

    def update_button_states(self):
        """Update button states based on current progress"""
        # If no command is running, show retry buttons for failed operations
        if not (self.command_thread and self.command_thread.isRunning()):
            for button_index in self.button_map:
                button = self.button_map[button_index]
                if button.status == "Failed" and button.retry_button:
                    button.retry_button.setVisible(True)

    def cancel_operation(self):
        """Cancel current operation"""
        if self.command_thread and self.command_thread.isRunning():
            self.log_message("Canceling current operation...", "YELLOW")

            # 使用延迟更新UI的方法,首先更新UI，然后再进行线程操作
            # 这样可以防止UI线程被阻塞
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.cancel_button.setEnabled(False)
            self.statusBar().showMessage("Operation canceled")

            # 立即处理事件队列，确保UI更新被处理
            QApplication.processEvents()

            try:
                # 设置终止标志 - 但不强制终止线程
                self.command_thread.terminated = True

                # 使用安全的方式终止子进程
                if hasattr(self.command_thread, 'process') and self.command_thread.process:
                    try:
                        self.command_thread.terminate_process()
                    except Exception as e:
                        # 捕获所有终止进程的异常，但不允许它们影响UI
                        self.log_message(f"Note: Process termination issue: {str(e)}", "YELLOW")

                # 通过计时器增加安全性，确保即使有异常，UI也会更新
                QTimer.singleShot(100, lambda: self.finalize_cancel_operation())

            except Exception as e:
                self.log_message(f"Error during operation cancellation: {str(e)}", "RED")
                # 即使异常，也要保证继续进行UI更新
                self.finalize_cancel_operation()

    def finalize_cancel_operation(self):
        """在取消操作完成后更新UI状态"""
        try:
            # 标记当前操作失败
            if hasattr(self, "current_operation_button") and self.current_operation_button:
                update_button_status(self.current_operation_button, "Failed", COLOR_RED)

                # 如果有重启点，显示消息
                if self.restart_from_phase:
                    QMessageBox.warning(
                        self, "Operation Failed",
                        f"The current operation has been canceled.\n\n"
                        f"You should restart from the {self.restart_from_phase} phase."
                    )

                self.current_operation_button = None

            # 重新启用按钮
            self.update_button_states()

            # 更新工作流按钮状态
            self.update_workflow_buttons()

        except Exception as e:
            # 最终的安全网，捕获所有异常
            self.log_message(f"Warning: UI update issue: {str(e)}", "RED")

    def update_next_step_highlight(self):
        """Find the next step to execute and provide guidance"""
        # Check firmware and SHSH files
        if not self.firmware_path:
            self.log_message("Please select a firmware file first", "YELLOW")
            return

        if self.workflow.downgrade_type == DowngradeType.UNTETHERED and not self.shsh_path:
            self.log_message(f"{self.workflow.description}: Please select an SHSH blob file", "YELLOW")
            return

        # Find next step
        next_step_info = None

        # If no current step, get the first step
        if not self.current_step:
            next_step_info = self.workflow.get_first_step()
        else:
            # Find next step based on current step and completion status
            current_step_button = self.button_map.get(self.workflow.steps[self.current_step].button_index)

            # Only proceed to next step if current step is completed
            if current_step_button and current_step_button.status == "Completed":
                next_step_info = self.workflow.get_next_step(self.current_step)

                # Check for files before proceeding
                if next_step_info and WorkflowStep.CHECK_SHC == next_step_info.step:
                    # Check if SHC file exists or is selected
                    if not self.shcblock_path and not self.shcblock_path_widget.get_path():
                        self.log_message(next_step_info.description, "YELLOW")
                        return
                    # If SHC file exists, skip to next step
                    next_step_info = self.workflow.get_next_step(next_step_info.step)

                elif next_step_info and WorkflowStep.CHECK_PTE == next_step_info.step:
                    # Check if PTE file exists or is selected
                    if not self.pteblock_path and not self.pteblock_path_widget.get_path():
                        self.log_message(next_step_info.description, "YELLOW")
                        return
                    # If PTE file exists, skip to next step
                    next_step_info = self.workflow.get_next_step(next_step_info.step)
            else:
                # If current step is not completed, highlight it
                next_step_info = self.workflow.steps.get(self.current_step)

        # If we have a next step, provide guidance
        if next_step_info and next_step_info.button_index > 0:
            next_button = self.button_map.get(next_step_info.button_index)
            if next_button:
                # Show next operation guidance
                self.log_message(f"Next operation: {next_step_info.description}", "BLUE")

                # Set current step
                self.current_step = next_step_info.step

    def update_workflow_buttons(self):
        """更新当前工作流程中所有按钮的显示和高亮状态"""
        # 先重置所有按钮为基本样式
        for button_index, button in self.button_map.items():
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

        # 如果没有选择固件，提示用户并返回
        if not self.firmware_path:
            self.log_message("Please select a firmware file first", "YELLOW")
            return

        # 如果是非绑定降级但没有SHSH，提示用户并返回
        if self.workflow.downgrade_type == DowngradeType.UNTETHERED and not self.shsh_path:
            self.log_message(f"{self.workflow.description}: Please select an SHSH blob file", "YELLOW")
            return

        # 高亮显示当前工作流所有需要的按钮
        workflow_buttons = []
        for step_info in self.workflow.steps.values():
            if step_info.button_index > 0:  # 跳过没有对应按钮的步骤
                button = self.button_map.get(step_info.button_index)
                if button:
                    workflow_buttons.append(button)

                    # 如果按钮尚未完成或失败，高亮显示它
                    if button.status != "Completed" and button.status != "Failed":
                        highlight_next_step_button(button)

        # 找出需要执行的下一个步骤并添加提示
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
        self.current_step = WorkflowStep.SET_PERMISSIONS
        update_button_status(self.btn_set_permissions, "In Progress", COLOR_BLUE)
        self.log_message("Setting tool permissions", "BLUE")

        # Run xattr command
        self.run_command(
            f"/usr/bin/xattr -c {TURDUSRA1N_PATH} && /usr/bin/xattr -c {TURDUS_MERULA_PATH} && chmod +x {TURDUSRA1N_PATH} && chmod +x {TURDUS_MERULA_PATH}",
            callback=self._after_set_permissions
        )

    def _after_set_permissions(self, success, _):
        """Callback after setting permissions"""
        if success:
            self.log_message("Tool permissions set successfully", "GREEN")
            update_button_status(self.btn_set_permissions, "Completed", COLOR_GREEN)
        else:
            self.log_message("Failed to set tool permissions", "RED")
            update_button_status(self.btn_set_permissions, "Failed", COLOR_RED)
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

        # Check if there's already a command running
        if self.command_thread and self.command_thread.isRunning():
            QMessageBox.warning(self, "Operation in Progress",
                                "Another operation is currently running. Please wait for it to complete.")
            return

        self.current_operation_button = self.btn_enter_pwnedDFU
        self.current_step = WorkflowStep.ENTER_PWNED_DFU
        update_button_status(self.btn_enter_pwnedDFU, "In Progress", COLOR_BLUE)
        self.log_message("\n===== Entering pwned DFU mode =====", "BLUE")

        # Manual mode, show confirmation dialog
        result = QMessageBox.question(
            self, "Enter DFU Mode",
            "Please make sure your device is connected and in DFU mode.\n\nReady to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if result != QMessageBox.StandardButton.Yes:
            update_button_status(self.btn_enter_pwnedDFU, "Canceled", COLOR_GREY)
            self.current_operation_button = None
            self.update_next_step_highlight()
            return

        cmd = f"{TURDUSRA1N_PATH} -ED"

        self.run_command(
            cmd,
            callback=self._after_enter_pwned_dfu
        )

    def _after_enter_pwned_dfu(self, success, _):
        """Callback after entering pwned DFU mode"""
        if success:
            self.log_message("Successfully entered pwned DFU mode", "GREEN")
            update_button_status(self.btn_enter_pwnedDFU, "Completed", COLOR_GREEN)
            self.btn_get_shcblock.setEnabled(True)
        else:
            self.log_message("Failed to enter pwned DFU mode", "RED")
            update_button_status(self.btn_enter_pwnedDFU, "Failed", COLOR_RED)
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

        # Make sure this step is relevant for the current workflow
        if WorkflowStep.EXTRACT_SHC not in self.workflow.steps:
            QMessageBox.information(self, "Not Needed",
                                    f"SHC block extraction is not needed for {self.workflow.description}.")
            return

        self.current_operation_button = self.btn_get_shcblock
        self.current_step = WorkflowStep.EXTRACT_SHC
        update_button_status(self.btn_get_shcblock, "In Progress", COLOR_BLUE)
        self.log_message("\n===== Extracting SHC block =====", "BLUE")

        # Create working directory for blocks
        block_dir = os.path.join(WORK_DIR, "block")
        os.makedirs(block_dir, exist_ok=True)

        # Run turdus_merula to get shcblock
        cmd = f"{TURDUS_MERULA_PATH} --get-shcblock \"{self.firmware_path}\""
        self.run_command(
            cmd,
            callback=self._after_extract_shcblock
        )

    def _after_extract_shcblock(self, success, _):
        """Callback after extracting SHC block"""
        if not success:
            self.log_message("Failed to extract SHC block", "RED")
            update_button_status(self.btn_get_shcblock, "Failed", COLOR_RED)

            QMessageBox.critical(
                self, "Error",
                "Failed to extract SHC block. Please try again after re-entering Pwned DFU mode."
            )
            self.current_operation_button = None
            return

        # Check if shcblock file was generated
        self.shcblock_path = find_latest_block("shcblock", WORK_DIR)
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
            update_button_status(self.btn_get_shcblock, "Partial", COLOR_YELLOW)
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
        update_button_status(self.btn_get_shcblock, "Completed", COLOR_GREEN)

        # Enable next button
        self.current_operation_button = None

    def reenter_pwned_dfu(self):
        """Re-enter pwned DFU mode for PTE block extraction"""
        # Check if there's already a command running
        if self.command_thread and self.command_thread.isRunning():
            QMessageBox.warning(self, "Operation in Progress",
                                "Another operation is currently running. Please wait for it to complete.")
            return

        # Make sure this step is relevant for the current workflow
        if WorkflowStep.REENTER_DFU_FOR_PTE not in self.workflow.steps:
            QMessageBox.information(self, "Not Needed",
                                    f"This step is not needed for {self.workflow.description}.")
            return

        self.current_step = WorkflowStep.REENTER_DFU_FOR_PTE
        self.prompt_for_dfu_reentry()

    def prompt_for_dfu_reentry(self):
        """Prompt user to re-enter DFU mode"""
        self.current_operation_button = self.btn_enter_pwnedDFU2
        update_button_status(self.btn_enter_pwnedDFU2, "In Progress", COLOR_BLUE)
        self.log_message("\n===== Re-entering pwned DFU mode for PTE block extraction =====", "BLUE")

        # In manual mode, show confirmation dialog
        result = QMessageBox.question(
            self, "Re-enter DFU Mode",
            "Please put your device back in DFU mode after restart.\n\nReady to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if result != QMessageBox.StandardButton.Yes:
            update_button_status(self.btn_enter_pwnedDFU2, "Canceled", COLOR_GREY)
            self.current_operation_button = None
            self.update_next_step_highlight()
            return

        # Run turdusra1n -ED
        self.run_command(
            f"{TURDUSRA1N_PATH} -ED",
            callback=self._after_reenter_pwned_dfu
        )

    def _after_reenter_pwned_dfu(self, success, _):
        """Callback after re-entering pwned DFU mode"""
        if success:
            self.log_message("Successfully re-entered pwned DFU mode", "GREEN")
            update_button_status(self.btn_enter_pwnedDFU2, "Completed", COLOR_GREEN)
            self.btn_get_pteblock.setEnabled(True)
        else:
            self.log_message("Failed to re-enter pwned DFU mode", "RED")
            update_button_status(self.btn_enter_pwnedDFU2, "Failed", COLOR_RED)
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

        # Make sure this step is relevant for the current workflow
        if WorkflowStep.EXTRACT_PTE not in self.workflow.steps:
            QMessageBox.information(self, "Not Needed",
                                    f"PTE block extraction is not needed for {self.workflow.description}.")
            return

        # Check for SHC block, but allow custom path from widget
        custom_shcblock_path = self.shcblock_path_widget.get_path()
        if not self.shcblock_path and not custom_shcblock_path:
            QMessageBox.critical(self, "Error",
                                 "SHC block not found. Please extract the SHC block first or select an SHC block file manually.")
            return

        self.current_operation_button = self.btn_get_pteblock
        self.current_step = WorkflowStep.EXTRACT_PTE
        update_button_status(self.btn_get_pteblock, "In Progress", COLOR_BLUE)
        self.log_message("\n===== Extracting PTE block =====", "BLUE")

        # Get custom SHC block path if user changed it
        if custom_shcblock_path:
            self.shcblock_path = custom_shcblock_path
            self.log_message(f"Using custom SHC block path: {custom_shcblock_path}", "BLUE")

        # Create working directory for blocks
        block_dir = os.path.join(WORK_DIR, "block")
        os.makedirs(block_dir, exist_ok=True)

        # Run turdus_merula to get pteblock
        cmd = f"{TURDUS_MERULA_PATH} --get-pteblock --load-shcblock \"{self.shcblock_path}\" \"{self.firmware_path}\""
        self.run_command(
            cmd,
            callback=self._after_extract_pteblock
        )

    def _after_extract_pteblock(self, success, _):
        """Callback after extracting PTE block"""
        if not success:
            self.log_message("Failed to extract PTE block", "RED")
            update_button_status(self.btn_get_pteblock, "Failed", COLOR_RED)

            QMessageBox.critical(
                self, "Error",
                "Failed to extract PTE block. Please try again after re-entering Pwned DFU mode."
            )
            self.current_operation_button = None
            return

        # Check if pteblock file was generated
        self.pteblock_path = find_latest_block("pteblock", WORK_DIR)
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
            update_button_status(self.btn_get_pteblock, "Partial", COLOR_YELLOW)
            QMessageBox.warning(
                self, "Warning",
                "No PTE block file was found automatically. You can proceed but will need to select a PTE block file manually."
            )
            self.current_operation_button = None
            return

        # Update PTE block path in the UI
        self.pteblock_path_widget.set_path(self.pteblock_path)

        self.log_message(f"Successfully extracted PTE block: {os.path.basename(self.pteblock_path)}", "GREEN")
        update_button_status(self.btn_get_pteblock, "Completed", COLOR_GREEN)

        # Enable next button
        self.current_operation_button = None

    def reenter_pwned_dfu_for_restore(self):
        """Re-enter pwned DFU mode for device restoration"""
        # Check if there's already a command running
        """Enter pwned DFU mode"""
        if not self.firmware_path:
            QMessageBox.critical(self, "Error", "No firmware selected. Please select a firmware file first.")
            return

        # For untethered mode, check if SHSH file exists
        if self.workflow.downgrade_type == DowngradeType.UNTETHERED and not self.shsh_path:
            QMessageBox.critical(self, "Error",
                                 "No SHSH blob selected. Please select an SHSH blob file for untethered downgrade.")
            return

        # Check if there's already a command running
        if self.command_thread and self.command_thread.isRunning():
            QMessageBox.warning(self, "Operation in Progress",
                                "Another operation is currently running. Please wait for it to complete.")
            return

        self.current_operation_button = self.btn_enter_pwnedDFU
        self.current_step = WorkflowStep.ENTER_PWNED_DFU
        update_button_status(self.btn_enter_pwnedDFU, "In Progress", COLOR_BLUE)
        self.log_message("\n===== Entering pwned DFU mode =====", "BLUE")

        # Manual mode, show confirmation dialog
        result = QMessageBox.question(
            self, "Enter DFU Mode",
            "Please make sure your device is connected and in DFU mode.\n\nReady to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if result != QMessageBox.StandardButton.Yes:
            update_button_status(self.btn_enter_pwnedDFU, "Canceled", COLOR_GREY)
            self.current_operation_button = None
            self.update_next_step_highlight()
            return

        # Execute different commands based on workflow
        if self.workflow.downgrade_type == DowngradeType.UNTETHERED:
            # Input generator
            generator, ok = QInputDialog.getText(
                self, "Generator Input",
                "Enter the generator value from your SHSH blob:",
                QLineEdit.EchoMode.Normal
            )

            if not ok or not generator:
                update_button_status(self.btn_enter_pwnedDFU, "Canceled", COLOR_GREY)
                self.current_operation_button = None
                self.update_next_step_highlight()
                return

            self.generator = generator
            cmd = f"{TURDUSRA1N_PATH} -EDb {generator}"
            self.log_message(f"Using generator: {generator}", "BLUE")
        else:
            cmd = f"{TURDUSRA1N_PATH} -ED"

        self.run_command(
            cmd,
            callback=self._after_enter_pwned_dfu
        )

        self.current_step = WorkflowStep.REENTER_DFU_FOR_RESTORE

    def prompt_for_dfu_reentry_restore(self):
        """Prompt user to re-enter DFU mode for restoration"""
        self.current_operation_button = self.btn_enter_pwnedDFU3
        update_button_status(self.btn_enter_pwnedDFU3, "In Progress", COLOR_BLUE)
        self.log_message("\n===== Re-entering pwned DFU mode for device restoration =====", "BLUE")

        # In manual mode, show confirmation dialog
        result = QMessageBox.question(
            self, "Re-enter DFU Mode",
            "Please put your device back in DFU mode to prepare for restoration.\n\nReady to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if result != QMessageBox.StandardButton.Yes:
            update_button_status(self.btn_enter_pwnedDFU3, "Canceled", COLOR_GREY)
            self.current_operation_button = None
            self.update_next_step_highlight()
            return

        # Run turdusra1n -ED
        self.run_command(
            f"{TURDUSRA1N_PATH} -ED",
            callback=self._after_reenter_pwned_dfu_restore
        )

    def _after_reenter_pwned_dfu_restore(self, success, _):
        """Callback after re-entering pwned DFU mode for restoration"""
        if success:
            self.log_message("Successfully re-entered pwned DFU mode, ready for device restoration", "GREEN")
            update_button_status(self.btn_enter_pwnedDFU3, "Completed", COLOR_GREEN)
            self.btn_restore_device.setEnabled(True)
        else:
            self.log_message("Failed to re-enter pwned DFU mode", "RED")
            update_button_status(self.btn_enter_pwnedDFU3, "Failed", COLOR_RED)
            QMessageBox.critical(
                self, "Error",
                "Failed to enter Pwned DFU mode. Please check device connection and try again."
            )

        self.current_operation_button = None

    def restore_device(self):
        """Restore device"""
        if not self.firmware_path:
            QMessageBox.critical(self, "Error", "No firmware selected. Please select a firmware file first.")
            return

        # Check if there's already a command running
        if self.command_thread and self.command_thread.isRunning():
            QMessageBox.warning(self, "Operation in Progress",
                                "Another operation is currently running. Please wait for it to complete.")
            return

        # Check required files based on workflow step
        step_info = self.workflow.steps.get(WorkflowStep.RESTORE_DEVICE)
        if step_info:
            for required_file in step_info.requires_files:
                if required_file == "shsh" and not self.shsh_path:
                    QMessageBox.critical(self, "Error",
                                         "No SHSH blob file selected. Please select an SHSH blob file.")
                    return
                elif required_file == "shcblock":
                    custom_shcblock_path = self.shcblock_path_widget.get_path()
                    if not self.shcblock_path and not custom_shcblock_path:
                        QMessageBox.critical(self, "Error",
                                             "SHC block not found. Please extract SHC block first or select an SHC block file manually.")
                        return
                    # Use the manually selected path if available
                    if custom_shcblock_path:
                        self.shcblock_path = custom_shcblock_path
                elif required_file == "pteblock":
                    custom_pteblock_path = self.pteblock_path_widget.get_path()
                    if not self.pteblock_path and not custom_pteblock_path:
                        QMessageBox.critical(self, "Error",
                                             "PTE block not found. Please extract PTE block first or select a PTE block file manually.")
                        return
                    # Use the manually selected path if available
                    if custom_pteblock_path:
                        self.pteblock_path = custom_pteblock_path

        self.current_operation_button = self.btn_restore_device
        self.current_step = WorkflowStep.RESTORE_DEVICE
        update_button_status(self.btn_restore_device, "In Progress", COLOR_BLUE)
        self.log_message("\n===== Restoring device =====", "BLUE")

        # Get and execute restore command from workflow
        cmd = self.workflow.get_restore_command(
            self.firmware_path,
            self.shsh_path,
            self.shcblock_path,
            self.pteblock_path
        )

        # Log what files are being used
        if self.shsh_path and 'load-shsh' in cmd:
            self.log_message(f"Using SHSH blob: {os.path.basename(self.shsh_path)}", "BLUE")
        if self.shcblock_path and 'load-shcblock' in cmd:
            self.log_message(f"Using SHC block: {os.path.basename(self.shcblock_path)}", "BLUE")
        if self.pteblock_path and 'load-pteblock' in cmd:
            self.log_message(f"Using PTE block: {os.path.basename(self.pteblock_path)}", "BLUE")

        self.run_command(
            cmd,
            callback=self._after_restore_device
        )

    def _after_restore_device(self, success, _):
        """Callback after restoring device"""
        if not success:
            self.log_message("Device restoration failed", "RED")
            update_button_status(self.btn_restore_device, "Failed", COLOR_RED)

            QMessageBox.critical(
                self, "Error",
                "Device restoration failed. Please try again after re-entering Pwned DFU mode."
            )
            self.current_operation_button = None
            return

        self.log_message("Please follow any additional steps shown in the terminal window", "GREEN")
        self.log_message("Device restoration completed successfully", "GREEN")
        update_button_status(self.btn_restore_device, "Completed", COLOR_GREEN)

        # No need to explicitly enable, all buttons are clickable
        self.current_operation_button = None

    def boot_device(self):
        """Boot device"""
        # Check if there's already a command running
        if self.command_thread and self.command_thread.isRunning():
            QMessageBox.warning(self, "Operation in Progress",
                                "Another operation is currently running. Please wait for it to complete.")
            return

        # Check if this step is needed for the current workflow
        if WorkflowStep.BOOT_DEVICE not in self.workflow.steps:
            QMessageBox.information(self, "Not Needed",
                                    f"The device will boot automatically after restoration for {self.workflow.description}.")
            update_button_status(self.btn_boot_device, "Completed", COLOR_GREEN)
            self.current_operation_button = None
            return

        self.current_operation_button = self.btn_boot_device
        self.current_step = WorkflowStep.BOOT_DEVICE
        update_button_status(self.btn_boot_device, "In Progress", COLOR_BLUE)
        self.log_message("\n===== Booting device =====", "BLUE")

        # Check if this is an A9+Tethered or similar workflow requiring PTE block
        step_info = self.workflow.steps.get(WorkflowStep.BOOT_DEVICE)
        if step_info and "pteblock" in step_info.requires_files:
            # Check for PTE block
            custom_pteblock_path = self.pteblock_path_widget.get_path()
            if not self.pteblock_path and not custom_pteblock_path:
                QMessageBox.critical(self, "Error",
                                     "PTE block not found. Please complete device restoration first or select a PTE block file manually.")
                update_button_status(self.btn_boot_device, "Failed", COLOR_RED)
                self.current_operation_button = None
                return

            # Use custom path if provided
            if custom_pteblock_path:
                self.pteblock_path = custom_pteblock_path
                self.log_message(f"Using custom PTE block path: {custom_pteblock_path}", "BLUE")

            # Get boot command from workflow
            cmd = self.workflow.get_boot_command(self.pteblock_path)

        elif isinstance(self.workflow, A10TetheredWorkflow):
            # A10 Tethered needs to find image4 files
            image4_dir = "./image4"
            if not os.path.exists(image4_dir):
                QMessageBox.critical(self, "Error",
                                     "Image4 folder not found. Please check if the restoration operation completed successfully.")
                update_button_status(self.btn_boot_device, "Failed", COLOR_RED)
                self.current_operation_button = None
                return

            # Find required files
            iboot_files = glob.glob(os.path.join(image4_dir, "*iBoot*.img4"))
            sep_signed_files = glob.glob(os.path.join(image4_dir, "*signed-SEP*.img4"))
            sep_target_files = glob.glob(os.path.join(image4_dir, "*target-SEP*.im4p"))

            if not iboot_files or not sep_signed_files or not sep_target_files:
                QMessageBox.critical(self, "Error",
                                     "Required image4 files not found. Please check if the restoration operation completed successfully.")
                update_button_status(self.btn_boot_device, "Failed", COLOR_RED)
                self.current_operation_button = None
                return

            iboot_file = iboot_files[0]
            sep_signed_file = sep_signed_files[0]
            sep_target_file = sep_target_files[0]

            self.log_message(f"Using iBoot file: {os.path.basename(iboot_file)}", "BLUE")
            self.log_message(f"Using signed SEP file: {os.path.basename(sep_signed_file)}", "BLUE")
            self.log_message(f"Using target SEP file: {os.path.basename(sep_target_file)}", "BLUE")

            # Run turdusra1n -t -i -p
            cmd = f"{TURDUSRA1N_PATH} -t \"{iboot_file}\" -i \"{sep_signed_file}\" -p \"{sep_target_file}\""
        else:
            # Default boot command from workflow (should not be None if we got here)
            cmd = self.workflow.get_boot_command()
            if not cmd:
                QMessageBox.information(self, "Information",
                                        f"For {self.workflow.description}, the device will boot automatically after restoration.")
                update_button_status(self.btn_boot_device, "Completed", COLOR_GREEN)
                self.current_operation_button = None
                return

        self.run_command(
            cmd,
            callback=self._after_boot_device
        )

    def _after_boot_device(self, success, _):
        """Callback after booting device"""
        if not success:
            self.log_message("Device boot failed", "RED")
            update_button_status(self.btn_boot_device, "Failed", COLOR_RED)
            QMessageBox.critical(
                self, "Error",
                "Device boot failed. Please check device connection and try again."
            )
        else:
            self.log_message("Device has been successfully booted!", "GREEN")
            update_button_status(self.btn_boot_device, "Completed", COLOR_GREEN)
            QMessageBox.information(
                self, "Success",
                "Device has been successfully booted!\n\nYour device should now be running the restored iOS version."
            )

        self.log_message("\n====== Process completed! ======", "GREEN")
        self.log_message("Your device should now be running the restored iOS version", "GREEN")
        self.current_operation_button = None


def update_workflow_buttons(self):
    """更新当前工作流程中所有按钮的显示和高亮状态"""
    # 先重置所有按钮为基本样式
    for button_index, button in self.button_map.items():
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

    # 如果没有选择固件，提示用户并返回
    if not self.firmware_path:
        self.log_message("Please select a firmware file first", "YELLOW")
        return

    # 如果是非绑定降级但没有SHSH，提示用户并返回
    if self.workflow.downgrade_type == DowngradeType.UNTETHERED and not self.shsh_path:
        self.log_message(f"{self.workflow.description}: Please select an SHSH blob file", "YELLOW")
        return

    # 高亮显示当前工作流所有需要的按钮
    workflow_buttons = []
    for step_info in self.workflow.steps.values():
        if step_info.button_index > 0:  # 跳过没有对应按钮的步骤
            button = self.button_map.get(step_info.button_index)
            if button:
                workflow_buttons.append(button)

                # 如果按钮尚未完成或失败，高亮显示它
                if button.status != "Completed" and button.status != "Failed":
                    highlight_next_step_button(button)

    # 找出需要执行的下一个步骤并添加提示
    self.update_next_step_highlight()  # !/usr/bin/env python3

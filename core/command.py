#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# core/command.py - Command execution functionality

import os
import signal
import subprocess
import sys
import time

from PyQt6.QtCore import QThread, pyqtSignal, QTimer


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

        # Special handling for turdusra1n -ED command, allowing auto-retry
        while (
                self.is_dfu_command and self.dfu_auto_retry_count < self.max_dfu_retries and not success and not self.terminated) or (
                not self.is_dfu_command and not self.terminated):
            if self.is_dfu_command and self.dfu_auto_retry_count > 0:
                self.logOutput.emit(
                    f"Auto-retrying turdusra1n -ED (attempt {self.dfu_auto_retry_count + 1}/{self.max_dfu_retries})...",
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

            # Create DFU command monitoring timer
            if self.is_dfu_command:
                dfu_timer = QTimer()
                dfu_timer.setSingleShot(False)  # Continuous operation
                dfu_timer.timeout.connect(self.check_dfu_output)
                dfu_timer.start(1000)  # Check output status every second

            # Read output
            for line in iter(self.process.stdout.readline, ""):
                if self.terminated:
                    break
                self.logOutput.emit(line, None)  # Regular log, no color
                if self.check_output:
                    output_lines.append(line)

                # Update last output time
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

            # Stop DFU monitoring timer
            if self.is_dfu_command and 'dfu_timer' in locals() and dfu_timer.isActive():
                dfu_timer.stop()

            # Exit the loop if not a DFU command or if DFU command successful
            if not self.is_dfu_command or success:
                break

            # Increment retry count for DFU command failure
            self.dfu_auto_retry_count += 1

            # Exit the loop if maximum retries reached
            if self.dfu_auto_retry_count >= self.max_dfu_retries:
                self.logOutput.emit(f"turdusra1n -ED command failed after {self.max_dfu_retries} attempts", "RED")
                break

        if success and self.check_output:
            output = "".join(output_lines)

        # 确保在线程结束时通知UI，即使被终止
        if self.terminated:
            self.logOutput.emit("Command was terminated by user", "YELLOW")
            success = False

        self.commandComplete.emit(success, output if self.check_output else "")

    def check_dfu_output(self):
        """Check if DFU command has no output for a period and restart if necessary"""
        if not self.is_dfu_command or self.terminated or not self.process:
            return

        current_time = time.time()
        if current_time - self.last_output_time > 5:  # 5 seconds without output
            self.logOutput.emit("turdusra1n -ED command has had no output for 5 seconds, auto-restarting...", "YELLOW")

            # Terminate current process
            self.terminate_process()

            # A new process will be automatically started in the run method

    def terminate_process(self):
        """Terminate current process but not the thread"""
        if self.process:
            try:
                # 更安全的进程终止方法，避免影响父进程
                if sys.platform == "win32":
                    # 在Windows上只终止特定进程，不使用/T参数终止整个树
                    subprocess.run(["taskkill", "/F", "/PID", str(self.process.pid)],
                                   shell=False, capture_output=True)
                else:
                    # 在Unix系统上使用更安全的方法，只终止特定进程
                    # 不使用killpg，因为它可能会终止整个进程组，包括父进程
                    try:
                        self.process.terminate()  # 发送SIGTERM
                        # 给进程一点时间来清理
                        self.process.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        self.process.kill()  # 如果超时，使用SIGKILL强制终止
            except Exception as e:
                self.logOutput.emit(f"Warning: Error terminating process: {str(e)}", "YELLOW")
                # 捕获所有异常，确保不会导致父进程退出
                try:
                    # 最后尝试使用kill()，这是最强制的方式
                    self.process.kill()
                except Exception:
                    # 即使kill失败也不抛出异常
                    pass

    def terminate(self):
        """Terminate command execution"""
        self.terminated = True
        self.terminate_process()
        super().terminate()

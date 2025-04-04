#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# core/workflows.py - Define workflows for different device types and downgrade methods

from dataclasses import dataclass
from typing import List, Dict, Optional, Callable, Tuple
from enum import Enum, auto

from config import TURDUSRA1N_PATH, TURDUS_MERULA_PATH


class CPUType(Enum):
    """CPU types supported by the application"""
    A9 = "A9"
    A10 = "A10"


class DowngradeType(Enum):
    """Downgrade types supported by the application"""
    TETHERED = "tethered"
    UNTETHERED = "untethered"


class WorkflowStep(Enum):
    """Steps in a workflow"""
    SET_PERMISSIONS = auto()
    ENTER_PWNED_DFU = auto()
    EXTRACT_SHC = auto()
    CHECK_SHC = auto()
    REENTER_DFU_FOR_PTE = auto()
    EXTRACT_PTE = auto()
    CHECK_PTE = auto()
    REENTER_DFU_FOR_RESTORE = auto()
    RESTORE_DEVICE = auto()
    BOOT_DEVICE = auto()


@dataclass
class StepInfo:
    """Information about a step in the workflow"""
    step: WorkflowStep
    button_index: int
    description: str
    requires_files: List[str] = None
    next_step: Optional[WorkflowStep] = None

    def __post_init__(self):
        if self.requires_files is None:
            self.requires_files = []


class Workflow:
    """Class representing a device workflow (CPU type + downgrade method)"""

    def __init__(self, cpu_type: CPUType, downgrade_type: DowngradeType):
        self.cpu_type = cpu_type
        self.downgrade_type = downgrade_type
        self.key = f"{cpu_type.value.lower()}_{downgrade_type.value}"
        self.description = f"{cpu_type.value}+{downgrade_type.value} downgrade"
        self.steps: Dict[WorkflowStep, StepInfo] = {}
        self.first_step: Optional[WorkflowStep] = None
        self._init_steps()

    def _init_steps(self):
        """Initialize steps specific to this workflow"""
        # Common first step for all workflows
        self.add_step(
            WorkflowStep.SET_PERMISSIONS,
            1,
            f"{self.cpu_type.value}+{self.downgrade_type.value} downgrade: First set tool permissions",
            next_step=WorkflowStep.ENTER_PWNED_DFU
        )

        self.first_step = WorkflowStep.SET_PERMISSIONS

    def add_step(self, step: WorkflowStep, button_index: int, description: str,
                 requires_files: List[str] = None, next_step: Optional[WorkflowStep] = None):
        """Add a step to the workflow"""
        self.steps[step] = StepInfo(
            step=step,
            button_index=button_index,
            description=description,
            requires_files=requires_files if requires_files else [],
            next_step=next_step
        )

    def get_first_step(self) -> Optional[StepInfo]:
        """Get the first step in the workflow"""
        if self.first_step and self.first_step in self.steps:
            return self.steps[self.first_step]
        return None

    def get_next_step(self, current_step: WorkflowStep) -> Optional[StepInfo]:
        """Get the next step after the current one"""
        if current_step in self.steps and self.steps[current_step].next_step:
            next_step = self.steps[current_step].next_step
            if next_step in self.steps:
                return self.steps[next_step]
        return None

    def get_restore_command(self, firmware_path, shsh_path=None, shcblock_path=None, pteblock_path=None) -> str:
        """Get the command to restore the device based on workflow type"""
        # This should be overridden by subclasses
        return ""

    def get_boot_command(self, pteblock_path=None) -> Optional[str]:
        """Get the command to boot the device based on workflow type"""
        # This should be overridden by subclasses
        return None

    def get_info_message(self) -> str:
        """Get information message about this workflow"""
        return f"Workflow: {self.description}"


class A9TetheredWorkflow(Workflow):
    """A9 + tethered downgrade workflow"""

    def __init__(self):
        super().__init__(CPUType.A9, DowngradeType.TETHERED)
        self.log_message = "A9+tethered workflow: Will guide you to extract SHC, PTE blocks and perform tethered downgrade"
        self.warning_message = "This downgrade method requires computer connection for each boot"

    def _init_steps(self):
        """Initialize A9 + tethered workflow steps"""
        super()._init_steps()

        # Step 2: Enter Pwned DFU
        self.add_step(
            WorkflowStep.ENTER_PWNED_DFU,
            2,
            "A9+tethered downgrade: Enter Pwned DFU mode",
            next_step=WorkflowStep.EXTRACT_SHC
        )

        # Step 3: Extract SHC Block
        self.add_step(
            WorkflowStep.EXTRACT_SHC,
            3,
            "A9+tethered downgrade: Extract SHC Block",
            next_step=WorkflowStep.CHECK_SHC
        )

        # Step 3.5: Check SHC Block (not a button, but a validation step)
        self.add_step(
            WorkflowStep.CHECK_SHC,
            -1,  # No button
            "A9+tethered downgrade: Please select an SHC block file to continue",
            next_step=WorkflowStep.REENTER_DFU_FOR_PTE
        )

        # Step 4: Re-enter Pwned DFU for PTE extraction
        self.add_step(
            WorkflowStep.REENTER_DFU_FOR_PTE,
            4,
            "A9+tethered downgrade: Re-enter Pwned DFU mode to extract PTE Block",
            next_step=WorkflowStep.EXTRACT_PTE
        )

        # Step 5: Extract PTE Block
        self.add_step(
            WorkflowStep.EXTRACT_PTE,
            5,
            "A9+tethered downgrade: Extract PTE Block",
            requires_files=["shcblock"],
            next_step=WorkflowStep.CHECK_PTE
        )

        # Step 5.5: Check PTE Block (not a button, but a validation step)
        self.add_step(
            WorkflowStep.CHECK_PTE,
            -1,  # No button
            "A9+tethered downgrade: Please select a PTE block file to continue",
            next_step=WorkflowStep.REENTER_DFU_FOR_RESTORE
        )

        # Step 6: Re-enter Pwned DFU for device restoration
        self.add_step(
            WorkflowStep.REENTER_DFU_FOR_RESTORE,
            6,
            "A9+tethered downgrade: Re-enter Pwned DFU mode to prepare for device restore",
            next_step=WorkflowStep.RESTORE_DEVICE
        )

        # Step 7: Restore Device
        self.add_step(
            WorkflowStep.RESTORE_DEVICE,
            7,
            "A9+tethered downgrade: Restore device to selected firmware",
            requires_files=["pteblock"],
            next_step=WorkflowStep.BOOT_DEVICE
        )

        # Step 8: Boot Device
        self.add_step(
            WorkflowStep.BOOT_DEVICE,
            8,
            "A9+tethered downgrade: Boot the device",
            requires_files=["pteblock"]
        )

    def get_restore_command(self, firmware_path, shsh_path=None, shcblock_path=None, pteblock_path=None) -> str:
        """Get the restore command for A9 tethered workflow"""
        return f"{TURDUS_MERULA_PATH} -o --load-pteblock \"{pteblock_path}\" \"{firmware_path}\""

    def get_boot_command(self, pteblock_path=None) -> str:
        """Get the boot command for A9 tethered workflow"""
        return f"{TURDUSRA1N_PATH} -TP \"{pteblock_path}\""


class A10TetheredWorkflow(Workflow):
    """A10 + tethered downgrade workflow"""

    def __init__(self):
        super().__init__(CPUType.A10, DowngradeType.TETHERED)
        self.log_message = "A10+tethered workflow: Will directly perform firmware restore and boot operations"
        self.warning_message = "This downgrade method requires computer connection for each boot"

    def _init_steps(self):
        """Initialize A10 + tethered workflow steps"""
        super()._init_steps()

        # Step 2: Enter Pwned DFU
        self.add_step(
            WorkflowStep.ENTER_PWNED_DFU,
            2,
            "A10+tethered downgrade: Enter Pwned DFU mode",
            next_step=WorkflowStep.RESTORE_DEVICE
        )

        # Step 7: Restore Device (Skip several steps compared to A9)
        self.add_step(
            WorkflowStep.RESTORE_DEVICE,
            7,
            "A10+tethered downgrade: Restore device to selected firmware",
            next_step=WorkflowStep.REENTER_DFU_FOR_PTE
        )

        # Step 4: Re-enter Pwned DFU for boot (button 4, but actually 6th step in UI)
        self.add_step(
            WorkflowStep.REENTER_DFU_FOR_PTE,
            4,
            "A10+tethered downgrade: Re-enter Pwned DFU mode to prepare for boot",
            next_step=WorkflowStep.BOOT_DEVICE
        )

        # Step 8: Boot Device
        self.add_step(
            WorkflowStep.BOOT_DEVICE,
            8,
            "A10+tethered downgrade: Boot the device"
        )

    def get_restore_command(self, firmware_path, shsh_path=None, shcblock_path=None, pteblock_path=None) -> str:
        """Get the restore command for A10 tethered workflow"""
        return f"{TURDUS_MERULA_PATH} -o \"{firmware_path}\""

    def get_boot_command(self, pteblock_path=None) -> str:
        """Get the boot command for A10 tethered workflow (requires finding image4 files)"""
        # This is a placeholder - the actual command is built at runtime
        # because it depends on finding the image4 files after restore
        return None


class A9UntetheredWorkflow(Workflow):
    """A9 + untethered downgrade workflow"""

    def __init__(self):
        super().__init__(CPUType.A9, DowngradeType.UNTETHERED)
        self.log_message = "A9+untethered workflow: Will use SHSH blob and SHC block for untethered downgrade"
        self.warning_message = "Please ensure you have selected a valid SHSH blob file"

    def _init_steps(self):
        """Initialize A9 + untethered workflow steps"""
        super()._init_steps()

        # Step 2: Enter Pwned DFU and input Generator
        self.add_step(
            WorkflowStep.ENTER_PWNED_DFU,
            2,
            "A9+untethered downgrade: Enter Pwned DFU mode and input Generator",
            requires_files=["shsh"],
            next_step=WorkflowStep.EXTRACT_SHC
        )

        # Step 3: Extract SHC Block
        self.add_step(
            WorkflowStep.EXTRACT_SHC,
            3,
            "A9+untethered downgrade: Extract SHC Block",
            next_step=WorkflowStep.CHECK_SHC
        )

        # Step 3.5: Check SHC Block (not a button, but a validation step)
        self.add_step(
            WorkflowStep.CHECK_SHC,
            -1,  # No button
            "A9+untethered downgrade: Please select an SHC block file to continue",
            next_step=WorkflowStep.REENTER_DFU_FOR_RESTORE
        )

        # Step 6: Re-enter Pwned DFU for device restoration (using button 4)
        self.add_step(
            WorkflowStep.REENTER_DFU_FOR_RESTORE,
            4,
            "A9+untethered downgrade: Re-enter Pwned DFU mode to prepare for restore",
            next_step=WorkflowStep.RESTORE_DEVICE
        )

        # Step 7: Restore Device
        self.add_step(
            WorkflowStep.RESTORE_DEVICE,
            7,
            "A9+untethered downgrade: Restore device using SHSH and SHC",
            requires_files=["shsh", "shcblock"]
        )

        # No boot step needed for untethered

    def get_restore_command(self, firmware_path, shsh_path=None, shcblock_path=None, pteblock_path=None) -> str:
        """Get the restore command for A9 untethered workflow"""
        return f"{TURDUS_MERULA_PATH} -w --load-shsh \"{shsh_path}\" --load-shcblock \"{shcblock_path}\" \"{firmware_path}\""


class A10UntetheredWorkflow(Workflow):
    """A10 + untethered downgrade workflow"""

    def __init__(self):
        super().__init__(CPUType.A10, DowngradeType.UNTETHERED)
        self.log_message = "A10+untethered workflow: Will use SHSH blob for untethered downgrade"
        self.warning_message = "Please ensure you have selected a valid SHSH blob file"

    def _init_steps(self):
        """Initialize A10 + untethered workflow steps"""
        super()._init_steps()

        # Step 2: Enter Pwned DFU and input Generator
        self.add_step(
            WorkflowStep.ENTER_PWNED_DFU,
            2,
            "A10+untethered downgrade: Enter Pwned DFU mode and input Generator",
            requires_files=["shsh"],
            next_step=WorkflowStep.RESTORE_DEVICE
        )

        # Step 7: Restore Device
        self.add_step(
            WorkflowStep.RESTORE_DEVICE,
            7,
            "A10+untethered downgrade: Restore device using SHSH",
            requires_files=["shsh"]
        )

        # No boot step needed for untethered

    def get_restore_command(self, firmware_path, shsh_path=None, shcblock_path=None, pteblock_path=None) -> str:
        """Get the restore command for A10 untethered workflow"""
        return f"{TURDUS_MERULA_PATH} -w --load-shsh \"{shsh_path}\" \"{firmware_path}\""


# Dictionary of all available workflows
WORKFLOWS = {
    "a9_tethered": A9TetheredWorkflow(),
    "a9_untethered": A9UntetheredWorkflow(),
    "a10_tethered": A10TetheredWorkflow(),
    "a10_untethered": A10UntetheredWorkflow()
}


def get_workflow(cpu_type: str, downgrade_type: str) -> Workflow:
    """Get the appropriate workflow based on CPU type and downgrade method"""
    key = f"{cpu_type.lower()}_{downgrade_type.lower()}"
    return WORKFLOWS.get(key)


def get_workflow_by_key(key: str) -> Optional[Workflow]:
    """Get a workflow by its key"""
    return WORKFLOWS.get(key)

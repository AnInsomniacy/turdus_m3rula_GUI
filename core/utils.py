#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# core/utils.py - Utility functions for core functionality

import glob
import os
import shutil


def find_latest_block(block_type, work_dir):
    """Find the latest block file

    Args:
        block_type (str): Type of block to find (e.g., 'shcblock', 'pteblock')
        work_dir (str): Working directory path

    Returns:
        str or None: Path to the latest block file, or None if not found
    """
    block_dirs = [os.path.join(work_dir, "block"), os.path.join(work_dir, "blocks"), "./block", "./blocks"]
    all_block_files = []

    for blocks_dir in block_dirs:
        if os.path.exists(blocks_dir):
            pattern = f"*-{block_type}.bin"
            block_files = glob.glob(os.path.join(blocks_dir, pattern))
            all_block_files.extend(block_files)

    if not all_block_files:
        return None

    # Sort by modification time
    latest_block = max(all_block_files, key=os.path.getmtime)
    return latest_block


def ensure_directories_exist(work_dir):
    """Ensure necessary directories exist

    Args:
        work_dir (str): Working directory path
    """
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(os.path.join(work_dir, "ipsw"), exist_ok=True)
    os.makedirs(os.path.join(work_dir, "block"), exist_ok=True)


def copy_firmware_to_workdir(source_path, work_dir):
    """Copy firmware file to working directory

    Args:
        source_path (str): Source path of firmware file
        work_dir (str): Working directory path

    Returns:
        str: Path to the copied firmware file

    Raises:
        Exception: If copying fails
    """
    dest_dir = os.path.join(work_dir, "ipsw")
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, os.path.basename(source_path))

    shutil.copy2(source_path, dest_path)
    return dest_path

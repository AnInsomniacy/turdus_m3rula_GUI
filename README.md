# turdus_m3rula_GUI (Currently only for tethered downgrade)

A graphical user interface for the turdus_m3rula iOS device downgrade/restoration tool.

## Overview

turdus_m3rula_GUI provides an easy-to-use interface for restoring and downgrading iOS devices without requiring
command-line knowledge. The application guides users through the complete process with clear instructions and status
updates.
<img width="1236" alt="WechatIMG12139" src="https://github.com/user-attachments/assets/4f10e128-b5f3-4641-8df0-6cebf7913e21" />


## Features

- Simple step-by-step interface for the entire restoration process
- Device detection and DFU mode guidance
- Firmware file selection
- Custom PTE block path support
- Automatic or manual operation modes
- Detailed status logging
- Visual progress indicators

## Requirements

- Compatible iOS device
- macOS (application is designed for macOS)
- Internet connection for firmware downloads (if not provided locally)
- USB connection to device

## Usage

1. Launch the application
2. Select your firmware file (.ipsw)
3. Follow the on-screen instructions to put your device in DFU mode
4. Choose between manual operation (step-by-step) or automatic execution
5. The application will guide you through the entire process

## Advanced Options

- Custom PTE block paths can be specified for advanced users
- Detailed logs show all operations being performed
- Manual mode allows for greater control over the process

## Troubleshooting

If you encounter issues:

- Ensure your device is properly connected
- Verify the firmware file is compatible with your device
- Check the application logs for specific error messages
- Try re-entering DFU mode if operations fail

## Disclaimer

This tool is for educational purposes. Downgrading iOS devices may void warranties and could potentially cause issues
with device functionality. Use at your own risk.

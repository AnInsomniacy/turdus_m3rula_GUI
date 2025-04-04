# Turdus Merula GUI

A graphical user interface for turdus_m3rula, providing an easy-to-use interface for iOS device downgrading operations.
<img width="1236" alt="WechatIMG1866" src="https://github.com/user-attachments/assets/dde6e1bf-1f51-4d93-aaa8-0442ad38abe6" />


## Overview

Turdus Merula GUI is a PyQt-based application that wraps the functionality of turdus_m3rula tools into a user-friendly interface. It supports both A9 and A10 devices with tethered and untethered downgrade options.

> **IMPORTANT:** This GUI is only a wrapper. The core downgrade tool `turdus_m3rula` is NOT included and must be properly set up separately before using this interface. To set up turdus_m3rula:
>
> 1. Download the turdus_m3rula package from its official source
> 2. Place the entire turdus_m3rula folder directly in this project's root directory
> 3. Do not modify the folder structure or rename any components
> 4. Use the "Set Tool Permissions" button within the application to set the correct permissions
>
> The application will expect to find the turdus_m3rula tools at the path: `./turdus_m3rula/bin/`

## Features

- User-friendly graphical interface for iOS device downgrading
- Support for A9(X) and A10(X) devices
- Both tethered and untethered downgrade methods
- Guided workflow with highlighted steps
- Comprehensive logging with export capability
- Clear visualization of the downgrade process

## Requirements

- Python 3.6+
- PyQt6
- macOS (primary support)
- `turdus_m3rula` tools installed and configured

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/turdus_merula_gui.git
cd turdus_merula_gui
```

2. Install the required Python packages:
```bash
pip install PyQt6
```

3. **IMPORTANT**: Setup the turdus_m3rula tools
    - Simply download the turdus_m3rula package and place the **entire folder** directly in the project root directory
    - Do NOT extract or modify the contents of the turdus_m3rula folder - keep its original structure
    - The application expects the following directory structure:
      ```
      ./
      ├── main.py
      ├── config.py
      ├── core/
      ├── gui/
      └── turdus_m3rula/    <-- Place the entire folder here
          └── bin/
              ├── turdusra1n
              └── turdus_merula
      ```
    - The first step in the application will help set the proper permissions for these tools

## Usage

1. Run the application:
```bash
python main.py
```

2. Select your device type (A9 or A10)
3. Choose your downgrade method (Tethered or Untethered)
4. Select the required files when prompted:
    - IPSW firmware
    - SHSH blob (for untethered downgrades)
5. Follow the highlighted steps in order
6. Use the log area to track progress and troubleshoot issues

## Project Structure

```
turdus_merula_gui/
├── main.py                  # Entry point
├── config.py                # Constants and configuration
├── core/                    # Core functionality
│   ├── command.py           # Command execution thread
│   ├── utils.py             # Utility functions
│   └── workflows.py         # Workflow definitions
└── gui/                     # GUI components
    ├── main_window.py       # Main window implementation
    ├── widgets.py           # Custom widgets
    └── utils.py             # GUI utility functions
```

## Troubleshooting

- If you encounter permissions issues, use the "Set Tool Permissions" button
- For detailed logs, use the "Generate Log" button to save logs for debugging
- Make sure your device is properly connected and in DFU mode when prompted
- Check the logs for detailed error messages and guidance

## Contributing

Contributions are welcome! Please feel free to submit pull requests. For major changes, please open an issue first to discuss what you would like to change.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This tool is for educational purposes only. The developers are not responsible for any damage to your devices. Always make sure to have proper backups before attempting to downgrade your iOS device.

## Acknowledgements

- This GUI is just a wrapper for the underlying `turdus_m3rula` tools
- Thanks to the developers of the original turdus_m3rula tools
- Thanks to the checkm8 exploit developers and the iOS jailbreak community

# audio2ogg

A lightweight Windows GUI app for batch-converting audio files to OGG format using ffmpeg. Builds into a single portable `.exe` with ffmpeg bundled inside.

## Features

- Drag and drop audio files into the window
- Add files via dialog
- Select output folder
- Batch convert to `.ogg`
- Conversion log in a separate tab
- Keyboard shortcuts (work on any layout)
- English, Russian, and Chinese UI

## Usage

1. Launch the app
2. Drag audio files into the list or click **Add files** (`Ctrl+O`)
3. Choose an output folder if needed
4. Click **Convert to OGG** (`Ctrl+Enter`)

Converted files are saved in the selected folder with the `.ogg` extension.

## Keyboard Shortcuts

| Shortcut     | Action              |
|--------------|---------------------|
| `Ctrl+O`     | Add files           |
| `Ctrl+A`     | Select all in list  |
| `Delete`     | Remove selected     |
| `Escape`     | Deselect all        |
| `Ctrl+Enter` | Start conversion    |
| `Ctrl+L`     | Clear list          |

## Building

Requirements: Python 3.10+, PowerShell, internet access (for ffmpeg download if not found).

```powershell
.\scripts\build.ps1
```

Or just double-click `build.cmd`.

The script will automatically:
1. Install Python via `winget` if not found
2. Find, copy, or download ffmpeg and embed it into `vendor/ffmpeg.exe`
3. Install Python dependencies
4. Generate the app icon
5. Build `dist\audio2ogg.exe` — a single portable executable

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

ffmpeg must be available in `PATH` or placed at `vendor\ffmpeg.exe`.

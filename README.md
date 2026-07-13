# audio2ogg

<img width="756" height="501" alt="{62AE83B8-306A-44E4-A082-23BED4C2710C}" src="https://github.com/user-attachments/assets/dc7118d1-51f6-4a30-a865-850d1f2b2264" />

Windows GUI app for batch-converting audio files to OGG via ffmpeg. Ships as a single portable `.exe` with ffmpeg bundled inside.

## Usage

1. Drag audio files into the list or press `Ctrl+O`
2. Choose an output folder if needed
3. Press `Ctrl+Enter` to convert

Converted files are saved with the `.ogg` extension in the selected folder.

## Shortcuts

| Key          | Action             |
|--------------|--------------------|
| `Ctrl+O`     | Add files          |
| `Ctrl+A`     | Select all         |
| `Delete`     | Remove selected    |
| `Escape`     | Deselect all       |
| `Ctrl+Enter` | Start conversion   |
| `Ctrl+L`     | Clear list         |

Shortcuts work on any keyboard layout.

## Building

Requires Python 3.10+, PowerShell. Double-click `build.cmd` - the script handles everything automatically (Python install, ffmpeg download, icon generation, packaging).

Output: `build\audio2ogg.exe`

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m source
```

Place `ffmpeg.exe` in `vendor\` or have it available in `PATH`.

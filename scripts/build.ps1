param(
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$vendorDir = Join-Path $projectRoot "vendor"
$cacheDir = Join-Path $projectRoot ".cache"
$ffmpegExe = Join-Path $vendorDir "ffmpeg.exe"

function Test-PythonLauncher {
    param([string]$Launcher)

    if ([string]::IsNullOrWhiteSpace($Launcher)) {
        return $false
    }

    try {
        & $Launcher --version *> $null
        return ($LASTEXITCODE -eq 0)
    }
    catch {
        return $false
    }
}

function Get-PythonLauncher {
    param([string]$Preferred)

    if (-not [string]::IsNullOrWhiteSpace($Preferred)) {
        $preferredCmd = Get-Command $Preferred -ErrorAction SilentlyContinue
        if ($preferredCmd -and (Test-PythonLauncher -Launcher $Preferred)) {
            return $Preferred
        }
        if ((Test-Path $Preferred) -and (Test-PythonLauncher -Launcher $Preferred)) {
            return (Resolve-Path $Preferred).Path
        }
    }

    $candidates = @("py", "python", "python3")
    foreach ($candidate in $candidates) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd -and (Test-PythonLauncher -Launcher $candidate)) {
            return $candidate
        }
    }

    $installedPythons = Get-ChildItem -Path "$env:LocalAppData\Programs\Python" -Filter "python.exe" -Recurse -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending
    foreach ($pythonPath in $installedPythons) {
        if (Test-PythonLauncher -Launcher $pythonPath.FullName) {
            return $pythonPath.FullName
        }
    }

    return ""
}

$PythonExe = Get-PythonLauncher -Preferred $PythonExe

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $winget = Get-Command "winget" -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "Python not found and winget is unavailable. Install Python 3 manually, then rerun the build."
    }

    Write-Host "Python not found. Installing Python 3.12 via winget..."
    & winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements

    $PythonExe = Get-PythonLauncher -Preferred ""
    if ([string]::IsNullOrWhiteSpace($PythonExe)) {
        throw "Python installation finished, but launcher is still unavailable in current session. Reopen PowerShell and rerun build."
    }
}

Write-Host "Using Python launcher: $PythonExe"

New-Item -ItemType Directory -Force -Path $vendorDir | Out-Null
New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null

if (Test-Path $ffmpegExe) {
    Write-Host "Using existing embedded ffmpeg: $ffmpegExe"
}
else {
    $ffmpegCmd = Get-Command "ffmpeg" -ErrorAction SilentlyContinue
    if ($ffmpegCmd -and $ffmpegCmd.Source -and (Test-Path $ffmpegCmd.Source)) {
        Copy-Item -Path $ffmpegCmd.Source -Destination $ffmpegExe -Force
        Write-Host "Found ffmpeg in PATH and embedded it: $($ffmpegCmd.Source)"
    }
}

if (-not (Test-Path $ffmpegExe)) {
    $zipPath = Join-Path $cacheDir "ffmpeg-release-essentials.zip"
    $extractDir = Join-Path $cacheDir "ffmpeg-extracted"
    $ffmpegUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

    Write-Host "Downloading ffmpeg..."
    Invoke-WebRequest -Uri $ffmpegUrl -OutFile $zipPath

    if (Test-Path $extractDir) {
        Remove-Item -Recurse -Force $extractDir
    }

    Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

    $downloadedFfmpeg = Get-ChildItem -Path $extractDir -Recurse -Filter "ffmpeg.exe" |
        Where-Object { $_.FullName -match "\\bin\\ffmpeg.exe$" } |
        Select-Object -First 1

    if (-not $downloadedFfmpeg) {
        throw "ffmpeg.exe not found in downloaded archive."
    }

    Copy-Item -Path $downloadedFfmpeg.FullName -Destination $ffmpegExe -Force
    Write-Host "ffmpeg embedded binary prepared at: $ffmpegExe"
}

if (-not (Test-Path $ffmpegExe)) {
    throw "vendor\ffmpeg.exe not found and download failed."
}

Push-Location $projectRoot
try {
    & $PythonExe -m pip install --upgrade pip
    & $PythonExe -m pip install -r requirements.txt

    $iconArg = @()
    $addIconData = @()
    $pngPath = Join-Path $projectRoot "assets\icon.png"
    $icoPath = Join-Path $projectRoot "assets\icon.ico"

    if (Test-Path $pngPath) {
        Write-Host "Converting icon.png to icon.ico..."
        & $PythonExe -c @"
from PIL import Image
img = Image.open(r'$pngPath').convert('RGBA')
frames = [img.resize((s, s), Image.LANCZOS) for s in [256,128,64,48,32,16]]
frames[0].save(r'$icoPath', format='ICO', append_images=frames[1:])
"@
        $iconArg    = @("--icon", $icoPath)
        $addIconData = @("--add-data", "assets/icon.png;assets", "--add-data", "assets/icon.ico;assets")
        Write-Host "Icon ready."
    }

    & $PythonExe -m PyInstaller `
        --noconfirm `
        --clean `
        --windowed `
        --onefile `
        --name "audio2ogg" `
        --distpath "build" `
        --workpath "_tmp" `
        --add-binary "vendor/ffmpeg.exe;ffmpeg" `
        --add-data "changelog.json;." `
        @addIconData `
        @iconArg `
        --exclude-module unittest `
        --exclude-module pydoc `
        --exclude-module doctest `
        --exclude-module lib2to3 `
        --exclude-module xmlrpc `
        --exclude-module sqlite3 `
        --exclude-module tkinter.test `
        --exclude-module PIL.JpegImagePlugin `
        --exclude-module PIL.TiffImagePlugin `
        --exclude-module PIL.GifImagePlugin `
        --exclude-module PIL.BmpImagePlugin `
        --exclude-module PIL.WebPImagePlugin `
        --exclude-module PIL.IcoImagePlugin `
        run.py
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Build complete:"
Write-Host "build\audio2ogg.exe"

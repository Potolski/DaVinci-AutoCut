@echo off
REM Build a standalone DaVinciAutoCut.exe on Windows (ffmpeg bundled in).
REM Requires Python 3.9+ on PATH. Run from the repo root:  build_windows.bat
setlocal

echo === Installing Python dependencies ===
python -m pip install --upgrade pip || goto :error
python -m pip install -r requirements.txt pyinstaller || goto :error

echo === Downloading ffmpeg ===
if not exist vendor mkdir vendor
if not exist vendor\ffmpeg.exe (
    powershell -NoProfile -Command ^
        "$ErrorActionPreference='Stop';" ^
        "Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile 'ffmpeg.zip';" ^
        "Expand-Archive 'ffmpeg.zip' -DestinationPath 'ffmpeg_dl' -Force;" ^
        "Copy-Item (Get-ChildItem -Recurse 'ffmpeg_dl' -Filter ffmpeg.exe  | Select-Object -First 1).FullName 'vendor\ffmpeg.exe';" ^
        "Copy-Item (Get-ChildItem -Recurse 'ffmpeg_dl' -Filter ffprobe.exe | Select-Object -First 1).FullName 'vendor\ffprobe.exe';" ^
        "Remove-Item 'ffmpeg.zip','ffmpeg_dl' -Recurse -Force" || goto :error
) else (
    echo ffmpeg already present in vendor\, skipping download.
)

echo === Building executable ===
pyinstaller autocut.spec || goto :error

echo.
echo Done. Your standalone app is at: dist\DaVinciAutoCut.exe
goto :eof

:error
echo.
echo Build failed. See the messages above.
exit /b 1

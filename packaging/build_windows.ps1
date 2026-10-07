# Native Windows x86-64 build with PyInstaller (alternative to build_windows_portable.sh).
# Run in PowerShell on Windows from the repo root with Python 3.12 and Node.js 22 available on the BUILD machine only.
$ErrorActionPreference = "Stop"
npm --prefix frontend ci
npm --prefix frontend run build
python -m venv build\venv-win
build\venv-win\Scripts\pip install --quiet -r backend\requirements.txt pyinstaller==6.22.3
build\venv-win\Scripts\pyinstaller --noconfirm --log-level WARN --distpath dist --workpath build\pyinstaller packaging\pyinstaller\fmpoc.spec
Compress-Archive -Force -Path dist\PennyWarden -DestinationPath dist\PennyWarden-windows-x64-pyinstaller.zip
Write-Host "Built dist\PennyWarden-windows-x64-pyinstaller.zip (run PennyWarden.exe)"

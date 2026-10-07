# PyInstaller spec - self-contained onedir build (Linux or Windows; build on the target OS).
# Usage (from repo root, after `npm --prefix frontend run build`):
#   pyinstaller --noconfirm --distpath dist --workpath build/pyinstaller packaging/pyinstaller/fmpoc.spec
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
PKG = os.path.join(ROOT, "backend", "fmpoc")

datas = [
    (os.path.join(PKG, "static"), "fmpoc/static"),
    (os.path.join(PKG, "migrations"), "fmpoc/migrations"),
] + collect_data_files("reportlab")  # fonts used by the audit report
if os.path.isfile(os.path.join(PKG, "build_info.json")):  # v1.4 CR-022 (written by CI)
    datas.append((os.path.join(PKG, "build_info.json"), "fmpoc"))
hidden = (collect_submodules("fmpoc") + collect_submodules("uvicorn") + collect_submodules("alembic")
          + ["sqlalchemy.dialects.sqlite", "argon2", "argon2._password_hasher", "multipart", "python_multipart",
             "PIL.PngImagePlugin", "PIL.JpegImagePlugin", "re2", "re2._re2"] + collect_submodules("reportlab")
          + collect_submodules("pypdf"))

a = Analysis([os.path.join(SPECPATH, "entry.py")], pathex=[os.path.join(ROOT, "backend")], datas=datas,
             hiddenimports=hidden, excludes=["tkinter", "pytest", "PIL.ImageTk", "IPython"], noarchive=False)
pyz = PYZ(a.pure)
NAME = "PennyWarden" if sys.platform.startswith("win") else "pennywarden"  # dist/<NAME>/<NAME>[.exe]
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NAME, console=True, debug=False,
          icon=os.path.join(ROOT, "packaging", "windows", "pennywarden.ico"),
          strip=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name=NAME, strip=False, upx=False)

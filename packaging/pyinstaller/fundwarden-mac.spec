# PyInstaller spec - macOS app bundle (1.6.7): dist/Fundwarden.app for Apple Silicon (arm64).
# Double-click = local mode (127.0.0.1): a small window shows the address, opens the browser and has Quit.
# Data stays in ~/Library/Application Support/Fundwarden, never inside the app.
# Build ON a Mac with Apple Silicon (CI: macos-15) - use packaging/build_macos.sh, which also makes the .dmg.
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
PKG = os.path.join(ROOT, "backend", "fmpoc")
VERSION = os.environ.get("FM_VERSION", "0.0.0")
ICON = os.path.join(ROOT, "packaging", "macos", "fundwarden.icns")

datas = [
    (os.path.join(PKG, "static"), "fmpoc/static"),
    (os.path.join(PKG, "migrations"), "fmpoc/migrations"),
    (os.path.join(ROOT, "LICENSE"), "legal"),
    (os.path.join(ROOT, "THIRD-PARTY-NOTICES.txt"), "legal"),
] + collect_data_files("reportlab")
if os.path.isfile(os.path.join(PKG, "build_info.json")):
    datas.append((os.path.join(PKG, "build_info.json"), "fmpoc"))
hidden = (collect_submodules("fmpoc") + collect_submodules("uvicorn") + collect_submodules("alembic")
          + ["sqlalchemy.dialects.sqlite", "argon2", "argon2._password_hasher", "multipart", "python_multipart",
             "PIL.PngImagePlugin", "PIL.JpegImagePlugin", "re2", "re2._re2"] + collect_submodules("reportlab")
          + collect_submodules("pypdf") + collect_submodules("segno") + ["pyotp", "tkinter", "tkinter.ttk"])

a = Analysis([os.path.join(SPECPATH, "entry_mac.py")], pathex=[os.path.join(ROOT, "backend")], datas=datas,
             hiddenimports=hidden, excludes=["pytest", "PIL.ImageTk", "IPython"], noarchive=False)
pyz = PYZ(a.pure)
# A folder inside the app (not one-file): nothing is unpacked at start, so it opens quickly.
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Fundwarden", console=False, debug=False, strip=False,
          upx=False, target_arch="arm64", argv_emulation=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Fundwarden", strip=False, upx=False)
app = BUNDLE(coll, name="Fundwarden.app", icon=ICON, bundle_identifier="io.github.kretherford0983.fundwarden",
             version=VERSION,
             info_plist={
                 "CFBundleName": "Fundwarden", "CFBundleDisplayName": "Fundwarden",
                 "CFBundleShortVersionString": VERSION, "CFBundleVersion": VERSION,
                 "NSHighResolutionCapable": True, "LSMinimumSystemVersion": "11.0",
                 "LSApplicationCategoryType": "public.app-category.finance",
                 "NSHumanReadableCopyright": "Fundwarden is free software under the GNU AGPL-3.0.",
             })

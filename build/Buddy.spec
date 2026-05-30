# Buddy.spec — PyInstaller build spec for Desktop Pet "Buddy"
# Build with:  pyinstaller build/Buddy.spec --noconfirm
# Output:      dist/Buddy/Buddy.exe  (+ supporting files)

# Use one-folder mode (not one-file) for PyQt6 apps:
#   • startup is ~3x faster (no temp extraction on every launch)
#   • fewer false positives from Windows Defender
#   • smaller download once compressed by the installer

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent.resolve()

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # (source_path_on_disk, destination_inside_bundle)
        (str(ROOT / "assets"),             "assets"),
        (str(ROOT / "config.example.yaml"), "."),
    ],
    hiddenimports=[
        # PyQt6 sub-modules sometimes missed by PyInstaller's hook
        "PyQt6.sip",
        # Win32 sub-modules used by notification_watcher / window
        "win32con",
        "win32gui",
        # sounddevice CFFI back-end
        "_sounddevice_data",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Trim ~150 MB by excluding stuff we don't use
        "tkinter",
        "matplotlib",
        "scipy",
        "pandas",
        "notebook",
        "IPython",
        "pytest",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtMultimediaWidgets",
        "PyQt6.QtPdf",
        "PyQt6.QtPdfWidgets",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Buddy",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,            # UPX often triggers AV — skip
    console=False,        # no terminal window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "tray_icon.png"),
    version=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Buddy",
)

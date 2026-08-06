# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Karyer Local Server (YOLO bilan).
Build: python -m PyInstaller Karyer.spec --noconfirm
Natija: dist/Karyer/Karyer.exe (+ _internal). ffmpeg/ va yolov8n.pt build'dan
keyin dist/Karyer/ yoniga ko'chiriladi (app_dir orqali topiladi)."""

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []

# og'ir paketlar — data/binary/submodullar bilan to'liq yig'iladi
for pkg in ("ultralytics", "torch", "torchvision", "cv2"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:  # noqa: BLE001
        print(f"[spec] collect_all({pkg}) o'tkazildi: {e}")

# local modullar (ba'zilari kech import qilinadi) + seriya/GUI
hiddenimports += [
    "main", "manager", "station", "config", "db", "api_client", "outbox",
    "anpr_listener", "video_recorder", "media", "detector", "provision",
    "tray", "setup_gui", "icons",
    "scale", "scale.base", "scale.serial_driver", "scale.stabilizer",
    "serial", "serial.tools", "serial.tools.list_ports",
    "PIL", "numpy", "requests",
    "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets",
]

a = Analysis(
    ["boshlash.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Karyer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,   # birinchi test — xatolarni ko'rish uchun konsol; keyin False qilamiz
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Karyer",
)

#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║   KARYER LOCAL SERVER — HAMMASINI AVTOMATIK BAJARADI          ║
╚══════════════════════════════════════════════════════════════╝

Faqat shu bitta faylni ishga tushiring (ikki marta bosing yoki
`python boshlash.py`). U o'zi:

  1) Kerakli kutubxonalarni o'rnatadi (yo'q bo'lganlarini)
  2) Windows'da avtomatik ishga tushirishni yoqadi
     (kompyuter yoqilganda dastur o'zi fonda ishlaydi)
  3) Dasturni ishga tushiradi:
       - birinchi marta   -> Sozlash oynasi (parolsiz), keyin fon rejim
       - keyingi safar     -> to'g'ridan-to'g'ri fon (tray) rejim

Sozlamalarni keyin tahrirlash: fon ikonkasi -> "Sozlamalarni tahrirlash"
(parol so'raladi).
"""

import os
# torch (YOLO) barcha yadrolarni olmasin — torch importidan OLDIN (main.py'da ham bor)
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")

import sys
import subprocess
import importlib.util

FROZEN = getattr(sys, "frozen", False)   # PyInstaller .exe ichida ishlayaptimi
BASE = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))

# (import nomi, pip paketi)
CORE_DEPS = [
    ("PyQt6", "PyQt6"),
    ("cv2", "opencv-python"),
    ("requests", "requests"),
    ("serial", "pyserial"),
    ("PIL", "Pillow"),
    ("numpy", "numpy"),
]
# YOLO zona detektori — og'ir (torch bilan), ixtiyoriy
OPTIONAL_DEPS = [("ultralytics", "ultralytics")]


def _have(mod):
    """Modul o'rnatilganmi (import qilmasdan, tez tekshirish)."""
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


def _pip_install(pkg):
    print(f"    📦 o'rnatilmoqda: {pkg} ...")
    for extra in ([], ["--user"]):
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", pkg, "-q"] + extra)
            return True
        except Exception:
            continue
    print(f"    ⚠️ {pkg} o'rnatilmadi — keyin qo'lda: pip install {pkg}")
    return False


def ensure_deps():
    if FROZEN:
        print("[1/3] Frozen (.exe) — kutubxonalar ichida, o'rnatish shart emas")
        return
    print("[1/3] Kutubxonalar tekshirilmoqda...")
    missing = [(m, p) for m, p in CORE_DEPS if not _have(m)]
    if not missing:
        print("    ✅ asosiy kutubxonalar allaqachon bor")
    else:
        for _, pkg in missing:
            _pip_install(pkg)
        print("    ✅ asosiy kutubxonalar tayyor")

    # ixtiyoriy — YOLO (zavodda yo'nalish/video trigger uchun)
    if not _have("ultralytics"):
        print("    ℹ️ YOLO (ultralytics) o'rnatilmoqda — zona detektori uchun.")
        print("       Bu biroz vaqt olishi mumkin; xohlamasangiz Ctrl+C bilan")
        print("       o'tkazib yuboring (dastur YOLOsiz ham ishlaydi).")
        try:
            _pip_install("ultralytics")
        except KeyboardInterrupt:
            print("    (YOLO o'tkazib yuborildi)")


def setup_autostart():
    print("[2/3] Avtomatik ishga tushirish...")
    if not sys.platform.startswith("win"):
        print("    ℹ️ Avtostart faqat Windows'da (bu OS'da o'tkazildi)")
        return
    try:
        startup = os.path.join(os.environ["APPDATA"],
                               r"Microsoft\Windows\Start Menu\Programs\Startup")
        os.makedirs(startup, exist_ok=True)
        vbs = os.path.join(startup, "KaryerServer.vbs")
        if FROZEN:
            # exe'ni to'g'ridan-to'g'ri ishga tushiramiz (Python/boshlash.py yo'q)
            run_cmd = f'"""{sys.executable}"""'
        else:
            pyw = sys.executable
            if pyw.lower().endswith("python.exe"):
                pyw = pyw[:-len("python.exe")] + "pythonw.exe"
            boot = os.path.join(BASE, "boshlash.py")
            run_cmd = f'"""{pyw}"" ""{boot}"""'
        content = (
            'Set sh = CreateObject("WScript.Shell")\r\n'
            f'sh.CurrentDirectory = "{BASE}"\r\n'
            f'sh.Run {run_cmd}, 0, False\r\n'
        )
        with open(vbs, "w", encoding="utf-8") as f:
            f.write(content)
        print("    ✅ Yoqildi — kompyuter yoqilganda dastur o'zi fonda ishlaydi")
    except Exception as e:
        print(f"    ⚠️ Avtostart o'rnatilmadi: {e}")


def launch():
    print("[3/3] Dastur ishga tushmoqda...\n")
    os.chdir(BASE)
    if BASE not in sys.path:
        sys.path.insert(0, BASE)
    import main
    main.main()


if __name__ == "__main__":
    print("=" * 60)
    print("  KARYER LOCAL SERVER — avtomatik o'rnatish va ishga tushirish")
    print("=" * 60)
    ensure_deps()
    setup_autostart()
    launch()

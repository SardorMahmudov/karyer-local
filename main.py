#!/usr/bin/env python3
"""
Karyer Local Server — kirish nuqtasi.

Ishlash:
  python main.py            -> config bo'lsa TRAY (fon) rejimida ishga tushadi;
                               config yo'q bo'lsa Setup GUI ochiladi.
  python main.py --setup    -> Setup GUI ni majburan ochadi (tahrirlash).
  python main.py --console  -> tray'siz, terminalда ishlaydi (Ctrl+C bilan to'xtatish).
  python main.py --sim      -> apparatsiz simulyator (uchidan-uchiga test, konsol).
  python main.py --provision <TOKEN> [URL]
                            -> token bilan serverdan sozlamalarni olib config.json ga yozadi
                               (web-main'dagi kalit tugmasidan olingan token).
"""

import os
# MUHIM: torch/numpy IMPORTIDAN OLDIN — YOLO (torch) default holda barcha
# yadrolarni band qiladi (CPU ~60-70%), video yozish va tizimga xalaqit beradi.
# 4 thread zona-kesish uchun bemalol yetadi. set_num_threads() kech chaqirilsa
# ta'sir qilmaydi, shuning uchun env orqali.
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")

import sys
import time
import socket

import config as cfgmod
from manager import StationManager

# single-instance qulfi (GC bo'lmasligi uchun global saqlanadi)
_instance_sock = None


def _acquire_single_instance():
    """Faqat BITTA nusxa ishlashini ta'minlaydi (localhost port qulfi).

    Ikkinchi nusxa COM8/kameralarni talashadi va hodisalarni IKKILANTIRADI —
    shuning uchun ochilmasa ishga tushirmaymiz. Port jarayon o'lsa OS tomonidan
    avtomatik bo'shaydi (fayl-qulfdan farqli, 'o'lik qulf' muammosi yo'q)."""
    global _instance_sock
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 47653))
        s.listen(1)
        _instance_sock = s
        return True
    except OSError:
        s.close()
        return False


def _force_utf8_output():
    """Konsol chiqishini UTF-8 ga o'tkazadi — dastur emoji chop etadi, Windows
    cp1251 konsolida esa bu UnicodeEncodeError berib oqimlarni yiqitadi.
    tray/pythonw rejimida stdout None bo'lishi mumkin — xatoni yutamiz."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def make_sim_config():
    """--sim uchun tez soxta konfiguratsiya (bitta zavod stansiyasi)."""
    cfg = cfgmod.default_config()
    cfg["quarry_id"] = "SIM-001"
    st = cfgmod.make_zavod_station("zavod-sim")
    st["scale"]["type"] = "sim"
    cfg["stations"] = [st]
    cfg["server"]["enabled"] = False   # yuborilmaydi, faqat outbox'da to'planadi
    return cfg


def run_console(cfg, sim=False):
    """Terminalда ishlaydi — Ctrl+C bilan to'xtatiladi."""
    mgr = StationManager(sim=sim)
    if not mgr.start_all(cfg):
        print("⚠️ Konfiguratsiyada birorta stansiya yo'q. --setup bilan sozlang.")
        return
    print("   To'xtatish: Ctrl+C\n")
    try:
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nTo'xtatilyapti...")
        mgr.stop_all()
        print(f"Yuborilmagan (pending) hodisalar: {mgr.status()['pending']}")


def main():
    _force_utf8_output()
    args = set(sys.argv[1:])

    # 0) Provisioning — token bilan serverdan sozlamalarni olib config.json yozadi
    if "--provision" in args:
        import provision
        provision.run_cli(sys.argv)
        return

    # 1) Simulyator — konsol
    if "--sim" in args:
        print("🧪 SIMULYATOR rejimi — apparatsiz uchidan-uchiga test")
        run_console(make_sim_config(), sim=True)
        return

    # Stansiyalarni ishga tushiradigan rejimlar uchun yagona-nusxa qulfi
    # (--setup/--provision bundan mustasno — ular apparatga tegmaydi).
    if "--setup" not in args and not _acquire_single_instance():
        print("⚠️ Dastur ALLAQACHON ishlayapti (fonda). Ikkinchi nusxa ochilmadi —")
        print("   ikkitasi tarozi/kameralarni talashib hodisalarni ikkilantiradi.")
        print("   Sozlash uchun: Sozlash.bat  |  Holat: Holat.bat")
        return

    cfg = cfgmod.load_config()

    # 2) Birinchi o'rnatish — config yo'q: Setup (parolsiz), keyin tray
    if cfg is None:
        try:
            import setup_gui
            setup_gui.run()                       # birinchi setup — parol yo'q
        except ImportError as e:
            print(f"Setup GUI yuklanmadi ({e}). PyQt6 kerak.")
            return
        if cfgmod.load_config() is None:
            return                                # foydalanuvchi saqlamay yopdi
        # sozlandi — endi fon rejimida ishga tushamiz
        _run_tray_or_console()
        return

    # 3) Tahrirlash (--setup) — parol setup_gui ichida so'raladi
    if "--setup" in args:
        try:
            import setup_gui
            setup_gui.run()
        except ImportError as e:
            print(f"Setup GUI yuklanmadi ({e}).")
        return

    # 4) Konsol rejim (tray'siz)
    if "--console" in args:
        run_console(cfg, sim=False)
        return

    # 5) Default — TRAY (fon) rejim
    _run_tray_or_console()


def _run_tray_or_console():
    """Tray'ni ishga tushiradi; system tray bo'lmasa konsolga tushadi."""
    try:
        import tray
        tray.run()
    except Exception as e:
        print(f"Tray ishga tushmadi ({e}) — konsol rejimga o'tildi.")
        run_console(cfgmod.load_config(), sim=False)


if __name__ == "__main__":
    main()

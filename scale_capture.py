#!/usr/bin/env python3
"""
KELI D12 tarozi — serial (RS-232) XOM MA'LUMOT capture vositasi.

Maqsad: tarozi "PC接口" (DB9, RS-232) porti orqali qanday ma'lumot
yuborayotganini ko'rish. Natijaga qarab aniq parser yoziladi.

Ishlatish (Windows 10/11):
  1. USB-RS232 adapterni (FTDI/CH340) kompyuterga ulang.
  2. Adapterni tarozining "PC接口" (DB9) portiga ulang.
  3. Tarozini yoqing, ustiga biror yuk qo'ying (vazn ko'rinsin).
  4. python scale_capture.py

Skript:
  - barcha COM portlarni ko'rsatadi va tanlashni so'raydi
  - baud tezligini so'raydi (default 9600) yoki "scan" — barcha tezliklarni sinaydi
  - xom baytlarni HEX va ASCII ko'rinishda chiqaradi
  - hammasini scale_capture_log.txt fayliga yozadi

Talab: pip install pyserial
"""

import sys
import os
import time
import datetime

# ---- pyserial ----
try:
    import serial
    from serial.tools import list_ports
except ImportError:
    print("pyserial topilmadi — o'rnatilmoqda...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyserial", "-q"])
    import serial
    from serial.tools import list_ports

# KELI / Xitoy indikatorlarida uchraydigan keng tarqalgan tezliklar
COMMON_BAUDS = [9600, 1200, 2400, 4800, 19200, 38400, 57600, 115200]

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "scale_capture_log.txt")


def list_serial_ports():
    """Mavjud COM portlar ro'yxati."""
    ports = list(list_ports.comports())
    if not ports:
        print("\n❌ Hech qanday COM port topilmadi!")
        print("   - USB-RS232 adapter ulanganmi?")
        print("   - Device Manager -> Ports (COM & LPT) da ko'rinyaptimi?")
        print("   - Drayver o'rnatilganmi (FTDI/CH340)?")
        return []
    print("\nTopilgan COM portlar:")
    for i, p in enumerate(ports):
        print(f"  [{i}] {p.device}  —  {p.description}")
    return ports


def choose_port(ports):
    """Foydalanuvchidan port tanlashni so'raydi."""
    while True:
        raw = input("\nQaysi portni tanlaysiz? (raqam yoki port nomi, masalan COM3): ").strip()
        if not raw:
            continue
        # raqam bilan
        if raw.isdigit():
            idx = int(raw)
            if 0 <= idx < len(ports):
                return ports[idx].device
        # to'g'ridan-to'g'ri nom bilan
        for p in ports:
            if p.device.lower() == raw.lower():
                return p.device
        print("  ! Noto'g'ri tanlov, qayta urinib ko'ring.")


def choose_baud():
    """Baud tezligini tanlash yoki 'scan' rejimi."""
    print("\nBaud tezligi:")
    print("  - Enter bosing -> 9600 (default)")
    print("  - raqam kiriting -> masalan 1200")
    print("  - 'scan' yozing -> barcha tezliklarni ketma-ket sinaydi")
    raw = input("Tanlov: ").strip().lower()
    if raw == "scan":
        return "scan"
    if not raw:
        return 9600
    if raw.isdigit():
        return int(raw)
    return 9600


def log_write(fh, line):
    """Ekranga va faylga bir vaqtda yozish."""
    print(line)
    fh.write(line + "\n")
    fh.flush()


def format_bytes(data):
    """Baytlarni HEX va ASCII ko'rinishda formatlash."""
    hex_part = " ".join(f"{b:02X}" for b in data)
    ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    return hex_part, ascii_part


def capture(port, baud, fh, duration=None):
    """Bitta port+baud dan ma'lumot o'qish.

    duration=None -> Ctrl+C gacha (asosiy rejim)
    duration=N    -> N soniya (scan rejimi uchun)
    Qaytaradi: o'qilgan jami bayt soni.
    """
    total = 0
    try:
        ser = serial.Serial(port, baud, timeout=0.3,
                            bytesize=serial.EIGHTBITS,
                            parity=serial.PARITY_NONE,
                            stopbits=serial.STOPBITS_ONE)
    except Exception as e:
        log_write(fh, f"❌ Port ochilmadi ({port} @ {baud}): {e}")
        return 0

    log_write(fh, f"\n=== {port} @ {baud} 8N1 — o'qish boshlandi ===")
    start = time.monotonic()
    buf = bytearray()
    try:
        while True:
            chunk = ser.read(64)
            if chunk:
                total += len(chunk)
                buf.extend(chunk)
                # \r yoki \n bo'yicha satrlarga ajratib chiqaramiz (o'qishga qulay)
                while b"\n" in buf or b"\r" in buf:
                    # eng yaqin terminatorni topamiz
                    nl = buf.find(b"\n")
                    cr = buf.find(b"\r")
                    idxs = [x for x in (nl, cr) if x != -1]
                    cut = min(idxs) + 1
                    line = bytes(buf[:cut])
                    del buf[:cut]
                    hexp, asc = format_bytes(line)
                    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    log_write(fh, f"[{ts}] LEN={len(line):2d} | HEX: {hexp}")
                    log_write(fh, f"                    | ASCII: {asc!r}")
            else:
                # terminator kelmasa ham, yig'ilib qolган baytlarni ko'rsatamiz
                if buf and (time.monotonic() - start) > 1.5:
                    hexp, asc = format_bytes(bytes(buf))
                    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    log_write(fh, f"[{ts}] LEN={len(buf):2d} | HEX: {hexp}")
                    log_write(fh, f"                    | ASCII: {asc!r}  (terminatorsiz)")
                    buf.clear()

            if duration is not None and (time.monotonic() - start) >= duration:
                break
    except KeyboardInterrupt:
        log_write(fh, "\n⏹  To'xtatildi (Ctrl+C).")
    finally:
        ser.close()

    log_write(fh, f"=== {port} @ {baud}: jami {total} bayt o'qildi ===")
    return total


def scan_all_bauds(port, fh):
    """Har bir baud tezligini ~3 soniya sinaydi va qaysi biri
    o'qiladigan (printable) ma'lumot berishini ko'rsatadi."""
    log_write(fh, "\n🔎 SCAN rejimi — har bir tezlik 3 soniya sinaladi...")
    results = []
    for baud in COMMON_BAUDS:
        got = capture(port, baud, fh, duration=3)
        results.append((baud, got))
        time.sleep(0.2)

    log_write(fh, "\n===== SCAN NATIJASI =====")
    for baud, got in results:
        mark = "✅ ma'lumot bor" if got > 0 else "—  jim"
        log_write(fh, f"  {baud:>7} baud : {got:5d} bayt  {mark}")
    # ma'lumot kelgan tezlikni tavsiya qilamiz
    active = [b for b, g in results if g > 0]
    if active:
        log_write(fh, f"\n👉 Ma'lumot kelgan tezlik(lar): {active}")
        log_write(fh, "   Shu tezlikni tanlab to'liq rejimda qayta ishga tushiring.")
    else:
        log_write(fh, "\n⚠️ Hech qaysi tezlikda ma'lumot kelmadi. Tekshiring:")
        log_write(fh, "   - simlar (RXD/TXD/GND) to'g'ri ulanganmi (null-modem kerakmi?)")
        log_write(fh, "   - tarozida serial 'continuous' rejim yoqilganmi")
        log_write(fh, "   - to'g'ri port tanlanganmi")


def main():
    print("=" * 60)
    print("  KELI D12 — SERIAL XOM MA'LUMOT CAPTURE")
    print("=" * 60)

    ports = list_serial_ports()
    if not ports:
        input("\nEnter bosing va chiqing...")
        return

    port = choose_port(ports)
    baud = choose_baud()

    with open(LOG_FILE, "a", encoding="utf-8") as fh:
        header = f"\n\n########## CAPTURE {datetime.datetime.now():%Y-%m-%d %H:%M:%S} — {port} ##########"
        log_write(fh, header)

        if baud == "scan":
            scan_all_bauds(port, fh)
        else:
            print(f"\n▶ {port} @ {baud} 8N1 o'qilmoqda... (to'xtatish: Ctrl+C)\n")
            capture(port, baud, fh, duration=None)

    print(f"\n💾 Hammasi saqlandi -> {LOG_FILE}")
    print("Shu faylni menga yuboring — aniq parserni yozaman.")


if __name__ == "__main__":
    main()

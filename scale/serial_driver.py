#!/usr/bin/env python3
"""
Serial (RS-232) tarozi drayveri — KELI D12.

DIQQAT: KELI D12 aniq frame formati scale_capture.py natijasidan
qat'iylashtiriladi. Hozircha universal parser: ASCII satrdan birinchi
o'nlik sonni ajratib oladi (masalan '=+00123.4 kg\\r\\n' -> 123.4).
capture natijasi kelgach, _parse_line ni aniq formatga moslashtiramiz.
"""

import re
import time
from .base import ScaleReader, ScaleReading

# ASCII satrdan vazn sonini ajratish (ishora + butun/o'nlik)
_NUM_RE = re.compile(rb"([+-]?\d+(?:\.\d+)?)")


class SerialScaleReader(ScaleReader):
    def _open(self):
        import serial
        # KELI D12 indikatorining o'zida parity sozlanadi (nonE/EvEn/odd).
        # Indikator EvEn (7E1) yuborsa 8N1 bilan o'qish baytlarni buzadi
        # (parity biti 8-bit sifatida o'qiladi) — shuning uchun config'dan:
        #   "bytesize": 7, "parity": "E"   -> 7E1 (KELI zavod holati ko'p uchraydi)
        #   default: 8 / "N"               -> 8N1 (hozirgi ishlab turgan holat)
        bits = {7: serial.SEVENBITS, 8: serial.EIGHTBITS}
        par = {"N": serial.PARITY_NONE, "E": serial.PARITY_EVEN, "O": serial.PARITY_ODD}
        return serial.Serial(
            self.cfg.get("port", "COM3"),
            self.cfg.get("baud", 9600),
            bytesize=bits.get(int(self.cfg.get("bytesize", 8)), serial.EIGHTBITS),
            parity=par.get(str(self.cfg.get("parity", "N")).upper()[:1],
                           serial.PARITY_NONE),
            stopbits=serial.STOPBITS_ONE,
            timeout=0.3,
        )

    def _parse_frame(self, frame: bytes):
        """KELI D12 frame (STX..ETX orasidagi ma'lumot) dan vaznni ajratadi.

        Bu tarozi formati (COM8 capture'dan): '+001180013' =
          belgi(1) + vazn(6 raqam) + o'nlik-pozitsiya(1) + status(2).
        Masalan '+001180013' -> '+', vazn=001180 (=1180), dp=0 -> 1180.0 kg.
        (Boshqa KELI formati chiqsa shu yerni moslashtiramiz.)"""
        s = frame.decode(errors="ignore").strip()
        m = re.match(r"([+-]?)(\d+)", s)
        if not m:
            return None
        sign = -1 if m.group(1) == "-" else 1
        d = m.group(2)
        try:
            if len(d) >= 7:
                w = int(d[:6])
                dp = int(d[6])          # o'nlik xonalar soni
                return sign * w / (10 ** dp)
            return float(sign * int(d))
        except ValueError:
            return None

    # eski newline-asosli parser (zaxira) — hozir STX/ETX ishlatiladi
    def _parse_line(self, line: bytes):
        m = _NUM_RE.search(line)
        if not m:
            return None
        try:
            return float(m.group(1))
        except ValueError:
            return None

    def _run(self):
        buf = bytearray()
        while self._running:
            try:
                ser = self._open()
            except Exception as e:
                print(f"[scale] Port ochilmadi: {e} — 5s dan keyin qayta...")
                time.sleep(5)
                continue

            print(f"[scale] Ulandi: {self.cfg.get('port')} @ {self.cfg.get('baud')} "
                  f"{self.cfg.get('bytesize', 8)}{str(self.cfg.get('parity', 'N')).upper()[:1]}1")
            buf.clear()   # qayta ulanishda eski chala baytlar aralashmasin
            try:
                while self._running:
                    chunk = ser.read(64)
                    if not chunk:
                        continue
                    buf.extend(chunk)
                    # KELI D12: STX(0x02) ... ETX(0x03) bilan freymlanadi (newline yo'q)
                    while b"\x03" in buf:
                        etx = buf.find(b"\x03")
                        stx = buf.rfind(b"\x02", 0, etx)
                        if stx == -1:
                            del buf[:etx + 1]     # STX yo'q — axlatni tashlaymiz
                            continue
                        frame = bytes(buf[stx + 1:etx])
                        del buf[:etx + 1]
                        w = self._parse_frame(frame)
                        if w is not None:
                            self._emit(ScaleReading(w, raw=frame.decode(errors="ignore").strip()))
                    # himoya: STX/ETX kelmasa bufer cheksiz o'smasin
                    if len(buf) > 4096:
                        del buf[:-1024]
            except Exception as e:
                print(f"[scale] O'qish xatosi: {e} — qayta ulanaman...")
                time.sleep(2)
            finally:
                try:
                    ser.close()
                except Exception:
                    pass

#!/usr/bin/env python3
"""Dahua ANPR event-oqimini XOM holda yozib oladi (tashxis uchun).
Rasm (JPEG) qismlari tashlanadi; matnli metama'lumot faqat yoziladi."""
import re
import sys
import time

import requests
from requests.auth import HTTPDigestAuth

IP = sys.argv[1] if len(sys.argv) > 1 else "192.168.100.110"
PW = sys.argv[2] if len(sys.argv) > 2 else "Jizzax321"
SECS = int(sys.argv[3]) if len(sys.argv) > 3 else 90
OUT = "_anpr_capture.txt"

url = (f"http://{IP}/cgi-bin/snapManager.cgi"
       f"?action=attachFileProc&Flags[0]=Event&Events=[All]&heartbeat=5")
out = open(OUT, "w", encoding="utf-8")


def log(s):
    out.write(s + "\n")
    out.flush()


try:
    r = requests.get(url, auth=HTTPDigestAuth("admin", PW), stream=True, timeout=(8, SECS + 10))
    log(f"HTTP {r.status_code} | CT: {r.headers.get('Content-Type')}")
    ctype = r.headers.get("Content-Type", "")
    m = re.search(r"boundary=([^;]+)", ctype)
    boundary = ("--" + m.group(1).strip()).encode() if m else b"--myboundary"
    log(f"boundary: {boundary!r}")
    t0 = time.time()
    buf = b""
    npart = 0
    for chunk in r.iter_content(4096):
        if chunk:
            buf += chunk
            while boundary in buf:
                idx = buf.find(boundary)
                part, buf = buf[:idx], buf[idx + len(boundary):]
                if not part.strip():
                    continue
                npart += 1
                if b"\xff\xd8" in part[:300] or b"image/jpeg" in part[:300].lower():
                    log(f"[#{npart}] <IMAGE {len(part)} bayt>")
                    continue
                txt = part.decode("utf-8", "ignore")
                log(f"[#{npart}] --- text part ---")
                for line in txt.splitlines():
                    line = line.strip()
                    if line and ("=" in line or ":" in line):
                        log("   " + line)
            if len(buf) > 4 * 1024 * 1024:
                buf = buf[-1024 * 1024:]
        if time.time() - t0 > SECS:
            break
    log(f"\n=== TUGADI ({SECS}s, {npart} part) ===")
except Exception as e:
    log(f"XATO: {e!r}")
finally:
    out.close()

#!/usr/bin/env python3
"""
Rasm va video siqish (compress) — yuborishdan oldin hajmni kamaytirish.

Rasm: JPEG sifatini pasaytirish + kenglikni cheklash (cv2 yoki Pillow).
Video: ffmpeg bo'lsa H.264 (CRF) bilan kuchli siqadi (~5-10x kichik);
       ffmpeg bo'lmasa — yozishda o'lcham kichraytiriladi (video_recorder da).
"""

import os
import shutil
import subprocess

from config import app_dir

BASE_DIR = app_dir()


def ffmpeg_exe():
    """ffmpeg.exe joyini topadi (tartib bilan):
      1) KARYER_FFMPEG muhit o'zgaruvchisi
      2) app yonidagi bundlangan nusxa: local/ffmpeg/ffmpeg.exe (yoki .../bin/)
      3) tizim PATH
    Topilmasa None — video H.264 ga o'girilmaydi (brauzer o'ynatmasligi mumkin)."""
    env = os.environ.get("KARYER_FFMPEG")
    if env and os.path.exists(env):
        return env
    for p in (
        os.path.join(BASE_DIR, "ffmpeg", "ffmpeg.exe"),
        os.path.join(BASE_DIR, "ffmpeg", "bin", "ffmpeg.exe"),
        os.path.join(BASE_DIR, "ffmpeg.exe"),
    ):
        if os.path.exists(p):
            return p
    return shutil.which("ffmpeg")


def _cv2():
    try:
        import cv2
        return cv2
    except ImportError:
        return None


# ---------------- RASM ----------------
def compress_image_bytes(data, quality=70, max_width=1280):
    """JPEG baytlarni siqadi. Muvaffaqiyatsiz bo'lsa — asl baytlarni qaytaradi."""
    cv2 = _cv2()
    if cv2 is not None:
        try:
            import numpy as np
            arr = np.frombuffer(data, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is not None:
                h, w = img.shape[:2]
                if w > max_width:
                    nh = int(h * max_width / w)
                    img = cv2.resize(img, (max_width, nh), interpolation=cv2.INTER_AREA)
                ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
                if ok:
                    return enc.tobytes()
        except Exception:
            pass
    # Pillow zaxira
    try:
        import io
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        im = im.convert("RGB")
        if im.width > max_width:
            nh = int(im.height * max_width / im.width)
            im = im.resize((max_width, nh))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=int(quality), optimize=True)
        return buf.getvalue()
    except Exception:
        return data


# ---------------- VIDEO ----------------
def has_ffmpeg():
    return ffmpeg_exe() is not None


def compress_video_file(path, crf=28, max_width=1280, preset="veryfast"):
    """Videoni JOYIDA (in-place) H.264 (avc1) ga o'giradi — brauzerlar aynan
    shuni o'ynaydi. cv2 xom holda mp4v/FMP4 yozadi, uni brauzer O'YNATMAYDI.
    ffmpeg yo'q yoki xato bo'lsa — faylni o'zgartirmaydi (va ogohlantiradi)."""
    if not os.path.exists(path):
        return path
    exe = ffmpeg_exe()
    if not exe:
        print("[media] ⚠️ FFMPEG TOPILMADI — video H.264 ga o'girilmadi. "
              "Brauzer (dashboard) bu videoni O'YNATMAYDI (mp4v/FMP4).\n"
              "        Yeching: ffmpeg o'rnating (PATH) yoki local/ffmpeg/ffmpeg.exe qo'ying.")
        return path
    tmp = path + ".tmp.mp4"
    cmd = [
        exe, "-y", "-i", path,
        "-vcodec", "libx264", "-crf", str(int(crf)), "-preset", preset,
        "-pix_fmt", "yuv420p",       # keng brauzer mosligi (Safari ham)
        "-vf", f"scale='min({int(max_width)},iw)':-2",
        "-an",                       # ovoz kerak emas
        "-movflags", "+faststart",   # moov atom boshda — oqim/tez ochilish
        tmp,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=300)
        if r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
            before = os.path.getsize(path)
            os.replace(tmp, path)
            after = os.path.getsize(path)
            print(f"[media] video siqildi: {before//1024}KB -> {after//1024}KB")
        else:
            if os.path.exists(tmp):
                os.remove(tmp)
    except Exception as e:
        print(f"[media] video siqishda xato: {e}")
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
    return path

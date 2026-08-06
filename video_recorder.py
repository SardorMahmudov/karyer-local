#!/usr/bin/env python3
"""
Video klip yozuvchi — RTSP main stream'dan belgilangan soniya klip yozadi.

record_clip(rtsp_url, duration, out_path, delay) alohida oqimda ishlaydi,
video bloklanmaydi. Natija: mp4 fayl yo'li (yoki None).
"""

import os
import time
import threading
import subprocess

import media

try:
    import cv2
except ImportError:
    cv2 = None


def _vlog(msg):
    """Video yozish tashxisi (video_debug.log). KARYER_VIDEO_DEBUG=0 o'chiradi."""
    if os.environ.get("KARYER_VIDEO_DEBUG", "1") == "0":
        return
    try:
        import datetime
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "video_debug.log")
        if os.path.exists(p) and os.path.getsize(p) > 2 * 1024 * 1024:
            return   # 2MB chegara
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


def record_clip(rtsp_url, out_path, duration=10, delay=0, fps=20, media_cfg=None):
    """RTSP dan klip yozadi. AVVAL FFMPEG (rtsp_transport tcp, to'g'ridan H.264 —
    ishonchli, cv2 ochilmasa ham ishlaydi). ffmpeg yo'q/uzilса — cv2 zaxira.

    MUHIM: yozish avval `.part.mp4` vaqtinchalik faylga boradi, tayyor bo'lgach
    os.replace bilan out_path'ga o'tadi. Shunda out_path FAQAT TO'LIQ video
    bo'lganda mavjud bo'ladi — outbox yarim faylni yuborib yubormaydi va
    hodisani darhol navbatga qo'yish xavfsiz."""
    media_cfg = media_cfg or {}
    if delay > 0:
        time.sleep(delay)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    _vlog(f"START: {os.path.basename(out_path)}")

    exe = media.ffmpeg_exe()
    if exe:
        p = _record_ffmpeg(exe, rtsp_url, out_path, duration, media_cfg)
        if p:
            return p
        _vlog("ffmpeg natija bermadi — cv2 zaxiraga o'tamiz")
    return _record_cv2(rtsp_url, out_path, duration, fps, media_cfg)


def _record_ffmpeg(exe, rtsp_url, out_path, duration, media_cfg):
    """ffmpeg bilan RTSP -> H.264 mp4 (bir bosqichda). cv2'dan farqli — TCP
    transport, kamera SUB oqimni ushlab turса ham MAIN'ni ishonchli ochadi."""
    max_w = int(media_cfg.get("video_max_width", 1280))
    crf = int(media_cfg.get("video_crf", 28))
    tmp = out_path + ".part.mp4"
    cmd = [
        exe, "-y", "-nostdin",
        "-rtsp_transport", "tcp",            # UDP emas — barqaror
        "-i", rtsp_url,
        "-t", str(int(duration)),
        "-an",                               # ovoz kerak emas
        "-c:v", "libx264", "-crf", str(crf), "-preset", "veryfast",
        "-pix_fmt", "yuv420p",               # brauzer mosligi
        "-vf", f"scale='min({max_w},iw)':-2",
        "-movflags", "+faststart",
        tmp,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=duration + 40)
        if r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
            os.replace(tmp, out_path)   # atomik: to'liq video paydo bo'ladi
            _vlog(f"OK (ffmpeg) {os.path.getsize(out_path) // 1024}KB -> {os.path.basename(out_path)}")
            print(f"[video] Klip yozildi (ffmpeg) -> {out_path}")
            return out_path
        err = (r.stderr or b"")[-300:].decode("utf-8", "ignore").strip()
        _vlog(f"FFMPEG XATO rc={r.returncode}: {err[-160:]}")
        return None
    except Exception as e:  # noqa: BLE001
        _vlog(f"FFMPEG istisno: {e}")
        return None
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _record_cv2(rtsp_url, out_path, duration, fps, media_cfg):
    """Zaxira usul: cv2 bilan yozish (ffmpeg topilmaganda). `.part` ga yozib,
    tayyor bo'lgach out_path'ga ko'chiriladi (yarim fayl ko'rinmasin)."""
    if cv2 is None:
        _vlog("cv2 ham yo'q — yozilmadi")
        return None
    cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        _vlog(f"cv2 RTSP OCHILMADI: {os.path.basename(out_path)}")
        return None

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    if not src_fps or src_fps <= 1 or src_fps > 60:
        src_fps = fps

    max_w = int(media_cfg.get("video_max_width", 1280))
    out_w, out_h = w, h
    if w > max_w:
        out_w = max_w
        out_h = int(h * max_w / w)
        out_h -= out_h % 2

    tmp = out_path + ".part.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(tmp, fourcc, src_fps, (out_w, out_h))
    start = time.monotonic()
    frames = 0
    while time.monotonic() - start < duration:
        ret, frame = cap.read()
        if not ret:
            break
        if (out_w, out_h) != (w, h):
            frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_AREA)
        writer.write(frame)
        frames += 1
    cap.release()
    writer.release()

    if frames == 0:
        _vlog(f"cv2 0 KADR: {os.path.basename(out_path)}")
        try:
            os.remove(tmp)
        except OSError:
            pass
        return None
    if media_cfg.get("video_compress", True):
        media.compress_video_file(tmp, crf=media_cfg.get("video_crf", 28), max_width=max_w)
    os.replace(tmp, out_path)
    _vlog(f"OK (cv2) {frames} kadr -> {os.path.basename(out_path)}")
    return out_path


def record_clip_async(rtsp_url, out_path, duration=10, delay=0, on_done=None, media_cfg=None):
    """record_clip ni fon oqimda ishga tushiradi."""
    def _work():
        path = record_clip(rtsp_url, out_path, duration, delay, media_cfg=media_cfg)
        if on_done:
            on_done(path)
    t = threading.Thread(target=_work, name="video-rec", daemon=True)
    t.start()
    return t

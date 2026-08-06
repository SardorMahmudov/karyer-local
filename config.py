#!/usr/bin/env python3
"""
Konfiguratsiya — config.json o'qish/yozish va default qiymatlar.

Bitta dastur bir yoki bir nechta STANSIYA'ni boshqaradi. Har bir stansiya
'kon' (ANPR + video) yoki 'zavod' (ANPR + video + tarozi) rejimida bo'ladi —
farqi faqat tarozida, video/zona mexanizmi ikkalasida bir xil.
"""

import os
import sys
import json


def app_dir():
    """Yozib bo'ladigan ma'lumotlar papkasi (config.json, DB, media, ffmpeg,
    model). Frozen (PyInstaller .exe) bo'lsa — EXE yonida; aks holda skript
    papkasi. Shu bilan bir papkani boshqa kompyuterga ko'chirsa yetadi."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = app_dir()
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

DEFAULT_LOGIN = "admin"
DEFAULT_PASSWORD = "Jizzax321"

# Sozlamalarni TAHRIRLASH uchun parol (birinchi o'rnatishda so'ralmaydi)
EDIT_PASSWORD = "!QAZ"


def config_exists():
    """config.json mavjudmi — ya'ni allaqachon sozlanganmi."""
    return os.path.exists(CONFIG_FILE)


def default_anpr(ip=""):
    return {"brand": "dahua", "ip": ip, "login": DEFAULT_LOGIN, "password": DEFAULT_PASSWORD}


def default_video(ip=""):
    return {"brand": "dahua", "ip": ip, "login": DEFAULT_LOGIN,
            "password": DEFAULT_PASSWORD, "rtsp_main": ""}


def default_scale():
    """Tarozi (KELI D12) va vaznni barqarorlashtirish sozlamalari."""
    return {
        "type": "serial",          # serial | tcp | sim
        "port": "COM3",            # serial uchun
        "baud": 9600,
        "tcp_host": "", "tcp_port": 0,   # tcp uchun
        # --- vazn mantig'i (TZ 4a) ---
        "min_weight": 500,         # mashina bor deb hisoblash chegarasi (kg)
        "settle_time": 3.0,        # barqarorlik uchun kutish (s)
        "stability_tolerance": 20, # ruxsat etilgan tebranish (± kg)
        "division": 10,            # tarozi qadami (kg) — qiymat shunga yaxlitlanadi
        "tie_break": "largest",    # mode teng bo'lsa: largest | smallest | first
        "min_samples": 5,          # barqarorlik uchun minimal o'qishlar soni
    }


def default_capture():
    """Video klip sozlamalari (o'zgartiriladigan)."""
    return {"duration": 10, "delay": 0}   # klip uzunligi (s), boshlanish kechikishi (s)


def default_detector():
    """YOLO zona detektori sozlamalari."""
    return {
        "enabled": True,
        "model": "yolov8n.pt",
        "frame_skip": 4,    # har nechanchi kadr tahlil qilinadi (katta = yengil)
        "imgsz": 640,
        "conf": 0.35,
        "cooldown": 5,      # bitta mashina qayta hisoblanish oralig'i (s)
    }


def default_media():
    """Yuborishdan oldin siqish sozlamalari."""
    return {
        "image_quality": 70,       # JPEG sifati (1-100, past = kichik hajm)
        "image_max_width": 1280,   # rasm kengligi shundan oshsa kichraytiriladi
        "video_compress": True,    # video H.264 ga siqilsinmi (ffmpeg kerak)
        "video_crf": 28,           # H.264 sifat (23=yaxshi, 28=o'rtacha, 32=kichik)
        "video_max_width": 1280,   # video kengligi cheklovi
    }


def default_config():
    return {
        "quarry_id": "",
        "server": {"url": "", "api_key": "", "enabled": False,
                   "endpoint": "/api/weigh", "send_files": True,
                   # send_images=false -> ANPR snapshot rasmlari yuborilmaydi
                   # (video + raqam matni ketadi). Server rasm ingest'ini
                   # tuzatgach (material seed) true qilinadi.
                   "send_images": True},
        "media": default_media(),
        "stations": [],
        # umumiy papkalar
        "save_dir": "captures",
        "video_dir": "videos",
    }


def make_kon_station(name, anpr_ip="", video_ip=""):
    # camera_name — serverga yuboriladi, stansiyalarni shu orqali ajratadi.
    # Video/zona mexanizmi zavod bilan bir xil — faqat tarozi yo'q.
    return {
        "name": name, "mode": "kon", "camera_name": name,
        # is_main — serverga yuboriladigan bayroq (asosiy zavod tarozisimi).
        # kon = false. weight_source — vazn manbai (5-bo'lim): kon'da yo'q.
        "is_main": False,
        "weight_source": "none",   # none | scale | camera
        # kirish/chiqish almashinuvi: shu soatdan keyin qayta "kirish" deb boshlanadi
        "direction_reset_hours": 12,
        "anpr": default_anpr(anpr_ip),
        "video": default_video(video_ip),
        "capture": default_capture(),
        "zone": None,
        "detector": default_detector(),
        "crossing_window": 40.0,  # hodisa bilan zona kirishini bog'lash vaqti (s)
    }


def make_zavod_station(name, anpr_ip="", video_ip="", weight_source="scale"):
    """Asosiy zavod stansiyasi (is_main=true).

    weight_source — vazn qayerdan olinadi:
      - "scale"  : KELI D12 serial tarozi (barqaror vazn hodisani boshlaydi)
      - "camera" : tarozi displayini kamera OCR bilan o'qiydi (2-usul; keyin ulanadi)
      - "none"   : hozircha vazn yo'q — hodisani ANPR raqam boshlaydi, weight=null
    "scale" bo'lmaganda hodisa ANPR raqamdan boshlanadi (tarozisiz), lekin
    serverga is_main=true bilan ketadi.
    """
    st = {
        "name": name, "mode": "zavod", "camera_name": name,
        "is_main": True,
        "weight_source": weight_source,
        "direction_reset_hours": 12,
        "anpr": default_anpr(anpr_ip),
        "video": default_video(video_ip),
        "scale": default_scale(),
        "capture": default_capture(),
        # video kamerada chizilgan ZONA + kirish/chiqish tomonlari (setup GUI da):
        # {"polygon":[[x,y],...], "entry_edge":[[x,y],[x,y]], "exit_edge":[[x,y],[x,y]]}
        # (normalized 0-1). Mashina zonaga kirishi bilan video boshlanadi;
        # qaysi tomondan kirgani yo'nalishni beradi (kirish/chiqish).
        "zone": None,
        "detector": default_detector(),
        "anpr_window": 8.0,     # tarozi hodisasi bilan ANPR raqamni bog'lash vaqti (s)
        "crossing_window": 40.0, # tarozi hodisasi bilan zona kirishini bog'lash vaqti (s)
    }
    return st


def load_config():
    """config.json bo'lsa o'qiydi, aks holda None."""
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"config.json o'qishda xato: {e}")
        return None


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return CONFIG_FILE


def build_rtsp_url(brand, ip, login, password, channel=1, subtype=0):
    """Main stream RTSP havolasi (dahua/hikvision)."""
    if brand == "hikvision":
        stream_id = channel * 100 + (subtype + 1)   # main=..01
        return f"rtsp://{login}:{password}@{ip}:554/Streaming/Channels/{stream_id}"
    # dahua (default)
    return (f"rtsp://{login}:{password}@{ip}:554"
            f"/cam/realmonitor?channel={channel}&subtype={subtype}")

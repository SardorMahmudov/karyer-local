#!/usr/bin/env python3
"""
Provisioning — token bilan avtomatik sozlash (server API.md §9).

Qo'lda quarry_id / api_key ko'chirish o'rniga: web-main'da karyer qatoridagi
kalit tugmasi TOKEN beradi. Local server shu token bilan serverdan o'z
konfiguratsiyasini oladi:

    GET {server}/api/local/config
    Authorization: Bearer <token>

Javob: quarry_id (code), server{url, api_key, endpoint, enabled, send_files}
va ro'yxatga olingan kameralar (camera_name shulardan biriga mos bo'lishi kerak).

Token — JWT: ichida server URL claim'i (`url`) bor, shuning uchun foydalanuvchi
faqat tokenni joylaydi. Bu yerda tokenni TEKSHIRMAYMIZ (imzoni server tekshiradi)
— faqat `url` claim'ini o'qish uchun payload'ni dekodlaymiz.
"""

import sys
import json
import base64

import config as cfgmod

try:
    import requests
except ImportError:
    requests = None


class ProvisionError(Exception):
    """Foydalanuvchiga ko'rsatiladigan tushunarli xato."""


def _jwt_payload(token):
    """JWT o'rta qismini (payload) imzosiz dekodlaydi. Faqat `url` uchun."""
    parts = (token or "").split(".")
    if len(parts) < 2:
        raise ProvisionError("Token formati xato (JWT emas)")
    seg = parts[1]
    seg += "=" * (-len(seg) % 4)   # base64url padding
    try:
        return json.loads(base64.urlsafe_b64decode(seg))
    except Exception as e:
        raise ProvisionError(f"Tokenni o'qib bo'lmadi: {e}")


def server_url_from_token(token):
    """Token ichidagi server URL (`url` claim). Topilmasa bo'sh satr."""
    try:
        return (_jwt_payload(token).get("url") or "").rstrip("/")
    except ProvisionError:
        return ""


def fetch_remote_config(token, server_url=None, timeout=15):
    """Serverdan config'ni oladi. Qaytaradi: dict (quarry_id, server, cameras).

    server_url berilmasa — token ichidagi `url` ishlatiladi.
    Xatoda ProvisionError ko'taradi (tushunarli matn bilan)."""
    if requests is None:
        raise ProvisionError("requests kutubxonasi yo'q (pip install requests)")
    token = (token or "").strip()
    if not token:
        raise ProvisionError("Token bo'sh")

    url = (server_url or "").rstrip("/") or server_url_from_token(token)
    if not url:
        raise ProvisionError(
            "Server URL topilmadi — token ichida yo'q. Server manzilini qo'lda kiriting.")

    endpoint = f"{url}/api/local/config"
    try:
        resp = requests.get(endpoint, headers={"Authorization": f"Bearer {token}"},
                            timeout=timeout)
    except Exception as e:
        raise ProvisionError(f"Serverga ulanib bo'lmadi ({url}): {e}")

    if resp.status_code == 401:
        raise ProvisionError("Token yaroqsiz yoki muddati o'tgan — web-main'dan yangisini oling")
    if resp.status_code == 404:
        raise ProvisionError(f"Karyer topilmadi yoki endpoint yo'q: {endpoint}")
    if resp.status_code != 200:
        raise ProvisionError(f"Server xatosi HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        return resp.json()
    except Exception as e:
        raise ProvisionError(f"Server javobi JSON emas: {e}")


def _set_if(conn, key, value):
    """Faqat serverdan BO'SH BO'LMAGAN qiymat kelsa yozadi — server hali
    to'ldirmagan maydon lokal to'g'ri qiymatni o'chirib yubormasin."""
    if value:
        conn[key] = value


def _merge_camera(station, cam):
    """Bitta server kamerasini stansiyaning ANPR yoki VIDEO blokiga singdiradi.

    plate -> anpr (ANPR HTTP), record -> video (RTSP). MUHIM: faqat server bu
    kamera uchun ulanish ma'lumotini (ip yoki to'liq stream_url) bergan bo'lsa
    yoziladi. Aks holda kamera serverda faqat NOM sifatida ro'yxatda (ip bo'sh,
    brand default 'dahua') — bunda lokal to'g'ri sozlamaga TEGMAYMIZ.
    IP kelgan-u aniq stream_url berilmagan bo'lsa — rtsp_main tozalanadi, shunda
    station uni brand/ip/login/password'dan qayta quradi (config.build_rtsp_url)."""
    ip = (cam.get("ip") or "").strip()
    stream_url = (cam.get("stream_url") or "").strip()
    if not ip and not stream_url:
        return   # server ulanish ma'lumotini bermagan — lokal saqlanadi

    block = "anpr" if cam.get("kind") == "plate" else "video"
    conn = station.setdefault(block, {})
    # server kamera kodi — live-stream so'rovlarini kameraga bog'lash uchun
    _set_if(conn, "code", cam.get("code"))
    _set_if(conn, "brand", cam.get("brand"))
    _set_if(conn, "ip", ip)
    _set_if(conn, "login", cam.get("login"))
    _set_if(conn, "password", cam.get("password"))
    conn.setdefault("login", "admin")
    if block == "video":
        if stream_url:
            conn["rtsp_main"] = stream_url
        elif ip:
            conn["rtsp_main"] = ""   # brand/ip'dan avtomatik quriladi


def _match_station(stations, post_code, claimed):
    """Postga mos MAVJUD stansiyani QAT'IY post_code bo'yicha topadi.

    Allaqachon egallangan (claimed) stansiyani qayta bermaydi — ikki post bir
    xil kamera nomiga ega bo'lsa (masalan ikkalasида ham "raqam"), ular bitta
    stansiyaga tushib bir-birining sozlamasини o'chirib yozmasin. camera_name
    bo'yicha moslashtirish OLIB TASHLANDI (nomlar postlar aro noyob emas)."""
    if not post_code:
        return None
    for s in stations:
        if id(s) not in claimed and s.get("post_code") == post_code:
            return s
    return None


def apply_remote(cfg, remote):
    """Serverdan kelgan config'ni mavjud cfg ustiga qo'yadi (stansiyalar saqlanadi).

    Server kameralari (brand/ip/login/password) mos stansiyaning ANPR/VIDEO
    bloklariga singdiriladi — qo'lda --setup shart emas. Lokalga xos narsalar
    (tarozi, zona, detektor, rejim, weight_source) saqlanadi.

    Qaytaradi: (yangilangan cfg, cameras ro'yxati)."""
    cfg = cfg or cfgmod.default_config()
    cfg["quarry_id"] = remote.get("quarry_id") or cfg.get("quarry_id", "")

    rsrv = remote.get("server") or {}
    srv = cfg.setdefault("server", {})
    srv["url"] = rsrv.get("url") or srv.get("url", "")
    srv["api_key"] = rsrv.get("api_key") or srv.get("api_key", "")
    srv["endpoint"] = rsrv.get("endpoint") or srv.get("endpoint", "/api/weigh")
    srv["enabled"] = bool(rsrv.get("enabled", srv.get("enabled", True)))
    srv["send_files"] = bool(rsrv.get("send_files", srv.get("send_files", True)))

    cfg.setdefault("media", cfgmod.default_media())

    cameras = remote.get("cameras") or []
    _apply_cameras_to_stations(cfg, cameras)
    return cfg, cameras


def _apply_cameras_to_stations(cfg, cameras):
    """Server kameralarini MAVJUD stansiyalarga (qat'iy post_code) singdiradi.

    MUHIM: mos post_code'li stansiya bo'lmasa — stansiya AVTOMATIK YARATILMAYDI.
    Sabab: bir karyerning postlari har xil kompyuterlarda bo'lishi mumkin, va
    bo'sh (ip'siz) stansiya AnprListener'da SIM rejimда SOXTA raqam chiqarib
    yuboradi. Yangi stansiya kerak bo'lsa --setup bilan QO'LDA qo'shiladi. Faqat
    post_code aynan mos kelgan stansiya server credlari (bo'sh bo'lmagan) bilan
    yangilanadi — lokal tarozi/zona/rejim saqlanadi.

    Qaytaradi: mos stansiyasi topilmagan (o'tkazib yuborilgan) post ro'yxati."""
    if not cameras:
        return []
    stations = cfg.get("stations") or []

    # postlar bo'yicha guruhlaymiz (post = stansiya)
    groups, order = {}, []
    for c in cameras:
        key = c.get("post_code") or c.get("post_name") or ""
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(c)

    claimed, skipped = set(), []
    for post_code in order:
        cams = groups[post_code]
        st = _match_station(stations, post_code, claimed)

        # birinchi migratsiya: aynan 1 post + 1 muhrlanmagan (post_code'siz)
        # stansiya bo'lsa — o'shani egallaymiz (eski configlarда post_code yo'q).
        if (st is None and len(order) == 1 and len(stations) == 1
                and not stations[0].get("post_code") and id(stations[0]) not in claimed):
            st = stations[0]

        if st is None:
            # Mos post_code'li stansiya yo'q. Post kameralari IP bilan SOZLANGAN
            # bo'lsa — hamma kamera shu PC' da, demak bu PC shu postни ham
            # boshqaradi -> YANGI alohida kon stansiya (mavjudini clobber qilmaydi;
            # tarozi kerak bo'lsa --setup'да qo'shiladi). IP'siz (sozlanmagan yoki
            # boshqa PC) bo'lsa — TEGMAYMIZ (bo'sh stansiya SIM soxta raqam chiqаradi).
            has_conn = any((c.get("ip") or "").strip() or (c.get("stream_url") or "").strip()
                           for c in cams)
            if not has_conn:
                skipped.append(post_code)
                continue
            post_name = next((c.get("post_name") for c in cams if c.get("post_name")), post_code)
            st = cfgmod.make_kon_station(post_name or post_code)
            stations.append(st)
        claimed.add(id(st))
        st["post_code"] = post_code
        plate = next((c for c in cams if c.get("kind") == "plate"), None)
        record = next((c for c in cams if c.get("kind") == "record"), None)
        # camera_name — stansiya serverga shuni yuboradi. NOM emas, KOD ishlatamiz:
        # nomlar postlar aro takrorlanishi mumkin ("raqam" ikkala postda ham), kod esa
        # noyob (DAHUASBJN/RAQAMHXNP) — server hodisani to'g'ri postga biriktiradi.
        if plate and (plate.get("code") or plate.get("name")):
            st["camera_name"] = plate.get("code") or plate["name"]
        elif record and (record.get("code") or record.get("name")) and not st.get("camera_name"):
            st["camera_name"] = record.get("code") or record["name"]
        for c in cams:
            _merge_camera(st, c)
    return skipped


def provision_and_save(token, server_url=None):
    """To'liq oqim: olib kel -> mavjud config'ga qo'sh -> saqla.

    Qaytaradi: (remote, cfg, cameras, path)."""
    remote = fetch_remote_config(token, server_url)
    cfg = cfgmod.load_config()
    cfg, cameras = apply_remote(cfg, remote)
    path = cfgmod.save_config(cfg)
    return remote, cfg, cameras, path


def _fmt_cameras(cameras):
    if not cameras:
        return "   ⚠️ Bu karyerda hali kamera ro'yxatga olinmagan (web-main'da qo'shing)."
    lines = ["   Ro'yxatdagi kameralar (stansiya camera_name shulardan biriga mos bo'lsin):"]
    for c in cameras:
        lines.append(f"     - {c.get('name')} "
                     f"(code={c.get('code')}, post={c.get('post_name')}, kind={c.get('kind')})")
    return "\n".join(lines)


def run_cli(argv):
    """python main.py --provision <TOKEN> [SERVER_URL]"""
    if "--provision" not in argv:
        return
    idx = argv.index("--provision")
    rest = [a for a in argv[idx + 1:] if not a.startswith("--")]
    token = rest[0] if rest else ""
    server_url = rest[1] if len(rest) > 1 else None
    if not token:
        print("Foydalanish: python main.py --provision <TOKEN> [SERVER_URL]")
        print("  TOKEN — web-main'da karyer qatoridagi kalit tugmasidan olinadi.")
        return

    print("🔑 Serverdan sozlamalar olinmoqda...")
    try:
        remote, cfg, cameras, path = provision_and_save(token, server_url)
    except ProvisionError as e:
        print(f"❌ {e}")
        return

    key = cfg["server"]["api_key"]
    masked = ("•••" + key[-4:]) if key else "(yo'q)"
    print(f"✅ Olindi: {remote.get('quarry_name', '')} [{cfg['quarry_id']}]")
    print(f"   server : {cfg['server']['url']}{cfg['server']['endpoint']}")
    print(f"   api_key: {masked}   | yuborish: {'yoqilgan' if cfg['server']['enabled'] else 'o‘chiq'}")
    print(f"   config : {path}")
    print(_fmt_cameras(cameras))
    print("\n   Keyingi qadam: kamera IP/parol va camera_name'ni sozlang:")
    print("     python main.py --setup")


if __name__ == "__main__":
    run_cli(sys.argv)

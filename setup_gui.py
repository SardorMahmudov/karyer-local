#!/usr/bin/env python3
"""
Setup GUI — bir martalik sozlash oynasi (PyQt6), zamonaviy dizayn.

Bu oyna faqat sozlash uchun ochiladi:
  - quarry_id, server sozlamalari
  - stansiyalar (kon / zavod) qo'shish, tahrirlash, o'chirish
  - har ikkala rejimda: video kamera, klip vaqtlari, ZONA chizish
  - zavod stansiyasida qo'shimcha: tarozi (KELI D12)

Saqlangach dastur fon rejimida `python main.py` bilan ishlaydi.
Talab: pip install PyQt6 opencv-python
"""

import sys
import copy

from PyQt6.QtWidgets import (
    QApplication, QWidget, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QListWidget, QListWidgetItem,
    QDoubleSpinBox, QSpinBox, QCheckBox, QMessageBox, QFrame, QInputDialog,
    QScrollArea, QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, QPoint, QSize, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QPolygon, QFont

import config as cfgmod
from icons import svg_icon, svg_pixmap

# ============================================================
#  DIZAYN TIZIMI (ranglar, uslublar)
# ============================================================
C_BG        = "#F3F5F9"   # oyna foni
C_CARD      = "#FFFFFF"   # kartochka
C_BORDER    = "#E4E8EF"
C_TEXT      = "#0F172A"
C_MUTED     = "#64748B"
C_ACCENT    = "#2563EB"   # asosiy ko'k
C_ACCENT_D  = "#1D4ED8"
C_GREEN     = "#059669"
C_AMBER     = "#D97706"
C_RED       = "#DC2626"

APP_QSS = f"""
* {{ font-family: 'Segoe UI', 'SF Pro Text', Arial, sans-serif; }}

QWidget#root, QDialog {{ background: {C_BG}; }}

/* ---------- kartochka ---------- */
QFrame#card {{
    background: {C_CARD};
    border: 1px solid {C_BORDER};
    border-radius: 14px;
}}
QLabel#cardTitle {{ color: {C_TEXT}; font-size: 15px; font-weight: 700; background: transparent; }}
QLabel#cardHint  {{ color: {C_MUTED}; font-size: 12px; background: transparent; }}
QLabel#h1 {{ color: {C_TEXT}; font-size: 22px; font-weight: 800; background: transparent; }}
QLabel#sub {{ color: {C_MUTED}; font-size: 13px; background: transparent; }}
QLabel#formLabel {{ color: {C_MUTED}; font-size: 12.5px; font-weight: 600; background: transparent; }}
QLabel#sect {{ color: {C_ACCENT}; font-size: 12px; font-weight: 700; letter-spacing: 1px; background: transparent; }}

/* ---------- inputlar ---------- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: #FFFFFF;
    color: {C_TEXT};
    border: 1.5px solid {C_BORDER};
    border-radius: 9px;
    padding: 9px 12px;
    font-size: 13.5px;
    min-height: 20px;
    selection-background-color: {C_ACCENT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1.5px solid {C_ACCENT};
}}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox::down-arrow {{
    image: none; border-left: 5px solid transparent; border-right: 5px solid transparent;
    border-top: 6px solid {C_MUTED}; margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background: #FFFFFF; color: {C_TEXT};
    border: 1px solid {C_BORDER}; border-radius: 8px;
    selection-background-color: #EFF6FF; selection-color: {C_ACCENT_D};
    padding: 4px;
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 22px; border: none; background: transparent; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-bottom: 5px solid {C_MUTED};
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid {C_MUTED};
}}

/* ---------- tugmalar ---------- */
QPushButton {{
    background: #FFFFFF; color: {C_TEXT};
    border: 1.5px solid {C_BORDER}; border-radius: 9px;
    padding: 9px 18px; font-size: 13.5px; font-weight: 600;
}}
QPushButton:hover {{ background: #F8FAFC; border-color: #CBD5E1; }}
QPushButton:pressed {{ background: #EEF2F7; }}

QPushButton#primary {{
    background: {C_ACCENT}; color: white; border: none;
}}
QPushButton#primary:hover {{ background: {C_ACCENT_D}; }}

QPushButton#success {{
    background: {C_GREEN}; color: white; border: none;
}}
QPushButton#success:hover {{ background: #047857; }}

QPushButton#danger {{
    background: transparent; color: {C_RED}; border: 1.5px solid #FECACA;
}}
QPushButton#danger:hover {{ background: #FEF2F2; }}

QPushButton#ghost {{
    background: transparent; border: none; color: {C_ACCENT}; font-weight: 700;
}}
QPushButton#ghost:hover {{ color: {C_ACCENT_D}; }}

/* ---------- checkbox ---------- */
QCheckBox {{ color: {C_TEXT}; font-size: 13.5px; spacing: 10px; background: transparent; }}
QCheckBox::indicator {{
    width: 20px; height: 20px; border-radius: 6px;
    border: 1.5px solid {C_BORDER}; background: white;
}}
QCheckBox::indicator:checked {{
    background: {C_ACCENT}; border-color: {C_ACCENT};
    image: url(none);
}}

/* ---------- ro'yxat ---------- */
QListWidget {{
    background: transparent; border: none; outline: none;
}}
QListWidget::item {{
    background: #FFFFFF; border: 1px solid {C_BORDER};
    border-radius: 12px; margin: 0 0 10px 0; padding: 0;
}}
QListWidget::item:selected {{
    border: 1.5px solid {C_ACCENT}; background: #F5F9FF;
}}
QListWidget::item:hover {{ border-color: #BFD3F2; }}

/* ---------- scroll ---------- */
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #C9D2DE; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #AAB6C6; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

QMessageBox {{ background: {C_CARD}; }}
QMessageBox QLabel {{ color: {C_TEXT}; font-size: 13.5px; }}

/* ---------- pastki panel ---------- */
QFrame#footer {{ background: {C_CARD}; border-top: 1px solid {C_BORDER}; }}
"""


# ============================================================
#  PAROL DIALOGI (tahrirlash uchun)
# ============================================================
class PasswordDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Parol")
        self.setStyleSheet(APP_QSS)
        self.setMinimumWidth(380)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 24, 26, 22)
        lay.setSpacing(14)

        head = QLabel("Sozlamalarni tahrirlash")
        head.setObjectName("h1")
        lay.addWidget(head)
        sub = QLabel("Davom etish uchun parolni kiriting.")
        sub.setObjectName("sub")
        lay.addWidget(sub)

        self.inp = QLineEdit()
        self.inp.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp.setPlaceholderText("parol")
        self.inp.returnPressed.connect(self._ok)
        lay.addWidget(self.inp)

        self.err = QLabel("")
        self.err.setStyleSheet(f"color:{C_RED}; font-size:12.5px; background:transparent;")
        self.err.hide()
        lay.addWidget(self.err)

        row = QHBoxLayout()
        cancel = QPushButton("Bekor")
        cancel.clicked.connect(self.reject)
        ok = QPushButton(" Kirish")
        ok.setIcon(svg_icon("check", "#FFFFFF"))
        ok.setObjectName("primary")
        ok.clicked.connect(self._ok)
        row.addStretch()
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)
        self.inp.setFocus()

    def _ok(self):
        if self.inp.text() == cfgmod.EDIT_PASSWORD:
            self.accept()
        else:
            self.err.setText("❌ Parol noto'g'ri")
            self.err.show()
            self.inp.selectAll()
            self.inp.setFocus()


def check_edit_access(parent=None):
    """Tahrirlashga ruxsat. Birinchi o'rnatish (config yo'q) — parolsiz.
    Aks holda parol so'raladi."""
    if not cfgmod.config_exists():
        return True
    return PasswordDialog(parent).exec() == QDialog.DialogCode.Accepted


def _shadow(widget, blur=24, dy=4, alpha=26):
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setOffset(0, dy)
    eff.setColor(QColor(15, 23, 42, alpha))
    widget.setGraphicsEffect(eff)


def card(title=None, hint=None, icon=None, icon_color=C_ACCENT):
    """Kartochka + ichki layout qaytaradi. icon — SVG ikonka nomi (icons.py)."""
    fr = QFrame()
    fr.setObjectName("card")
    _shadow(fr)
    lay = QVBoxLayout(fr)
    lay.setContentsMargins(20, 18, 20, 18)
    lay.setSpacing(12)
    if title:
        row = QHBoxLayout()
        row.setSpacing(9)
        if icon:
            ic = QLabel()
            ic.setPixmap(svg_pixmap(icon, icon_color, 19))
            ic.setStyleSheet("background: transparent;")
            row.addWidget(ic)
        t = QLabel(title)
        t.setObjectName("cardTitle")
        row.addWidget(t)
        row.addStretch()
        lay.addLayout(row)
    if hint:
        h = QLabel(hint)
        h.setObjectName("cardHint")
        h.setWordWrap(True)
        lay.addWidget(h)
    return fr, lay


def icon_label(name, color, size=16):
    l = QLabel()
    l.setPixmap(svg_pixmap(name, color, size))
    l.setStyleSheet("background: transparent;")
    return l


def form_row(form, label_text, widget):
    lbl = QLabel(label_text)
    lbl.setObjectName("formLabel")
    form.addRow(lbl, widget)


def section_label(text):
    s = QLabel(text.upper())
    s.setObjectName("sect")
    return s


def badge(text, color, bg):
    b = QLabel(text)
    b.setStyleSheet(
        f"background:{bg}; color:{color}; border-radius:9px; padding:3px 10px;"
        f"font-size:11.5px; font-weight:700;")
    return b


# ============================================================
#  ZONA + YO'NALISH CHIZISH DIALOGI
# ============================================================
class ZoneDirectionDialog(QDialog):
    """RTSP kadr ustida ZONA (polygon) chizish + KIRISH/CHIQISH tomonlarini belgilash.

    2 bosqich:
      1) Zona chizish — nuqtalar qo'yib polygon hosil qilinadi (≥3).
      2) Tomonlarni belgilash — zonaning bir tomoni KIRISH (yashil),
         boshqasi CHIQISH (qizil) qilib bosiladi. Strelkalar ikkala
         yo'nalishni ham ko'rsatadi.

    Natija: {"polygon":[[x,y],...], "entry_edge":[[x,y],[x,y]],
             "exit_edge":[[x,y],[x,y]]}  (normalized 0-1).
    """

    CW, CH = 840, 472

    def __init__(self, rtsp_url, zone=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Zona va yo'nalish")
        self.setStyleSheet(APP_QSS)
        self.points = []          # polygon nuqtalari (normalized)
        self.entry_idx = None     # KIRISH tomoni — chekka indeksi (i -> i,i+1)
        self.exit_idx = None      # CHIQISH tomoni
        self.mode = "draw"        # draw | edges
        self.frame_img = None
        if zone and zone.get("polygon"):
            self.points = [tuple(p) for p in zone["polygon"]]
            self.entry_idx = self._match_edge(zone.get("entry_edge"))
            self.exit_idx = self._match_edge(zone.get("exit_edge"))
            self.mode = "edges"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        hrow = QHBoxLayout(); hrow.setSpacing(10)
        hrow.addWidget(icon_label("zone", C_ACCENT, 24))
        head = QLabel("Zona va yo'nalish"); head.setObjectName("h1")
        hrow.addWidget(head); hrow.addStretch()
        lay.addLayout(hrow)

        self.sub = QLabel("")
        self.sub.setObjectName("sub"); self.sub.setWordWrap(True)
        lay.addWidget(self.sub)

        self.canvas = QLabel("Kadr olinmoqda...")
        self.canvas.setMinimumSize(self.CW, self.CH)
        self.canvas.setStyleSheet(
            "background:#0B1220; color:#94A3B8; border-radius:12px; font-size:14px;")
        self.canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas.mousePressEvent = self._on_click
        lay.addWidget(self.canvas)

        btns = QHBoxLayout()
        self.clear_btn = QPushButton(" Tozalash")
        self.clear_btn.setIcon(svg_icon("eraser", C_TEXT))
        self.clear_btn.clicked.connect(self._clear)
        self.step_btn = QPushButton()
        self.step_btn.clicked.connect(self._toggle_mode)
        cancel_btn = QPushButton("Bekor qilish")
        cancel_btn.clicked.connect(self.reject)
        self.ok_btn = QPushButton(" Saqlash")
        self.ok_btn.setIcon(svg_icon("check", "#FFFFFF"))
        self.ok_btn.setObjectName("primary")
        self.ok_btn.setMinimumWidth(140)
        self.ok_btn.clicked.connect(self._save)
        btns.addWidget(self.clear_btn)
        btns.addWidget(self.step_btn)
        btns.addStretch()
        btns.addWidget(cancel_btn)
        btns.addWidget(self.ok_btn)
        lay.addLayout(btns)

        self._grab_frame(rtsp_url)
        self._sync_ui()
        self._redraw()

    # ---- yordamchilar ----
    def _match_edge(self, edge):
        """Saqlangan chekka (ikki nuqta) qaysi polygon chekkasiga mos — indeks."""
        if not edge:
            return None
        n = len(self.points)
        for i in range(n):
            a, b = self.points[i], self.points[(i + 1) % n]
            e0, e1 = tuple(edge[0]), tuple(edge[1])
            if (a, b) == (e0, e1) or (a, b) == (e1, e0):
                return i
        return None

    def _centroid(self):
        xs = [p[0] for p in self.points]; ys = [p[1] for p in self.points]
        return sum(xs) / len(xs), sum(ys) / len(ys)

    def _nearest_edge(self, x, y):
        """Bosilgan nuqtaga eng yaqin polygon chekkasi indeksi."""
        n = len(self.points)
        best, best_d = None, 1e9
        for i in range(n):
            ax, ay = self.points[i]
            bx, by = self.points[(i + 1) % n]
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy or 1e-9
            t = max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / L2))
            cx, cy = ax + t * dx, ay + t * dy
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            if d < best_d:
                best, best_d = i, d
        return best

    def _grab_frame(self, rtsp_url):
        try:
            import cv2
            cap = cv2.VideoCapture(rtsp_url)
            ok, frame = cap.read()
            cap.release()
            if ok:
                frame = cv2.resize(frame, (self.CW, self.CH))
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame.shape
                self.frame_img = QImage(frame.data, w, h, ch * w,
                                        QImage.Format.Format_RGB888).copy()
                return
        except Exception as e:
            print(f"Kadr olishda xato: {e}")
        QMessageBox.warning(self, "Kamera",
                            "Kameradan kadr olinmadi — bo'sh fonda chizasiz.")

    # ---- interaksiya ----
    def _on_click(self, ev):
        x = ev.position().x() / self.canvas.width()
        y = ev.position().y() / self.canvas.height()
        if self.mode == "draw":
            if ev.button() == Qt.MouseButton.LeftButton:
                self.points.append((round(x, 4), round(y, 4)))
            elif ev.button() == Qt.MouseButton.RightButton and self.points:
                self.points.pop()
        else:  # edges — chekkani bosib KIRISH/CHIQISH belgilash
            if ev.button() == Qt.MouseButton.LeftButton and len(self.points) >= 3:
                idx = self._nearest_edge(x, y)
                if idx == self.entry_idx:
                    self.entry_idx = None
                elif idx == self.exit_idx:
                    self.exit_idx = None
                elif self.entry_idx is None:
                    self.entry_idx = idx
                elif self.exit_idx is None:
                    self.exit_idx = idx
                else:  # ikkalasi to'lgan — eng eskisini almashtiramiz (entry)
                    self.entry_idx = idx
        self._redraw()

    def _clear(self):
        if self.mode == "draw":
            self.points = []
        self.entry_idx = self.exit_idx = None
        self._redraw()

    def _toggle_mode(self):
        if self.mode == "draw":
            if len(self.points) < 3:
                QMessageBox.warning(self, "Zona", "Kamida 3 nuqta bilan zona chizing!")
                return
            self.mode = "edges"
        else:
            self.mode = "draw"
        self._sync_ui()
        self._redraw()

    def _sync_ui(self):
        if self.mode == "draw":
            self.sub.setText("1-bosqich: ZONA chizing.  Chap tugma — nuqta qo'shish   •   "
                             "O'ng tugma — oxirgisini o'chirish   •   Kamida 3 nuqta.")
            self.step_btn.setText(" Tomonlarni belgilash →")
            self.step_btn.setIcon(svg_icon("arrow-in", C_TEXT))
            self.step_btn.setObjectName("success")
        else:
            self.sub.setText("2-bosqich: zonaning KIRISH tomonini (yashil), so'ng "
                             "CHIQISH tomonini (qizil) bosing.  Qayta bosish — bekor qiladi.")
            self.step_btn.setText(" ← Zonani tahrirlash")
            self.step_btn.setIcon(svg_icon("pencil", C_TEXT))
            self.step_btn.setObjectName("")
        self.step_btn.setStyleSheet(self.step_btn.styleSheet())  # refresh
        self.setStyleSheet(APP_QSS)

    # ---- chizish ----
    def _draw_arrow(self, painter, mx, my, dirx, diry, color, label):
        import math
        L = max((dirx * dirx + diry * diry) ** 0.5, 1e-6)
        ux, uy = dirx / L, diry / L
        ax, ay = mx + ux * 62, my + uy * 62
        painter.setPen(QPen(QColor(color), 4))
        painter.drawLine(QPoint(int(mx), int(my)), QPoint(int(ax), int(ay)))
        ang = math.atan2(ay - my, ax - mx)
        for da in (math.radians(150), -math.radians(150)):
            hx = ax + 15 * math.cos(ang + da)
            hy = ay + 15 * math.sin(ang + da)
            painter.drawLine(QPoint(int(ax), int(ay)), QPoint(int(hx), int(hy)))
        painter.setPen(QPen(QColor(color), 1))
        f = painter.font(); f.setBold(True); f.setPointSize(12); painter.setFont(f)
        painter.drawText(QPoint(int(ax + 8), int(ay + 4)), label)

    def _redraw(self):
        w, h = self.canvas.width() or self.CW, self.canvas.height() or self.CH
        if self.frame_img:
            pix = QPixmap.fromImage(self.frame_img).scaled(w, h)
        else:
            pix = QPixmap(w, h); pix.fill(QColor("#0B1220"))
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pts = [QPoint(int(px * w), int(py * h)) for px, py in self.points]
        n = len(pts)

        # zona to'ldirish + chekkalar
        if n >= 3:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(34, 211, 238, 45))
            painter.drawPolygon(QPolygon(pts))
        # har chekkani alohida chizamiz (kirish/chiqish rangli)
        for i in range(n):
            a = pts[i]; b = pts[(i + 1) % n]
            if n < 2:
                break
            if i == self.entry_idx:
                painter.setPen(QPen(QColor("#34D399"), 6))       # yashil = KIRISH
            elif i == self.exit_idx:
                painter.setPen(QPen(QColor("#F87171"), 6))       # qizil = CHIQISH
            else:
                painter.setPen(QPen(QColor("#22D3EE"), 3))
            if n >= 3 or i < n - 1:
                painter.drawLine(a, b)
        # nuqtalar
        for i, p in enumerate(pts):
            painter.setBrush(QColor("#22D3EE"))
            painter.setPen(QPen(QColor("#FFFFFF"), 2))
            painter.drawEllipse(p, 6, 6)

        # yo'nalish strelkalari (markazga nisbatan)
        if n >= 3:
            cx, cy = self._centroid()
            for idx, color, label, inward in (
                    (self.entry_idx, "#34D399", "KIRISH", True),
                    (self.exit_idx, "#F87171", "CHIQISH", False)):
                if idx is None:
                    continue
                ax_, ay_ = self.points[idx]
                bx_, by_ = self.points[(idx + 1) % n]
                mx, my = (ax_ + bx_) / 2 * w, (ay_ + by_) / 2 * h
                # markaz tomon (ichkari) yo'nalish
                inx, iny = (cx - (ax_ + bx_) / 2), (cy - (ay_ + by_) / 2)
                if not inward:      # CHIQISH — tashqariga
                    inx, iny = -inx, -iny
                self._draw_arrow(painter, mx, my, inx * w, iny * h, color, label)

        # holat matni
        ready = n >= 3 and self.entry_idx is not None and self.exit_idx is not None
        if self.mode == "draw":
            status = f"  Zona: {n} nuqta" + ("  ✓" if n >= 3 else "  (kamida 3)")
        elif ready:
            status = "  Tayyor ✓ — yashil KIRISH, qizil CHIQISH"
        else:
            need = []
            if self.entry_idx is None: need.append("KIRISH")
            if self.exit_idx is None: need.append("CHIQISH")
            status = "  Tomonni bosing: " + " va ".join(need)
        painter.setPen(QPen(QColor("#E2E8F0")))
        f = painter.font(); f.setBold(True); f.setPointSize(11); painter.setFont(f)
        painter.fillRect(0, pix.height() - 30, pix.width(), 30, QColor(11, 18, 32, 170))
        painter.drawText(10, pix.height() - 10, status)
        painter.end()
        self.canvas.setPixmap(pix)

    def _save(self):
        if len(self.points) < 3:
            QMessageBox.warning(self, "Zona", "Kamida 3 nuqta bilan zona chizing!")
            return
        if self.entry_idx is None or self.exit_idx is None:
            QMessageBox.warning(self, "Yo'nalish",
                                "KIRISH va CHIQISH tomonlarini belgilang!\n"
                                "«Tomonlarni belgilash →» tugmasidan foydalaning.")
            return
        self.accept()

    def _edge_points(self, idx):
        n = len(self.points)
        return [list(self.points[idx]), list(self.points[(idx + 1) % n])]

    def get_zone(self):
        return {
            "polygon": [list(p) for p in self.points],
            "entry_edge": self._edge_points(self.entry_idx),
            "exit_edge": self._edge_points(self.exit_idx),
        }


# ============================================================
#  STANSIYA TAHRIRLASH DIALOGI
# ============================================================
class StationDialog(QDialog):
    def __init__(self, station_cfg, parent=None):
        super().__init__(parent)
        self.st = copy.deepcopy(station_cfg)
        mode = self.st.get("mode", "kon")
        self.setWindowTitle("Stansiya sozlamalari")
        self.setWindowIcon(svg_icon("factory" if mode == "zavod" else "mountain", C_ACCENT))
        self.setStyleSheet(APP_QSS)
        self.setMinimumWidth(620)
        self.setMinimumHeight(640)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # scroll ichida kontent
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("root")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(24, 22, 24, 12)
        lay.setSpacing(14)

        # sarlavha
        hrow = QHBoxLayout()
        hrow.setSpacing(10)
        self.head_icon = icon_label("factory" if mode == "zavod" else "mountain", C_ACCENT, 24)
        hrow.addWidget(self.head_icon)
        head = QLabel(self.st.get("name", "Yangi stansiya"))
        head.setObjectName("h1")
        hrow.addWidget(head)
        hrow.addStretch()
        lay.addLayout(hrow)
        sub = QLabel("Zavod — tarozi + video + ANPR birga ishlaydi.  Kon — video + ANPR (tarozisiz).  "
                     "Bitta darvozadan kirish ham chiqish ham bo'ladi — yo'nalish avtomatik aniqlanadi.")
        sub.setObjectName("sub")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        # ---- UMUMIY kartochka ----
        c1, l1 = card("Umumiy", icon="settings")
        f0 = QFormLayout()
        f0.setSpacing(10)
        self.name_in = QLineEdit(self.st.get("name", ""))
        self.name_in.setPlaceholderText("masalan: zavod-1")
        self.cam_in = QLineEdit(self.st.get("camera_name") or self.st.get("name", ""))
        self.cam_in.setPlaceholderText("serverga yuboriladigan nom, masalan: ZAVOD-KIRISH")
        self.mode_cb = QComboBox()
        self.mode_cb.addItem(svg_icon("factory", C_TEXT), "  Zavod — tarozi bilan (asosiy)", "zavod")
        self.mode_cb.addItem(svg_icon("mountain", C_TEXT), "  Kon — ANPR + video (tarozisiz)", "kon")
        self.mode_cb.setCurrentIndex(0 if mode == "zavod" else 1)
        self.mode_cb.currentIndexChanged.connect(self._mode_changed)
        self.dir_reset = QSpinBox()
        self.dir_reset.setRange(1, 48)
        self.dir_reset.setSuffix(" soat")
        self.dir_reset.setValue(int(self.st.get("direction_reset_hours", 12)))
        self.dir_reset.setToolTip(
            "Mashina kirgach shu muddat ichida qayta ko'rinsa — CHIQISH deb belgilanadi.\n"
            "Muddat o'tib ketsa — yana KIRISH deb hisoblanadi.")
        form_row(f0, "Stansiya nomi", self.name_in)
        form_row(f0, "Kamera nomi (serverga)", self.cam_in)
        form_row(f0, "Rejim", self.mode_cb)
        form_row(f0, "Kirish/chiqish qayta hisobi", self.dir_reset)
        l1.addLayout(f0)
        lay.addWidget(c1)

        # ---- ANPR kartochka ----
        c2, l2 = card("ANPR kamera", "Mashina raqamini o'qiydigan kamera", icon="camera")
        f1 = QFormLayout()
        f1.setSpacing(10)
        a = self.st.setdefault("anpr", cfgmod.default_anpr())
        self.a_brand = QComboBox(); self.a_brand.addItems(["dahua", "hikvision"])
        self.a_brand.setCurrentText(a.get("brand", "dahua"))
        self.a_ip = QLineEdit(a.get("ip", "")); self.a_ip.setPlaceholderText("192.168.1.10")
        self.a_login = QLineEdit(a.get("login", cfgmod.DEFAULT_LOGIN))
        self.a_pass = QLineEdit(a.get("password", cfgmod.DEFAULT_PASSWORD))
        self.a_pass.setEchoMode(QLineEdit.EchoMode.Password)
        form_row(f1, "Brend", self.a_brand)
        form_row(f1, "IP manzil", self.a_ip)
        form_row(f1, "Login", self.a_login)
        form_row(f1, "Parol", self.a_pass)
        l2.addLayout(f1)
        lay.addWidget(c2)

        # ---- video kamera (zavod ham, kon ham) ----
        self.c_video, lv = card("Video kamera",
                                "Mashina o'tishini videoga oladigan kamera (main stream)",
                                icon="video")
        fv = QFormLayout(); fv.setSpacing(10)
        v = self.st.setdefault("video", cfgmod.default_video())
        self.v_brand = QComboBox(); self.v_brand.addItems(["dahua", "hikvision"])
        self.v_brand.setCurrentText(v.get("brand", "dahua"))
        self.v_ip = QLineEdit(v.get("ip", "")); self.v_ip.setPlaceholderText("192.168.1.11")
        self.v_login = QLineEdit(v.get("login", cfgmod.DEFAULT_LOGIN))
        self.v_pass = QLineEdit(v.get("password", cfgmod.DEFAULT_PASSWORD))
        self.v_pass.setEchoMode(QLineEdit.EchoMode.Password)
        form_row(fv, "Brend", self.v_brand)
        form_row(fv, "IP manzil", self.v_ip)
        form_row(fv, "Login", self.v_login)
        form_row(fv, "Parol", self.v_pass)
        lv.addLayout(fv)

        zrow = QHBoxLayout()
        zrow.setSpacing(10)
        self.zone_btn = QPushButton(" Zona va yo'nalishni chizish")
        self.zone_btn.setIcon(svg_icon("zone", "#FFFFFF"))
        self.zone_btn.setObjectName("success")
        self.zone_btn.clicked.connect(self._draw_zone)
        self.zone_icon = QLabel()
        self.zone_icon.setStyleSheet("background: transparent;")
        self.zone_lbl = QLabel()
        self._update_zone_lbl()
        zrow.addWidget(self.zone_btn)
        zrow.addWidget(self.zone_icon)
        zrow.addWidget(self.zone_lbl)
        zrow.addStretch()
        lv.addLayout(zrow)
        line_hint = QLabel("Mashina zonaga kirishi bilan video yozila boshlaydi; "
                           "qaysi tomondan kirgani yo'nalishni (kirish/chiqish) beradi.")
        line_hint.setObjectName("cardHint")
        line_hint.setWordWrap(True)
        lv.addWidget(line_hint)
        lay.addWidget(self.c_video)

        # ---- ZAVOD: tarozi ----
        self.c_scale, ls = card("Tarozi — KELI D12",
                                "RS-232 orqali ulanadi. Silkinishda eng ko'p takrorlangan vazn olinadi.",
                                icon="scale")
        fs = QFormLayout(); fs.setSpacing(10)
        s = self.st.setdefault("scale", cfgmod.default_scale())
        self.s_type = QComboBox()
        self.s_type.addItem("Serial (COM port) — haqiqiy tarozi", "serial")
        self.s_type.addItem("Simulyator — test uchun", "sim")
        self.s_type.setCurrentIndex(0 if s.get("type", "serial") == "serial" else 1)
        self.s_port = QLineEdit(s.get("port", "COM3")); self.s_port.setPlaceholderText("COM3")
        self.s_baud = QSpinBox(); self.s_baud.setRange(1200, 115200)
        self.s_baud.setValue(int(s.get("baud", 9600)))
        self.s_minw = QSpinBox(); self.s_minw.setRange(0, 200000); self.s_minw.setSuffix(" kg")
        self.s_minw.setValue(int(s.get("min_weight", 500)))
        self.s_settle = QDoubleSpinBox(); self.s_settle.setRange(0.5, 60); self.s_settle.setSuffix(" s")
        self.s_settle.setValue(float(s.get("settle_time", 3.0)))
        self.s_tol = QSpinBox(); self.s_tol.setRange(1, 1000); self.s_tol.setSuffix(" kg")
        self.s_tol.setValue(int(s.get("stability_tolerance", 20)))
        form_row(fs, "Ulanish turi", self.s_type)
        form_row(fs, "COM port", self.s_port)
        form_row(fs, "Baud tezligi", self.s_baud)
        form_row(fs, "Min vazn (mashina bor)", self.s_minw)
        form_row(fs, "Barqarorlik vaqti", self.s_settle)
        form_row(fs, "Tebranish chegarasi (±)", self.s_tol)
        ls.addLayout(fs)
        lay.addWidget(self.c_scale)

        # ---- video klip (zavod ham, kon ham) ----
        self.c_clip, lc = card("Video klip", "Mashina kelganda yoziladigan klip sozlamalari",
                               icon="film")
        fc = QFormLayout(); fc.setSpacing(10)
        c = self.st.setdefault("capture", cfgmod.default_capture())
        self.c_dur = QSpinBox(); self.c_dur.setRange(3, 120); self.c_dur.setSuffix(" soniya")
        self.c_dur.setValue(int(c.get("duration", 10)))
        self.c_delay = QSpinBox(); self.c_delay.setRange(0, 60); self.c_delay.setSuffix(" soniya")
        self.c_delay.setValue(int(c.get("delay", 0)))
        form_row(fc, "Klip uzunligi", self.c_dur)
        form_row(fc, "Boshlanish kechikishi", self.c_delay)
        lc.addLayout(fc)
        lay.addWidget(self.c_clip)

        lay.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        # pastki tugmalar paneli
        footer = QFrame()
        footer.setObjectName("footer")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(24, 12, 24, 12)
        cancel = QPushButton("Bekor qilish")
        cancel.clicked.connect(self.reject)
        ok = QPushButton(" Saqlash")
        ok.setIcon(svg_icon("check", "#FFFFFF"))
        ok.setObjectName("primary")
        ok.setMinimumWidth(160)
        ok.clicked.connect(self._save)
        fl.addStretch()
        fl.addWidget(cancel)
        fl.addWidget(ok)
        outer.addWidget(footer)

        self._mode_changed()

    # ----- yordamchilar -----
    def _mode(self):
        return self.mode_cb.currentData()

    def _update_zone_lbl(self):
        z = self.st.get("zone")
        if z and z.get("polygon"):
            self.zone_icon.setPixmap(svg_pixmap("check", C_GREEN, 15))
            self.zone_lbl.setText("zona + yo'nalish tayyor")
            self.zone_lbl.setStyleSheet(f"color:{C_GREEN}; font-weight:600; background:transparent;")
        else:
            self.zone_icon.setPixmap(svg_pixmap("warn", C_AMBER, 15))
            self.zone_lbl.setText("hali chizilmagan")
            self.zone_lbl.setStyleSheet(f"color:{C_AMBER}; font-weight:600; background:transparent;")

    def _mode_changed(self, *_):
        # video + klip ikkala rejimda ham bor; faqat tarozi zavodgagina tegishli
        self.c_scale.setVisible(self._mode() == "zavod")

    def _draw_zone(self):
        ip = self.v_ip.text().strip()
        if not ip:
            QMessageBox.warning(self, "Zona", "Avval video kamera IP manzilini kiriting!")
            return
        rtsp = cfgmod.build_rtsp_url(self.v_brand.currentText(), ip,
                                     self.v_login.text(), self.v_pass.text())
        dlg = ZoneDirectionDialog(rtsp, zone=self.st.get("zone"), parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.st["zone"] = dlg.get_zone()
            self._update_zone_lbl()

    def _save(self):
        name = self.name_in.text().strip()
        if not name:
            QMessageBox.warning(self, "Xato", "Stansiya nomini kiriting!")
            return
        self.st["name"] = name
        self.st["camera_name"] = self.cam_in.text().strip() or name
        self.st["mode"] = self._mode()
        self.st["direction_reset_hours"] = self.dir_reset.value()
        self.st["anpr"] = {
            "brand": self.a_brand.currentText(), "ip": self.a_ip.text().strip(),
            "login": self.a_login.text(), "password": self.a_pass.text(),
        }
        # video + klip ikkala rejimda ham saqlanadi (kon = zavod, tarozisiz)
        ip = self.v_ip.text().strip()
        self.st["video"] = {
            "brand": self.v_brand.currentText(), "ip": ip,
            "login": self.v_login.text(), "password": self.v_pass.text(),
            "rtsp_main": cfgmod.build_rtsp_url(
                self.v_brand.currentText(), ip,
                self.v_login.text(), self.v_pass.text()) if ip else "",
        }
        self.st["capture"] = {"duration": self.c_dur.value(),
                              "delay": self.c_delay.value()}
        # eski (video'siz) kon konfiglarida bo'lmasligi mumkin
        self.st.setdefault("zone", None)
        self.st.setdefault("detector", cfgmod.default_detector())
        self.st.setdefault("crossing_window", 40.0)
        if self.st["mode"] == "zavod":
            self.st["scale"].update({
                "type": self.s_type.currentData(),
                "port": self.s_port.text().strip(),
                "baud": self.s_baud.value(),
                "min_weight": self.s_minw.value(),
                "settle_time": self.s_settle.value(),
                "stability_tolerance": self.s_tol.value(),
            })
        else:
            for k in ("scale", "anpr_window"):
                self.st.pop(k, None)
        self.accept()

    def get_station(self):
        return self.st


# ============================================================
#  STANSIYA RO'YXAT ELEMENTI (chiroyli kartochka)
# ============================================================
class StationItemWidget(QWidget):
    def __init__(self, st, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(14)

        is_zavod = st["mode"] == "zavod"
        icon_wrap = QLabel()
        icon_wrap.setPixmap(svg_pixmap("factory" if is_zavod else "mountain",
                                       C_ACCENT if is_zavod else C_MUTED, 26))
        icon_wrap.setStyleSheet(
            f"background: {'#EFF6FF' if is_zavod else '#F1F5F9'};"
            "border-radius: 10px; padding: 8px;")
        lay.addWidget(icon_wrap)

        mid = QVBoxLayout()
        mid.setSpacing(3)
        name = QLabel(st["name"])
        name.setStyleSheet(f"color:{C_TEXT}; font-size:15px; font-weight:700; background:transparent;")
        mid.addWidget(name)

        details = []
        details.append(f"ANPR: {st.get('anpr', {}).get('ip') or 'IP kiritilmagan'}")
        if is_zavod:
            details.append(f"Tarozi: {st.get('scale', {}).get('port', '?')}")
        details.append(f"Video: {st.get('video', {}).get('ip') or '—'}")
        info = QLabel("   •   ".join(details))
        info.setStyleSheet(f"color:{C_MUTED}; font-size:12.5px; background:transparent;")
        mid.addWidget(info)
        lay.addLayout(mid, 1)

        # badge'lar
        if is_zavod:
            lay.addWidget(badge("ZAVOD · asosiy", "#1D4ED8", "#DBEAFE"))
        else:
            lay.addWidget(badge("KON", "#475569", "#E2E8F0"))
        if st.get("zone", {}) and st.get("zone", {}).get("polygon"):
            lay.addWidget(badge("zona + yo'nalish", "#047857", "#D1FAE5"))
        else:
            lay.addWidget(badge("zona yo'q", "#B45309", "#FEF3C7"))


# ============================================================
#  ASOSIY SETUP OYNASI
# ============================================================
class SetupWindow(QWidget):
    saved = pyqtSignal()   # sozlamalar saqlanganda — tray shu signalni eshitadi

    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle("Karyer Local Server — Sozlash")
        self.setWindowIcon(svg_icon("settings", C_ACCENT))
        self.setMinimumSize(760, 720)
        self.setStyleSheet(APP_QSS)
        self.cfg = cfgmod.load_config() or cfgmod.default_config()
        self._provisioned_cameras = []   # provisioning'dan kelgan kamera ro'yxati

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("root")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(28, 24, 28, 16)
        lay.setSpacing(16)

        # ---- sarlavha ----
        trow = QHBoxLayout()
        trow.setSpacing(10)
        trow.addWidget(icon_label("settings", C_ACCENT, 26))
        title = QLabel("Karyer Local Server")
        title.setObjectName("h1")
        trow.addWidget(title)
        trow.addStretch()
        lay.addLayout(trow)
        sub = QLabel("Bir marta sozlang — keyin dastur fonda avtomatik ishlaydi.  "
                     "Tahrirlash uchun:  python main.py --setup")
        sub.setObjectName("sub")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        # ---- karyer ----
        c0, l0 = card("Karyer", icon="id")
        f0 = QFormLayout(); f0.setSpacing(10)
        self.quarry_in = QLineEdit(self.cfg.get("quarry_id", ""))
        self.quarry_in.setPlaceholderText("masalan: KARYER-01")
        form_row(f0, "Quarry ID", self.quarry_in)
        l0.addLayout(f0)
        lay.addWidget(c0)

        # ---- server ----
        c1, l1 = card("Server",
                      "Hodisalar shu serverga yuboriladi. Internet uzilsa — navbatda saqlanib, qayta yuboriladi.",
                      icon="globe")
        f1 = QFormLayout(); f1.setSpacing(10)
        srv = self.cfg.get("server", {})
        self.srv_url = QLineEdit(srv.get("url", ""))
        self.srv_url.setPlaceholderText("http://server-manzil:5555")
        self.srv_key = QLineEdit(srv.get("api_key", ""))
        self.srv_key.setPlaceholderText("maxfiy API kalit")
        form_row(f1, "Server URL", self.srv_url)
        form_row(f1, "API kalit", self.srv_key)
        l1.addLayout(f1)
        # --- token bilan avtomatik to'ldirish (provisioning, API.md §9) ---
        prov_row = QHBoxLayout()
        prov_row.setSpacing(10)
        self.prov_btn = QPushButton(" Serverdan olish (token)")
        self.prov_btn.setIcon(svg_icon("refresh", C_ACCENT))
        self.prov_btn.setObjectName("ghost")
        self.prov_btn.setToolTip(
            "web-main'dagi kalit tugmasidan olingan TOKENni joylab, quarry_id, "
            "API kalit va server URLni avtomatik to'ldiradi.")
        self.prov_btn.clicked.connect(self._provision_fetch)
        prov_row.addWidget(self.prov_btn)
        prov_row.addStretch()
        l1.addLayout(prov_row)
        self.srv_on = QCheckBox("Serverga yuborish yoqilgan")
        self.srv_on.setChecked(bool(srv.get("enabled", False)))
        self.srv_files = QCheckBox("Rasm va videoni fayl sifatida yuborish (siqilgan)")
        self.srv_files.setChecked(bool(srv.get("send_files", True)))
        l1.addWidget(self.srv_on)
        l1.addWidget(self.srv_files)
        lay.addWidget(c1)

        # ---- stansiyalar ----
        c2, l2 = card("Stansiyalar", icon="pin")
        hint = QLabel("Har bir nazorat nuqtasi — bitta stansiya.  Ikki marta bosib tahrirlang.")
        hint.setObjectName("cardHint")
        l2.addWidget(hint)

        self.st_list = QListWidget()
        self.st_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.st_list.itemDoubleClicked.connect(self._edit_station)
        self.st_list.setMinimumHeight(180)
        l2.addWidget(self.st_list)

        self.empty_lbl = QLabel("Hali stansiya qo'shilmagan — pastdagi tugmalar bilan qo'shing")
        self.empty_lbl.setStyleSheet(f"color:{C_MUTED}; font-size:13px; padding:8px; background:transparent;")
        self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l2.addWidget(self.empty_lbl)

        row = QHBoxLayout()
        row.setSpacing(10)
        add_zav = QPushButton(" Zavod stansiyasi")
        add_zav.setIcon(svg_icon("plus", "#FFFFFF"))
        add_zav.setObjectName("primary")
        add_zav.clicked.connect(lambda: self._add_station("zavod"))
        add_kon = QPushButton(" Kon stansiyasi")
        add_kon.setIcon(svg_icon("plus", C_TEXT))
        add_kon.clicked.connect(lambda: self._add_station("kon"))
        edit_b = QPushButton(" Tahrirlash")
        edit_b.setIcon(svg_icon("pencil", C_TEXT))
        edit_b.clicked.connect(self._edit_station)
        del_b = QPushButton(" O'chirish")
        del_b.setIcon(svg_icon("trash", C_RED))
        del_b.setObjectName("danger")
        del_b.clicked.connect(self._del_station)
        row.addWidget(add_zav)
        row.addWidget(add_kon)
        row.addStretch()
        row.addWidget(edit_b)
        row.addWidget(del_b)
        l2.addLayout(row)
        lay.addWidget(c2)

        lay.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        # ---- pastki panel ----
        footer = QFrame()
        footer.setObjectName("footer")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(28, 14, 28, 14)
        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("sub")
        save_btn = QPushButton(" Saqlash va yopish")
        save_btn.setIcon(svg_icon("save", "#FFFFFF"))
        save_btn.setObjectName("primary")
        save_btn.setMinimumHeight(46)
        save_btn.setMinimumWidth(220)
        save_btn.clicked.connect(self._save_all)
        fl.addWidget(self.status_lbl)
        fl.addStretch()
        fl.addWidget(save_btn)
        outer.addWidget(footer)

        self._refresh_list()

    # ----- stansiya ro'yxati -----
    def _refresh_list(self):
        self.st_list.clear()
        stations = self.cfg.get("stations", [])
        self.empty_lbl.setVisible(not stations)
        self.st_list.setVisible(bool(stations))
        for st in stations:
            item = QListWidgetItem()
            w = StationItemWidget(st)
            item.setSizeHint(QSize(0, 74))
            self.st_list.addItem(item)
            self.st_list.setItemWidget(item, w)
        n_zav = sum(1 for s in stations if s["mode"] == "zavod")
        n_kon = len(stations) - n_zav
        self.status_lbl.setText(f"{n_zav} zavod  •  {n_kon} kon stansiyasi")

    def _add_station(self, mode):
        n = sum(1 for s in self.cfg["stations"] if s["mode"] == mode) + 1
        default_name = f"{mode}-{n}"
        st = (cfgmod.make_zavod_station(default_name) if mode == "zavod"
              else cfgmod.make_kon_station(default_name))
        dlg = StationDialog(st, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.cfg["stations"].append(dlg.get_station())
            self._refresh_list()

    def _edit_station(self, *_):
        idx = self.st_list.currentRow()
        if idx < 0:
            QMessageBox.information(self, "Tanlash", "Avval ro'yxatdan stansiyani tanlang.")
            return
        dlg = StationDialog(self.cfg["stations"][idx], self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.cfg["stations"][idx] = dlg.get_station()
            self._refresh_list()

    def _del_station(self):
        idx = self.st_list.currentRow()
        if idx < 0:
            QMessageBox.information(self, "Tanlash", "Avval ro'yxatdan stansiyani tanlang.")
            return
        st = self.cfg["stations"][idx]
        if QMessageBox.question(
                self, "O'chirish",
                f"'{st['name']}' stansiyasi o'chirilsinmi?") == QMessageBox.StandardButton.Yes:
            self.cfg["stations"].pop(idx)
            self._refresh_list()

    # ----- provisioning (token bilan serverdan olish) -----
    def _provision_fetch(self):
        """TOKENni so'rab, serverdan config oladi va maydonlarni to'ldiradi."""
        token, ok = QInputDialog.getMultiLineText(
            self, "Serverdan olish",
            "web-main'dagi kalit tugmasidan olingan TOKENni bu yerga joylang:")
        if not ok or not token.strip():
            return
        import provision
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            remote = provision.fetch_remote_config(token.strip())
        except provision.ProvisionError as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Xato", str(e))
            return
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Xato", f"Kutilmagan xato: {e}")
            return
        QApplication.restoreOverrideCursor()

        srv = remote.get("server", {})
        self.quarry_in.setText(remote.get("quarry_id", ""))
        self.srv_url.setText(srv.get("url", ""))
        self.srv_key.setText(srv.get("api_key", ""))
        self.srv_on.setChecked(bool(srv.get("enabled", True)))
        self.srv_files.setChecked(bool(srv.get("send_files", True)))
        # keyingi safar stansiya tahrirlanganda camera_name taklifi uchun saqlab qo'yamiz
        self._provisioned_cameras = remote.get("cameras", [])

        cams = provision._fmt_cameras(self._provisioned_cameras)
        QMessageBox.information(
            self, "Olindi ✓",
            f"Karyer: {remote.get('quarry_name', '')} [{remote.get('quarry_id', '')}]\n"
            f"Server URL va API kalit to'ldirildi.\n\n{cams}\n\n"
            "Endi stansiya kamera IP/parol va camera_name'ni sozlang "
            "(camera_name yuqoridagi ro'yxatdagi biriga mos bo'lsin).")

    # ----- saqlash -----
    def _save_all(self):
        if not self.quarry_in.text().strip():
            QMessageBox.warning(self, "Xato", "Quarry ID kiriting!")
            return
        self.cfg["quarry_id"] = self.quarry_in.text().strip()
        prev_srv = self.cfg.get("server", {})
        self.cfg["server"] = {
            "url": self.srv_url.text().strip(),
            "api_key": self.srv_key.text().strip(),
            "enabled": self.srv_on.isChecked(),
            "send_files": self.srv_files.isChecked(),
            "endpoint": prev_srv.get("endpoint", "/api/weigh"),
            # GUI'da tugma yo'q — mavjud qiymatni saqlaymiz (tushib qolmasin)
            "send_images": prev_srv.get("send_images", True),
        }
        self.cfg.setdefault("media", cfgmod.default_media())
        path = cfgmod.save_config(self.cfg)
        self.saved.emit()   # tray eshitadi -> yangi config bilan qayta ishga tushiradi
        QMessageBox.information(
            self, "Saqlandi ✓",
            f"Sozlamalar saqlandi:\n{path}\n\n"
            "Dastur yangi sozlamalar bilan avtomatik qayta ishga tushadi "
            "(fon rejimida).")
        self.close()


def run():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    # tahrirlash bo'lsa parol so'raladi (birinchi o'rnatishda emas)
    if not check_edit_access():
        return
    win = SetupWindow()
    win.show()
    app.exec()


if __name__ == "__main__":
    run()

#!/usr/bin/env python3
"""
SVG ikonkalar — yagona standart (24x24, chiziqli/stroke uslub, Lucide'ga o'xshash).

Foydalanish:
    from icons import svg_icon, svg_pixmap
    btn.setIcon(svg_icon("save", "#FFFFFF"))
    label.setPixmap(svg_pixmap("factory", "#2563EB", 22))
"""

from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtCore import Qt, QByteArray, QRectF
from PyQt6.QtSvg import QSvgRenderer

_TPL = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '{body}</svg>')

_ICONS = {
    # umumiy
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1L7 17M17 7l2.1-2.1"/>',
    "id":       '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="11" r="2"/><path d="M6 16c.7-1.5 1.8-2 3-2s2.3.5 3 2M14 9h4M14 13h4"/>',
    "globe":    '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.5 3.5 5.5 3.5 9s-1 6.5-3.5 9c-2.5-2.5-3.5-5.5-3.5-9s1-6.5 3.5-9z"/>',
    "pin":      '<path d="M12 21c-4-4.2-7-7.3-7-10.8A7 7 0 0 1 19 10.2c0 3.5-3 6.6-7 10.8z"/><circle cx="12" cy="10" r="2.5"/>',
    "camera":   '<path d="M9.5 5.5 8 8H5a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2h-3l-1.5-2.5h-5z" transform="translate(0,-1)"/><circle cx="12" cy="13" r="3.2"/>',
    "video":    '<rect x="2" y="6" width="13" height="12" rx="2"/><path d="M22 8.5 15 12l7 3.5v-7z"/>',
    "scale":    '<circle cx="12" cy="5" r="2.5"/><path d="M8.5 8.5h7L18 20H6L8.5 8.5z"/><path d="M9.5 16h5"/>',
    "film":     '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M8 4v16M16 4v16M3 9h5M3 15h5M16 9h5M16 15h5"/>',
    "zone":     '<path d="M3 8V5a2 2 0 0 1 2-2h3M16 3h3a2 2 0 0 1 2 2v3M21 16v3a2 2 0 0 1-2 2h-3M8 21H5a2 2 0 0 1-2-2v-3"/><circle cx="12" cy="12" r="2"/>',
    "factory":  '<path d="M3 21h18M5 21V10l5 3v-3l5 3V6.5h4V21"/><path d="M9 17h1M13 17h1"/>',
    "mountain": '<path d="M3 20h18L14 7l-3.5 5.5L8.5 9 3 20z"/>',
    "plus":     '<path d="M12 5v14M5 12h14"/>',
    "pencil":   '<path d="M17 3.5a2.1 2.1 0 0 1 3 3L7.5 19 3 20l1-4.5L16.5 3.5z"/>',
    "trash":    '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v5M14 11v5"/>',
    "save":     '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><path d="M17 21v-8H7v8M7 3v5h8"/>',
    "check":    '<path d="M20 6 9 17l-5-5"/>',
    "warn":     '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
    "eraser":   '<path d="M20 20H8L3.5 15.5a2 2 0 0 1 0-2.8L13 3.3a2 2 0 0 1 2.8 0l4.9 4.9a2 2 0 0 1 0 2.8L12 20"/><path d="M7.5 11.5l5 5"/>',
    "x":        '<path d="M18 6 6 18M6 6l12 12"/>',
    "truck":    '<rect x="1" y="6" width="14" height="10" rx="1"/><path d="M15 10h4l3 3v3h-7"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/>',
    "arrow-in": '<path d="M9 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h4M13 8l4 4-4 4M17 12H7" transform="translate(2,0) scale(0.92)"/>',
    "arrow-out":'<path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l-4-4 4-4M6 13h10" transform="scale(0.92)"/>',
    "folder":   '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/>',
    "refresh":  '<path d="M21 12a9 9 0 1 1-2.64-6.36M21 4v5h-5"/>',
    "power":    '<path d="M12 4v8M7.8 6.8a7 7 0 1 0 8.4 0"/>',
    "activity": '<path d="M3 12h4l3 8 4-16 3 8h4"/>',
}


def svg_bytes(name, color="#0F172A"):
    body = _ICONS.get(name, _ICONS["settings"])
    return _TPL.format(color=color, body=body).encode()


def svg_pixmap(name, color="#0F172A", size=20):
    """SVG'ni QPixmap ga render qiladi (retina uchun 2x)."""
    renderer = QSvgRenderer(QByteArray(svg_bytes(name, color)))
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    renderer.render(p, QRectF(0, 0, size * 2, size * 2))
    p.end()
    pm.setDevicePixelRatio(2)
    return pm


def svg_icon(name, color="#0F172A", size=20):
    return QIcon(svg_pixmap(name, color, size))

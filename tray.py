#!/usr/bin/env python3
"""
Tray xizmati — dastur soat yonidagi ikonka sifatida FONDA ishlaydi.

Ikonkani o'ng tugma bilan bosib:
  - holatni ko'rish (nechta stansiya, navbatda nechta hodisa)
  - Sozlamalarni tahrirlash (saqlangach avtomatik qayta ishga tushadi)
  - Qayta ishga tushirish
  - Rasm/videolar papkasini ochish
  - Chiqish

Talab: PyQt6. System tray bo'lmasa main.py konsol rejimiga o'tadi.
"""

import os
import sys
import subprocess

from PyQt6.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QMessageBox)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import QTimer

import config as cfgmod
from manager import StationManager, _abs
from icons import svg_icon
from setup_gui import SetupWindow, check_edit_access

ACCENT = "#2563EB"
GREEN = "#059669"
RED = "#DC2626"
TEXT = "#0F172A"


class TrayApp:
    def __init__(self, app):
        self.app = app
        self.mgr = StationManager(sim=False)
        self.setup_win = None

        self.tray = QSystemTrayIcon(svg_icon("activity", ACCENT, 22))
        self.tray.setToolTip("Karyer Local Server")

        # menu — QAction'lar parent (menu) bilan yaratiladi, aks holda
        # lokal o'zgaruvchilar garbage-collector tomonidan o'chib ketadi
        self.menu = QMenu()
        self.status_act = QAction("Ishga tushmoqda...", self.menu)
        self.status_act.setEnabled(False)
        self.menu.addAction(self.status_act)
        self.menu.addSeparator()

        act_setup = QAction(svg_icon("settings", TEXT), "Sozlamalarni tahrirlash", self.menu)
        act_setup.triggered.connect(self.open_setup)
        self.menu.addAction(act_setup)

        act_restart = QAction(svg_icon("refresh", TEXT), "Qayta ishga tushirish", self.menu)
        act_restart.triggered.connect(self.restart)
        self.menu.addAction(act_restart)

        act_folder = QAction(svg_icon("folder", TEXT), "Rasm/videolar papkasi", self.menu)
        act_folder.triggered.connect(self.open_folder)
        self.menu.addAction(act_folder)

        self.menu.addSeparator()
        act_quit = QAction(svg_icon("power", RED), "Chiqish", self.menu)
        act_quit.triggered.connect(self.quit)
        self.menu.addAction(act_quit)

        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_activate)
        self.tray.show()

        # stansiyalarni ishga tushiramiz
        n = self.mgr.start_all()
        if not n:
            self._notify("Sozlanmagan", "Stansiya yo'q — «Sozlamalarni tahrirlash» ni bosing")
        else:
            self._notify("Karyer Local Server", "Fon rejimida ishga tushdi")

        self.timer = QTimer()
        self.timer.timeout.connect(self._update_status)
        self.timer.start(3000)
        self._update_status()

    # ---- holat ----
    def _update_status(self):
        s = self.mgr.status()
        if s["running"] and s["stations"]:
            txt = f"● Ishlayapti — {s['stations']} stansiya · navbat: {s['pending']}"
            self.tray.setIcon(svg_icon("activity", GREEN, 22))
        else:
            txt = "○ To'xtatilgan yoki sozlanmagan"
            self.tray.setIcon(svg_icon("activity", RED, 22))
        self.status_act.setText(txt)
        self.tray.setToolTip("Karyer Local Server\n" + txt)

    def _on_activate(self, reason):
        # ikonkaga ikki marta bosilsa — sozlash oynasi
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.open_setup()

    # ---- amallar ----
    def open_setup(self):
        if self.setup_win is not None and self.setup_win.isVisible():
            self.setup_win.raise_()
            self.setup_win.activateWindow()
            return
        # tahrirlash uchun parol (birinchi o'rnatishda so'ralmaydi)
        if not check_edit_access():
            return
        self.setup_win = SetupWindow()
        self.setup_win.saved.connect(self.on_saved)
        self.setup_win.show()
        self.setup_win.raise_()
        self.setup_win.activateWindow()

    def on_saved(self):
        """Sozlamalar saqlangach — yangi config bilan qayta ishga tushirish."""
        self.mgr.restart()
        self._update_status()
        self._notify("Sozlamalar yangilandi", "Dastur qayta ishga tushdi")

    def restart(self):
        self.mgr.restart()
        self._update_status()
        self._notify("Karyer Local Server", "Qayta ishga tushirildi")

    def open_folder(self):
        cfg = cfgmod.load_config() or cfgmod.default_config()
        path = _abs(cfg.get("save_dir", "captures"))
        os.makedirs(path, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)          # noqa
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            print(f"papka ochilmadi: {e}")

    def _notify(self, title, msg):
        try:
            self.tray.showMessage(title, msg,
                                  QSystemTrayIcon.MessageIcon.Information, 3000)
        except Exception:
            pass

    def quit(self):
        r = QMessageBox.question(
            None, "Chiqish",
            "Dasturni butunlay to'xtatib chiqasizmi?\n\n"
            "Fon xizmati o'chadi — yangi hodisalar yig'ilmaydi.\n"
            "(Yig'ilgan, hali yuborilmagan hodisalar saqlanib qoladi.)")
        if r == QMessageBox.StandardButton.Yes:
            self.mgr.stop_all()
            self.tray.hide()
            self.app.quit()


def run():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    # setup oynasi yopilganda dastur chiqib ketmasin — tray'da qoladi
    app.setQuitOnLastWindowClosed(False)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        raise RuntimeError("system tray mavjud emas")
    TrayApp(app)
    app.exec()


if __name__ == "__main__":
    run()

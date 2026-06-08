# -*- mode: python ; coding: utf-8 -*-
# PyInstaller-Spec — baut garmin-sync.exe (kein Konsolenfenster)
# Ausführen: pyinstaller build.spec

import os
from PyInstaller.utils.hooks import collect_all, copy_metadata

pkg_datas, pkg_binaries, pkg_hiddenimports = [], [], []
for pkg in ("garminconnect", "garth", "curl_cffi"):
    d, b, h = collect_all(pkg)
    pkg_datas += d
    pkg_binaries += b
    pkg_hiddenimports += h
    pkg_datas += copy_metadata(pkg)

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=pkg_binaries,
    datas=[
        (os.path.join(SPECPATH, "assets", "icon-master"), "assets/icon-master"),
        (os.path.join(SPECPATH, "assets", "garmin-sync.ico"), "assets"),
    ] + pkg_datas,
    hiddenimports=[
        "pystray._win32",
        "PIL._tkinter_finder",
        "garminconnect",
        "garth",
        "watchdog.observers.winapi",
        "tkinter",
        "tkinter.font",
        "tkinter.simpledialog",
        "tkinter.messagebox",
        "PIL.ImageTk",
    ] + pkg_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="garmin-sync",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # Kein Konsolenfenster — Tray-App
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(SPECPATH, "assets", "garmin-sync.ico"),
)

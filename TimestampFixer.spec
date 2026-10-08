# -*- mode: python ; coding: utf-8 -*-

import sys

# Windows and Linux get a single self-contained executable. macOS gets a
# one-folder build wrapped in a .app bundle instead: a one-file executable
# inside a bundle unpacks itself on every launch and cannot be code signed.
IS_MAC = sys.platform == 'darwin'


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    *([] if IS_MAC else [a.binaries, a.datas]),
    [],
    exclude_binaries=IS_MAC,
    name='TimestampFixer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=not IS_MAC,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

if IS_MAC:
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name='TimestampFixer',
    )
    app = BUNDLE(
        coll,
        name='TimestampFixer.app',
        icon=None,
        bundle_identifier='com.timestamp-gui.TimestampFixer',
    )

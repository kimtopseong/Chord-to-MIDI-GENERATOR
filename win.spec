# -*- mode: python ; coding: utf-8 -*-
import os

# __file__ 대신 PyInstaller의 내장 변수인 SPECPATH 사용
BASE = os.path.abspath(os.path.dirname(SPECPATH))

a = Analysis(
    ['main.py'],
    pathex=[BASE], 
    binaries=[],
    datas=[
        ('loading.png', '.'),
        ('pro_theme.json', '.'),
        ('root.json', '.')
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Chord-to-MIDI-GENERATOR',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch='x86',
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Chord-to-MIDI-GENERATOR',
)
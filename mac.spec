# -*- mode: python ; coding: utf-8 -*-
import os

# __file__ 대신 PyInstaller의 내장 변수인 SPECPATH 사용
BASE = os.path.abspath(os.path.dirname(SPECPATH))

a = Analysis(
    ['main.py'],
    pathex=[BASE],  # 'pathex'는 한 번만, 그리고 BASE를 사용해야 합니다.
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
app = BUNDLE(
    coll,
    name='Chord-to-MIDI-GENERATOR.app',
    icon=None,
    bundle_identifier=None,
)
# -*- mode: python ; coding: utf-8 -*-
import os

BASE = os.path.abspath(os.path.dirname(__file__))

def data_if_exists(path, dest='.'):
    abs_path = os.path.join(BASE, path) if not os.path.isabs(path) else path
    return [(abs_path, dest)] if os.path.exists(abs_path) else []

# Collect only existing resources to prevent build errors on CI
datas_list = []
for res in ['loading.png', 'pro_theme.json', 'root.json']:
    datas_list += data_if_exists(res, '.')

a = Analysis(
    ['main.py'],
    pathex=[BASE],
    binaries=[],
    datas=datas_list,
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
    # Thin build (runner-native arch). Do NOT set target_arch here.
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
